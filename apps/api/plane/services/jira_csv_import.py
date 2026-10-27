"""Validated, lossless, create-only Jira CSV import for a new project."""

import csv
import hashlib
import html
import io
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q

from plane.db.models import (
    Cycle,
    CycleIssue,
    Issue,
    IssueImportMetadata,
    IssueLabel,
    IssueRelation,
    IssueSequence,
    IssueType,
    Label,
    Project,
    ProjectIdentifier,
    ProjectIssueType,
    ProjectMember,
    State,
    Workspace,
    WorkspaceMember,
)

SOURCE = "jira_csv"
LEVELS = {"Epic": 0, "Task": 1, "Bug": 1, "Subtask": 2}
TYPE_COLORS = {"Epic": "#9333EA", "Task": "#3E63DD", "Bug": "#DC2626", "Subtask": "#0891B2"}
GROUPS = {"To Do": "unstarted", "In Progress": "started", "Done": "completed"}
PRIORITIES = {"Highest": "urgent", "High": "high", "Medium": "medium", "Low": "low", "Lowest": "low", "": "none"}
REQUIRED = (
    "Summary",
    "Issue key",
    "Issue id",
    "Issue Type",
    "Status",
    "Status category",
    "Project key",
    "Project name",
    "Priority",
    "Description",
    "Created",
    "Updated",
    "Resolved",
    "Due date",
    "Custom field (Start date)",
    "Parent",
    "Parent key",
    "Sprint",
)


def read_jira_csv(path, timezone_name="Asia/Bangkok"):
    raw = Path(path).read_bytes()
    table = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True))
    if len(table) < 2:
        raise ValueError("The CSV must contain a header and at least one work item.")
    headers, values = table[0], table[1:]
    positions = {name: [i for i, item in enumerate(headers) if item == name] for name in headers}
    for name in REQUIRED:
        if len(positions.get(name, [])) != 1:
            raise ValueError(f"Expected one column named {name}.")
    zone = ZoneInfo(timezone_name)
    rows, by_key, by_id, states, links = [], {}, {}, {}, set()
    for line, cells in enumerate(values, start=2):
        if len(cells) != len(headers):
            raise ValueError(f"Record {line}: expected {len(headers)} cells, got {len(cells)}.")
        row = {name: cells[indexes[0]] for name, indexes in positions.items()}
        key, source_id = row["Issue key"], row["Issue id"]
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*)-([1-9][0-9]*)", key)
        if not match or match[1] != row["Project key"] or not source_id:
            raise ValueError(f"Record {line}: invalid source key or ID.")
        if key in by_key or source_id in by_id:
            raise ValueError(f"Duplicate source key or ID: {key}.")
        if not row["Summary"].strip() or len(row["Summary"]) > 255:
            raise ValueError(f"{key}: Summary is required and must fit 255 characters.")
        if row["Issue Type"] not in LEVELS or row["Status category"] not in GROUPS:
            raise ValueError(f"{key}: unsupported type or status category.")
        if not row["Status"].strip() or len(row["Status"]) > 255 or len(row["Sprint"]) > 255:
            raise ValueError(f"{key}: invalid status or Sprint name.")
        if row["Priority"] not in PRIORITIES:
            raise ValueError(f"{key}: unsupported priority {row['Priority']}.")
        group = GROUPS[row["Status category"]]
        if row["Status"] in states and states[row["Status"]] != group:
            raise ValueError(f"{key}: conflicting status category.")
        states[row["Status"]] = group
        row["_dates"] = {}
        for field in (
            "Created",
            "Updated",
            "Resolved",
            "Last Viewed",
            "Status category changed",
            "Due date",
            "Custom field (Start date)",
        ):
            value = row.get(field, "")
            try:
                row["_dates"][field] = (
                    datetime.strptime(value, "%d/%b/%y %I:%M %p").replace(tzinfo=zone) if value else None
                )
            except ValueError as exc:
                raise ValueError(f"{key}: invalid date in {field}: {value}.") from exc
        if not row["_dates"]["Created"] or not row["_dates"]["Updated"]:
            raise ValueError(f"{key}: Created and Updated are required.")
        start, due = row["_dates"]["Custom field (Start date)"], row["_dates"]["Due date"]
        if start and due and start > due:
            raise ValueError(f"{key}: start date exceeds due date.")
        row["_labels"] = list(dict.fromkeys(cells[i] for i in positions.get("Labels", []) if cells[i]))
        if any(len(label) > 255 for label in row["_labels"]):
            raise ValueError(f"{key}: a label exceeds 255 characters.")
        row["_raw"] = [{"column_index": i, "name": name, "value": cells[i]} for i, name in enumerate(headers)]
        row["_number"] = int(match[2])
        for i in positions.get("Inward issue link (Blocks)", []):
            if cells[i]:
                links.add((key, cells[i]))  # this issue is blocked by the inward issue
        for i in positions.get("Outward issue link (Blocks)", []):
            if cells[i]:
                links.add((cells[i], key))
        rows.append(row)
        by_key[key], by_id[source_id] = row, row
    if len({(r["Project key"], r["Project name"]) for r in rows}) != 1:
        raise ValueError("Import one Jira project at a time.")
    for row in rows:
        parent_key, parent_id = row["Parent key"], row["Parent"]
        if bool(parent_key) != bool(parent_id):
            raise ValueError(f"{row['Issue key']}: parent key and ID must both be present.")
        if parent_key and (parent_key not in by_key or by_key[parent_key]["Issue id"] != parent_id):
            raise ValueError(f"{row['Issue key']}: missing or inconsistent parent reference.")
        if parent_key and LEVELS[row["Issue Type"]] != LEVELS[by_key[parent_key]["Issue Type"]] + 1:
            raise ValueError(f"{row['Issue key']}: invalid parent/child type hierarchy.")
        seen, current = set(), row
        while current["Parent key"]:
            if current["Parent key"] not in by_key:
                raise ValueError(f"Missing parent: {current['Parent key']}.")
            if current["Issue key"] in seen:
                raise ValueError("Cyclic parent hierarchy.")
            seen.add(current["Issue key"])
            current = by_key[current["Parent key"]]
    for child, blocker in links:
        if child == blocker or child not in by_key or blocker not in by_key:
            raise ValueError(f"Invalid blocking reference: {child}, {blocker}.")
    return {
        "rows": rows,
        "states": states,
        "links": sorted(links),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "timezone": timezone_name,
        "project_key": rows[0]["Project key"],
        "project_name": rows[0]["Project name"],
        "summary": {
            "items": len(rows),
            "columns": len(headers),
            "types": dict(Counter(r["Issue Type"] for r in rows)),
            "parents": sum(bool(r["Parent key"]) for r in rows),
            "blocking_relations": len(links),
            "cycles": len({r["Sprint"] for r in rows if r["Sprint"]}),
            "cycle_items": sum(bool(r["Sprint"]) for r in rows),
            "next_issue_number": max(r["_number"] for r in rows) + 1,
        },
    }


