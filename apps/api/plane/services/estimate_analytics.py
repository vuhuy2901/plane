from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from plane.db.models import EstimatePoint, Issue, IssueAssignee


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rounded(value):
    return round(float(value or 0), 2)


def _leaf_rows(scope, point_project_ids):
    active_parent_ids = Issue.issue_objects.filter(
        parent_id__in=scope.values("id"),
        archived_at__isnull=True,
        is_draft=False,
    ).values("parent_id")
    return list(
        scope.filter(project_id__in=point_project_ids)
        .exclude(id__in=active_parent_ids)
        .exclude(state__group="cancelled")
        .values(
            "id",
            "parent_id",
            "project_id",
            "project__name",
            "project__identifier",
            "name",
            "sequence_id",
            "state__group",
            "type_id",
            "type__name",
            "estimate_point_id",
            "estimate_point__value",
            "completed_at",
        )
    )


def build_estimate_analytics(
    *, current_scope, completion_scope, projects, cycles, range_start, range_end, count_mode="all"
):
    project_configs = list(projects.values("id", "name", "identifier", "estimate_id", "estimate__type"))
    point_projects = [project for project in project_configs if project["estimate__type"] == "points"]
    point_project_ids = [project["id"] for project in point_projects]
    incompatible_projects = [
        {
            "id": project["id"],
            "name": project["name"],
            "identifier": project["identifier"],
            "reason": "not_configured" if project["estimate_id"] is None else "non_points_estimate",
        }
        for project in project_configs
        if project["estimate__type"] != "points"
    ]

    rows = _leaf_rows(current_scope, point_project_ids)
    rows_by_id = {row["id"]: row for row in rows}
    estimated_rows = []
    for row in rows:
        value = _number(row["estimate_point__value"])
        row["estimate_value"] = value
        if value is not None:
            estimated_rows.append(row)

    total_points = sum(row["estimate_value"] for row in estimated_rows)
    completed_points = sum(row["estimate_value"] for row in estimated_rows if row["state__group"] == "completed")
    in_progress_points = sum(row["estimate_value"] for row in estimated_rows if row["state__group"] == "started")
    eligible_count = len(rows)
    estimated_count = len(estimated_rows)
    unestimated_count = eligible_count - estimated_count

    state_points = defaultdict(float)
    type_points = defaultdict(lambda: {"points": 0.0, "estimated_items": 0, "unestimated_items": 0})
    distribution_counts = defaultdict(int)
    project_metrics = defaultdict(
        lambda: {"total_points": 0.0, "completed_points": 0.0, "eligible_items": 0, "estimated_items": 0}
    )
    for row in rows:
        project_metric = project_metrics[row["project_id"]]
        project_metric["eligible_items"] += 1
        type_key = (row["type_id"], row["type__name"] or "No type")
        if row["estimate_value"] is None:
            type_points[type_key]["unestimated_items"] += 1
            continue
        value = row["estimate_value"]
        project_metric["estimated_items"] += 1
        project_metric["total_points"] += value
        if row["state__group"] == "completed":
            project_metric["completed_points"] += value
        state_points[row["state__group"] or "unstarted"] += value
        type_points[type_key]["points"] += value
        type_points[type_key]["estimated_items"] += 1
        distribution_counts[value] += 1

    values_by_estimate = defaultdict(set)
    for estimate_id, raw_value in EstimatePoint.objects.filter(
        project_id__in=point_project_ids,
        estimate_id__in=[project["estimate_id"] for project in point_projects],
    ).values_list("estimate_id", "value"):
        value = _number(raw_value)
        if value is not None:
            values_by_estimate[estimate_id].add(value)
    configured_values = set().union(*values_by_estimate.values()) if values_by_estimate else set()
    distribution = [
        {"value": value, "label": f"{value:g} SP", "work_items": distribution_counts[value]}
        for value in sorted(configured_values | set(distribution_counts))
    ]

    project_rows = []
    for project in project_configs:
        metric = project_metrics[project["id"]]
        total = metric["total_points"]
        completed = metric["completed_points"]
        project_rows.append(
            {
                "id": project["id"],
                "name": project["name"],
                "identifier": project["identifier"],
                "estimate_type": project["estimate__type"],
                "total_points": _rounded(total),
                "completed_points": _rounded(completed),
                "remaining_points": _rounded(total - completed),
                "completion_rate": round(completed / total * 100, 2) if total else 0,
                "estimated_items": metric["estimated_items"],
                "unestimated_items": metric["eligible_items"] - metric["estimated_items"],
            }
        )

    completion_rows = _leaf_rows(completion_scope, point_project_ids)
    completion_by_id = {row["id"]: row for row in completion_rows}
    assignees_by_issue = defaultdict(list)
    all_row_ids = completion_by_id.keys() | rows_by_id.keys()
    for assignee in IssueAssignee.objects.filter(issue_id__in=all_row_ids, deleted_at__isnull=True).values(
        "issue_id",
        "assignee_id",
        "assignee__display_name",
        "assignee__first_name",
        "assignee__last_name",
        "assignee__avatar",
    ):
        assignees_by_issue[assignee["issue_id"]].append(assignee)

    member_metrics = defaultdict(
        lambda: {
            "assigned_points": 0.0,
            "completed_points": 0.0,
            "remaining_points": 0.0,
            "estimated_items": 0,
            "unestimated_items": 0,
        }
    )
    member_identities = {}
    for row in rows:
        assignees = assignees_by_issue[row["id"]] or [
            {
                "assignee_id": None,
                "assignee__display_name": "Unassigned",
                "assignee__first_name": "",
                "assignee__last_name": "",
            }
        ]
        share = row["estimate_value"] / len(assignees) if row["estimate_value"] is not None else None
        for assignee in assignees:
            key = assignee["assignee_id"] or "unassigned"
            member_identities[key] = assignee
            metric = member_metrics[key]
            if share is None:
                metric["unestimated_items"] += 1
                continue
            metric["assigned_points"] += share
            metric["estimated_items"] += 1
            if row["state__group"] == "completed":
                metric["completed_points"] += share
            else:
                metric["remaining_points"] += share

    members = []
    for key, metric in member_metrics.items():
        identity = member_identities[key]
        members.append(
            {
                **{field: identity[field] for field in identity if field.startswith("assignee")},
                **{field: _rounded(value) if field.endswith("_points") else value for field, value in metric.items()},
                "allocation": "equal_share",
            }
        )
    members.sort(key=lambda row: (-row["assigned_points"], row["assignee__display_name"] or ""))

    # A leaderboard groups only projects with the same configured point scale.
    # Its denominator is current allocated work in the filtered scope; credit is
    # given only for items currently completed in the selected completion window.
    scale_projects = defaultdict(list)
    for project in point_projects:
        scale_projects[tuple(sorted(values_by_estimate[project["estimate_id"]]))].append(project)
    leaderboard = []
    for scale, grouped_projects in scale_projects.items():
        project_ids = {project["id"] for project in grouped_projects}
        metrics = defaultdict(
            lambda: {"assigned_points": 0.0, "completed_points": 0.0, "completed_items": 0, "work_items": []}
        )
        identities = {}
        for row in completion_rows:
            if row["project_id"] not in project_ids:
                continue
            if count_mode == "top_level" and row["parent_id"] is not None:
                continue
            value = _number(row["estimate_point__value"])
            if value is None:
                continue
            credited = (
                row["state__group"] == "completed"
                and row["completed_at"] is not None
                and range_start <= timezone.localtime(row["completed_at"]).date() <= range_end
            )
            assignees = assignees_by_issue[row["id"]] or [{
                "assignee_id": None,
                "assignee__display_name": "Unassigned",
                "assignee__first_name": "",
                "assignee__last_name": "",
                "assignee__avatar": None,
            }]
            share = value / len(assignees)
            for assignee in assignees:
                key = assignee["assignee_id"] or "unassigned"
                identities[key] = assignee
                metric = metrics[key]
                metric["assigned_points"] += share
                if credited:
                    metric["completed_points"] += share
                    metric["completed_items"] += 1
                    metric["work_items"].append({
                        "id": row["id"],
                        "project_id": row["project_id"],
                        "identifier": f'{row["project__identifier"]}-{row["sequence_id"]}',
                        "name": row["name"],
                        "allocated_points": _rounded(share),
                        "completed_at": row["completed_at"],
                    })
        ranking = []
        for key, metric in metrics.items():
            identity = identities[key]
            assigned = metric["assigned_points"]
            completed = metric["completed_points"]
            ranking.append({
                "assignee_id": identity["assignee_id"],
                "assignee__display_name": identity["assignee__display_name"],
                "assignee__first_name": identity["assignee__first_name"],
                "assignee__last_name": identity["assignee__last_name"],
                "assignee__avatar": identity["assignee__avatar"],
                "assigned_points": _rounded(assigned),
                "completed_points": _rounded(completed),
                "remaining_points": _rounded(max(assigned - completed, 0)),
                "completion_rate": round(completed / assigned * 100, 2) if assigned else None,
                "completed_items": metric["completed_items"],
                "work_items": metric["work_items"],
            })
        ranking.sort(
            key=lambda item: (
                item["assignee_id"] is None,
                -item["completed_points"],
                item["assignee__display_name"] or "",
            )
        )
        previous_points = None
        rank = 0
        position = 0
        for member in ranking:
            member["rank"] = None
            if not member["assignee_id"] or member["completed_points"] <= 0:
                continue
            position += 1
            if member["completed_points"] != previous_points:
                rank = position
            member["rank"] = rank
            previous_points = member["completed_points"]
        leaderboard.append({
            "key": ",".join(str(project["id"]) for project in grouped_projects),
            "projects": [project["name"] for project in grouped_projects],
            "scale": list(scale),
            "members": ranking,
        })

    selected_cycles = list(
        cycles.order_by("-created_at")[:100].values(
            "id", "name", "project_id", "project__name", "start_date", "end_date"
        )
    )
    cycle_ids = [cycle["id"] for cycle in selected_cycles]
    cycle_issue_ids = defaultdict(set)
    if cycle_ids and rows_by_id:
        from plane.db.models import CycleIssue

        for relation in CycleIssue.objects.filter(
            cycle_id__in=cycle_ids, issue_id__in=rows_by_id, deleted_at__isnull=True
        ).values("cycle_id", "issue_id"):
            cycle_issue_ids[relation["cycle_id"]].add(relation["issue_id"])

    cycle_rows = []
    for cycle in selected_cycles:
        cycle_scope = [rows_by_id[issue_id] for issue_id in cycle_issue_ids[cycle["id"]]]
        estimated = [row for row in cycle_scope if row["estimate_value"] is not None]
        total = sum(row["estimate_value"] for row in estimated)
        completed = sum(row["estimate_value"] for row in estimated if row["state__group"] == "completed")
        cycle_rows.append(
            {
                **cycle,
                "current_scope_points": _rounded(total),
                "completed_points": _rounded(completed),
                "remaining_points": _rounded(total - completed),
                "completion_rate": round(completed / total * 100, 2) if total else 0,
                "unestimated_items": len(cycle_scope) - len(estimated),
                "velocity_points": _rounded(completed),
            }
        )

    trend_points = defaultdict(float)
    for row in completion_rows:
        value = _number(row["estimate_point__value"])
        completed_at = row["completed_at"]
        if value is not None and row["state__group"] == "completed" and completed_at:
            completed_day = completed_at.date()
            if range_start <= completed_day <= range_end:
                trend_points[completed_day] += value
    completion_trend = [
        {
            "date": (range_start + timedelta(days=offset)).isoformat(),
            "completed_points": _rounded(trend_points[range_start + timedelta(days=offset)]),
        }
        for offset in range((range_end - range_start).days + 1)
    ]

    return {
        "configuration": {
            "points_projects": len(point_projects),
            "incompatible_projects": incompatible_projects,
            "is_available": bool(point_projects),
        },
        "summary": {
            "total_estimated_points": _rounded(total_points),
            "completed_points": _rounded(completed_points),
            "remaining_points": _rounded(total_points - completed_points),
            "in_progress_points": _rounded(in_progress_points),
            "completion_rate": round(completed_points / total_points * 100, 2) if total_points else 0,
            "coverage": round(estimated_count / eligible_count * 100, 2) if eligible_count else 0,
            "eligible_items": eligible_count,
            "estimated_items": estimated_count,
            "unestimated_items": unestimated_count,
            "average_points": _rounded(total_points / estimated_count) if estimated_count else 0,
        },
        "progress": [
            {"group": group, "points": _rounded(state_points[group])}
            for group in ("completed", "started", "unstarted", "backlog")
        ],
        "distribution": distribution,
        "by_type": [
            {
                "type_id": key[0],
                "type_name": key[1],
                "points": _rounded(metric["points"]),
                "estimated_items": metric["estimated_items"],
                "unestimated_items": metric["unestimated_items"],
            }
            for key, metric in sorted(type_points.items(), key=lambda item: item[0][1])
        ],
        "members": members,
        "leaderboard": leaderboard,
        "projects": project_rows,
        "cycles": cycle_rows,
        "completion_trend": completion_trend,
    }