def import_jira_csv(data, workspace_slug, actor_id, apply=False):
    workspace = Workspace.objects.get(slug=workspace_slug)
    if not WorkspaceMember.objects.filter(workspace=workspace, member_id=actor_id, role=20, is_active=True).exists():
        raise ValueError("The import actor must be an active workspace administrator.")
    if len(data["project_key"]) > 12 or len(data["project_name"]) > 255:
        raise ValueError("Project identifier or name is too long for Plane.")
    identity = f"{data['project_key']}:{data['sha256']}"

    def existing_project():
        existing = (
            Project.all_objects.filter(workspace=workspace)
            .filter(Q(identifier=data["project_key"]) | Q(name=data["project_name"]))
            .first()
        )
        if existing:
            if existing.deleted_at or existing.external_source != SOURCE or existing.external_id != identity:
                raise ValueError("Project name/identifier already exists with different data; nothing was overwritten.")
            if IssueImportMetadata.objects.filter(project=existing, file_sha256=data["sha256"]).count() != len(
                data["rows"]
            ):
                raise ValueError("Existing import metadata is incomplete; refusing to overwrite.")
        elif ProjectIdentifier.objects.filter(workspace=workspace, name=data["project_key"]).exists():
            raise ValueError("Project identifier is reserved; nothing was overwritten.")
        return existing

    existing = existing_project()
    result = {
        **data["summary"],
        "sha256": data["sha256"],
        "project_name": data["project_name"],
        "identifier": data["project_key"],
    }
    if existing:
        return {**result, "status": "already_imported", "project_id": str(existing.id)}
    if not apply:
        return {**result, "status": "dry_run"}
    with transaction.atomic():
        Workspace.objects.select_for_update().get(pk=workspace.pk)
        existing = existing_project()
        if existing:
            return {**result, "status": "already_imported", "project_id": str(existing.id)}
        project = Project.objects.create(
            workspace=workspace,
            name=data["project_name"],
            identifier=data["project_key"],
            description=data["rows"][0].get("Project description", ""),
            external_source=SOURCE,
            external_id=identity,
            timezone=data["timezone"],
            cycle_view=True,
            is_issue_type_enabled=True,
        )
        ProjectIdentifier.objects.create(project=project, workspace=workspace, name=project.identifier)
        ProjectMember.objects.create(project=project, member_id=actor_id, role=20)
        states, types, labels, cycles, issues = {}, {}, {}, {}, {}
        colors = {"unstarted": "#60646C", "started": "#F59E0B", "completed": "#46A758"}
        for index, (name, group) in enumerate(data["states"].items()):
            states[name] = State.objects.create(
                project=project,
                name=name,
                group=group,
                color=colors[group],
                sequence=(index + 1) * 10000,
                default=name == "To Do",
                external_source=SOURCE,
                external_id=name,
            )
        default = states.get("To Do") or next(iter(states.values()))
        State.objects.filter(pk=default.pk).update(default=True)
        Project.objects.filter(pk=project.pk).update(default_state=default)

        def normalize(value):
            return value.casefold().replace("-", "").replace(" ", "")

        for name in dict.fromkeys(r["Issue Type"] for r in data["rows"]):
            issue_type = next(
                (
                    t
                    for t in IssueType.objects.filter(workspace=workspace, is_active=True).order_by("created_at", "id")
                    if normalize(t.name) == normalize(name)
                ),
                None,
            )
            if issue_type is None:
                issue_type = IssueType.objects.create(
                    workspace=workspace, name=name, is_epic=name == "Epic", color=TYPE_COLORS[name]
                )
            types[name] = issue_type
            ProjectIssueType.objects.create(
                project=project, issue_type=issue_type, level=LEVELS[name], is_default=name == "Task"
            )
        for row in sorted(data["rows"], key=lambda r: r["_number"]):
            dates = row["_dates"]
            text = html.escape(row["Description"]).replace("\r\n", "\n").replace("\n", "<br>")
            issue = Issue.objects.create(
                project=project,
                name=row["Summary"],
                description_html=f"<p>{text}</p>",
                type=types[row["Issue Type"]],
                state=states[row["Status"]],
                priority=PRIORITIES[row["Priority"]],
                start_date=dates["Custom field (Start date)"].date() if dates["Custom field (Start date)"] else None,
                target_date=dates["Due date"].date() if dates["Due date"] else None,
                external_source=SOURCE,
                external_id=row["Issue id"],
            )
            # Model save allocates sequence IDs and completion times; restore source values explicitly.
            IssueSequence.objects.filter(issue=issue).update(sequence=row["_number"])
            Issue.objects.filter(pk=issue.pk).update(
                sequence_id=row["_number"],
                created_at=dates["Created"],
                updated_at=dates["Updated"],
                completed_at=dates["Resolved"],
                sort_order=0,
            )
            issues[row["Issue key"]] = issue
            IssueImportMetadata.objects.create(
                project=project,
                issue=issue,
                source=SOURCE,
                source_issue_id=row["Issue id"],
                source_issue_key=row["Issue key"],
                file_sha256=data["sha256"],
                source_timezone=data["timezone"],
                fields=row["_raw"],
            )
            for name in row["_labels"]:
                if name not in labels:
                    labels[name] = Label.objects.create(
                        project=project, workspace=workspace, name=name, color="#60646C"
                    )
                IssueLabel.objects.create(project=project, issue=issue, label=labels[name])
            sprint = row["Sprint"]
            if sprint:
                if sprint not in cycles:
                    cycles[sprint] = Cycle.objects.create(
                        project=project,
                        name=sprint,
                        owned_by_id=actor_id,
                        timezone=data["timezone"],
                        external_source=SOURCE,
                        external_id=sprint,
                    )
                CycleIssue.objects.create(project=project, issue=issue, cycle=cycles[sprint])
        for order, row in enumerate(
            sorted(data["rows"], key=lambda r: (r.get("Custom field (Rank)", ""), r["_number"]))
        ):
            Issue.objects.filter(pk=issues[row["Issue key"]].pk).update(
                parent_id=issues[row["Parent key"]].pk if row["Parent key"] else None,
                sort_order=(order + 1) * 10000,
            )
        for child, blocker in data["links"]:
            IssueRelation.objects.create(
                project=project, issue=issues[child], related_issue=issues[blocker], relation_type="blocked_by"
            )
        return {**result, "status": "imported", "project_id": str(project.id)}


def verify_jira_csv_import(data, project):
    """Reconcile every imported source cell and the native relationships."""
    issues = list(
        Issue.all_objects.filter(project=project, deleted_at__isnull=True)
        .select_related("state", "type", "import_metadata")
        .prefetch_related("labels", "assignees")
    )
    by_id = {issue.external_id: issue for issue in issues}
    by_key = {}
    if len(issues) != len(data["rows"]) or len(by_id) != len(issues):
        raise ValueError("Work item count or source IDs do not match.")
    cells = 0
    for row in data["rows"]:
        issue = by_id.get(row["Issue id"])
        if issue is None:
            raise ValueError(f"Missing issue {row['Issue key']}.")
        metadata = issue.import_metadata
        dates = row["_dates"]
        expected_dates = (
            dates["Created"],
            dates["Updated"],
            dates["Resolved"],
            dates["Custom field (Start date)"].date() if dates["Custom field (Start date)"] else None,
            dates["Due date"].date() if dates["Due date"] else None,
        )
        expected_text = html.escape(row["Description"]).replace("\r\n", "\n").replace("\n", "<br>")
        checks = {
            "source_columns": metadata.fields == row["_raw"],
            "source_identity": metadata.source_issue_key == row["Issue key"]
            and metadata.source_issue_id == row["Issue id"]
            and metadata.file_sha256 == data["sha256"],
            "summary": issue.name == row["Summary"],
            "description": issue.description_html == f"<p>{expected_text}</p>",
            "type": issue.type.name.casefold().replace("-", "") == row["Issue Type"].casefold().replace("-", ""),
            "state": issue.state.name == row["Status"] and issue.state.group == GROUPS[row["Status category"]],
            "priority": issue.priority == PRIORITIES[row["Priority"]],
            "dates": (issue.created_at, issue.updated_at, issue.completed_at, issue.start_date, issue.target_date)
            == expected_dates,
            "sequence": issue.sequence_id == row["_number"],
            "labels": {label.name for label in issue.labels.all()} == set(row["_labels"]),
            "assignees": not issue.assignees.all(),
        }
        for field, matches in checks.items():
            if not matches:
                raise ValueError(f"{row['Issue key']}: verification failed for {field}.")
        by_key[row["Issue key"]] = issue
        cells += len(row["_raw"])
    memberships = dict(CycleIssue.objects.filter(project=project).values_list("issue_id", "cycle__name"))
    for row in data["rows"]:
        issue = by_key[row["Issue key"]]
        parent = by_key[row["Parent key"]].id if row["Parent key"] else None
        if issue.parent_id != parent or memberships.get(issue.id, "") != row["Sprint"]:
            raise ValueError(f"{row['Issue key']}: incorrect parent or Sprint.")
    key_by_pk = {issue.pk: key for key, issue in by_key.items()}
    actual_links = {
        (key_by_pk[issue_id], key_by_pk[related_id])
        for issue_id, related_id in IssueRelation.objects.filter(
            project=project, relation_type="blocked_by"
        ).values_list("issue_id", "related_issue_id")
    }
    if actual_links != set(data["links"]):
        raise ValueError("Blocking relations do not match.")
    if Cycle.objects.filter(project=project).count() != data["summary"]["cycles"]:
        raise ValueError("Cycle count does not match.")
    if Cycle.objects.filter(project=project).exclude(start_date=None, end_date=None).exists():
        raise ValueError("Unexpected invented Sprint dates.")
    largest = IssueSequence.objects.filter(project=project).order_by("-sequence").first()
    if largest.sequence + 1 != data["summary"]["next_issue_number"]:
        raise ValueError("Next work item number is incorrect.")
    return {**data["summary"], "verified_source_cells": cells, "status": "verified", "project_id": str(project.id)}
