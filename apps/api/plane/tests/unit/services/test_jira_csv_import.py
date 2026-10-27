import csv
from copy import deepcopy
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from plane.db.models import (
    Cycle,
    CycleIssue,
    Issue,
    IssueType,
    IssueImportMetadata,
    IssueRelation,
    IssueSequence,
    Project,
    ProjectIssueType,
    ProjectMember,
    Workflow,
    WorkflowVersion,
    WorkflowVersionState,
    WorkflowIssueTypeMapping,
)
from plane.services.jira_csv_import import import_jira_csv, read_jira_csv, verify_jira_csv_import
from plane.tests.factories import UserFactory, WorkspaceFactory, WorkspaceMemberFactory


@pytest.fixture
def source_csv(tmp_path):
    headers = [
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
        "Labels",
        "Labels",
        "Inward issue link (Blocks)",
        "Outward issue link (Blocks)",
        "Custom field (Bug area)",
    ]
    records = []
    for number, kind, parent in [(1, "Epic", ""), (2, "Task", "1"), (4, "Subtask", "2"), (9, "Bug", "1")]:
        records.append(
            [
                f"Công việc {number}",
                f"TST-{number}",
                str(number),
                kind,
                "Done" if kind == "Bug" else "To Do",
                "Done" if kind == "Bug" else "To Do",
                "TST",
                "CSV import",
                "Medium",
                "Tiếng Việt, dấu phẩy\n<script>unsafe</script>",
                "15/Oct/26 12:26 AM",
                "16/Oct/26 1:14 PM",
                "16/Oct/26 1:00 PM" if kind == "Bug" else "",
                "08/Jan/27 12:00 AM",
                "04/Jan/27 12:00 AM",
                parent,
                f"TST-{parent}" if parent else "",
                "Sprint 1" if kind != "Epic" else "",
                "one",
                "two",
                "TST-9" if number == 1 else "",
                "TST-1" if kind == "Bug" else "",
                "Backend" if kind == "Bug" else "",
            ]
        )
    path = tmp_path / "jira.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(records)
    return path


@pytest.fixture
def target(monkeypatch):
    monkeypatch.setattr("celery.app.task.Task.delay", lambda *args, **kwargs: None)
    actor = UserFactory()
    workspace = WorkspaceFactory(owner=actor)
    WorkspaceMemberFactory(workspace=workspace, member=actor, role=20)
    return workspace, actor


@pytest.mark.unit
@pytest.mark.django_db
class TestJiraCSVImport:
    def test_new_import_exposes_every_work_type_through_entity_read_apis(self, source_csv, target):
        workspace, actor = target
        result = import_jira_csv(read_jira_csv(source_csv), workspace.slug, actor.id, apply=True)
        project = Project.objects.get(pk=result["project_id"])
        client = APIClient()
        client.force_authenticate(actor)
        base = f"/api/workspaces/{workspace.slug}/projects/{project.id}"
        response = client.get(f"{base}/issues-detail/")
        assert response.status_code == 200
        rows = response.json()["results"]
        expected = {str(issue.id): str(issue.type_id) for issue in Issue.objects.filter(project=project)}
        assert len(rows) == 4
        assert {row["id"]: row["type_id"] for row in rows} == expected
        types = client.get(f"{base}/workflow-issue-types/").json()
        assert {item["id"] for item in types} == set(expected.values())
        assert len({item["color"] for item in types}) == 4
        for issue in Issue.objects.filter(project=project):
            detail = client.get(f"{base}/issues/{issue.id}/")
            assert detail.status_code == 200
            assert detail.json()["type_id"] == str(issue.type_id)

    def test_reimport_keeps_user_work_type_assignment_and_workflow_mapping(self, source_csv, target):
        workspace, actor = target
        data = read_jira_csv(source_csv)
        result = import_jira_csv(data, workspace.slug, actor.id, apply=True)
        project = Project.objects.get(pk=result["project_id"])
        issue = Issue.objects.filter(project=project, type__name="Task").first()
        custom = IssueType.objects.create(workspace=workspace, name="Custom task", color="#D97706")
        ProjectIssueType.objects.create(project=project, issue_type=custom)
        workflow = Workflow.objects.create(project=project, name="Custom task workflow")
        version = WorkflowVersion.objects.create(project=project, workflow=workflow, version=1, status="published")
        WorkflowVersionState.objects.create(
            project=project,
            workflow_version=version,
            state=issue.state,
            name=issue.state.name,
            group=issue.state.group,
            color=issue.state.color,
            is_start=True,
            is_end=True,
        )
        workflow.active_version = version
        workflow.save(update_fields=["active_version"])
        mapping = WorkflowIssueTypeMapping.objects.create(project=project, issue_type=custom, workflow=workflow)
        client = APIClient()
        client.force_authenticate(actor)
        response = client.patch(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{issue.id}/",
            {"type_id": str(custom.id)},
            format="json",
        )
        assert response.status_code == 204, response.data
        before = (issue.state_id, issue.import_metadata.fields)
        rerun = import_jira_csv(data, workspace.slug, actor.id, apply=True)
        assert rerun["status"] == "already_imported"
        assert Issue.objects.filter(project=project).count() == 4
        issue.refresh_from_db()
        assert issue.type_id == custom.id
        assert (issue.state_id, issue.import_metadata.fields) == before
        assert WorkflowIssueTypeMapping.objects.get(pk=mapping.pk).workflow_id == workflow.id

    def test_import_reuses_existing_type_identity_and_custom_color(self, source_csv, target):
        workspace, actor = target
        existing = IssueType.objects.create(workspace=workspace, name="EPIC", color="#123456")
        result = import_jira_csv(read_jira_csv(source_csv), workspace.slug, actor.id, apply=True)
        issue = Issue.objects.get(project_id=result["project_id"], external_id="1")
        assert issue.type_id == existing.id
        assert issue.type.color == "#123456"
        assert IssueType.objects.filter(workspace=workspace, name__iexact="Epic").count() == 1

    def test_dry_run_and_apply_preserve_source_and_rerun_is_noop(self, source_csv, target):
        workspace, actor = target
        data = read_jira_csv(source_csv)
        initial = Project.objects.count()
        assert import_jira_csv(data, workspace.slug, actor.id)["status"] == "dry_run"
        assert Project.objects.count() == initial
        result = import_jira_csv(data, workspace.slug, actor.id, apply=True)
        project = Project.objects.get(pk=result["project_id"])
        assert Issue.objects.filter(project=project).count() == 4
        assert IssueSequence.objects.filter(project=project).order_by("-sequence").first().sequence == 9
        assert list(
            ProjectIssueType.objects.filter(project=project).order_by("level").values_list("level", flat=True)
        ) == [0, 1, 1, 2]
        for row in data["rows"]:
            issue = Issue.objects.get(project=project, external_id=row["Issue id"])
            assert issue.sequence_id == row["_number"]
            assert issue.created_at == row["_dates"]["Created"]
            assert issue.updated_at == row["_dates"]["Updated"]
            assert issue.completed_at == row["_dates"]["Resolved"]
            assert issue.import_metadata.fields == row["_raw"]
            assert set(issue.labels.values_list("name", flat=True)) == {"one", "two"}
            assert not issue.assignees.exists()
            assert "&lt;script&gt;" in issue.description_html
        assert Issue.objects.filter(project=project, parent__isnull=False).count() == 3
        relation = IssueRelation.objects.get(project=project)
        assert (relation.issue.external_id, relation.related_issue.external_id) == ("1", "9")
        assert Cycle.objects.filter(project=project, start_date__isnull=True, end_date__isnull=True).count() == 1
        assert CycleIssue.objects.filter(project=project).count() == 3
        assert verify_jira_csv_import(data, project)["verified_source_cells"] == 4 * 23
        assert import_jira_csv(data, workspace.slug, actor.id, apply=True)["status"] == "already_imported"
        assert IssueImportMetadata.objects.filter(project=project).count() == 4
        next_issue = Issue.objects.create(project=project, name="Next")
        assert next_issue.sequence_id == 10
        changed = deepcopy(data)
        changed["sha256"] = "0" * 64
        with pytest.raises(ValueError, match="different data"):
            import_jira_csv(changed, workspace.slug, actor.id, apply=True)

    def test_failure_rolls_back_new_project_and_related_records(self, source_csv, target):
        workspace, actor = target
        data = read_jira_csv(source_csv)
        counts = (Project.objects.count(), Issue.objects.count(), ProjectIssueType.objects.count())
        with patch.object(IssueImportMetadata.objects, "create", side_effect=RuntimeError("fail midway")):
            with pytest.raises(RuntimeError, match="fail midway"):
                import_jira_csv(data, workspace.slug, actor.id, apply=True)
        assert counts == (Project.objects.count(), Issue.objects.count(), ProjectIssueType.objects.count())

    def test_metadata_endpoint_is_scoped_to_project_members_and_issue(self, source_csv, target):
        workspace, actor = target
        result = import_jira_csv(read_jira_csv(source_csv), workspace.slug, actor.id, apply=True)
        issue = Issue.objects.filter(project_id=result["project_id"]).first()
        url = f"/api/workspaces/{workspace.slug}/projects/{issue.project_id}/issues/{issue.id}/import-metadata/"
        client = APIClient()
        client.force_authenticate(actor)
        assert client.get(url).status_code == 200
        assert client.get(url).data["fields"] == issue.import_metadata.fields
        stranger = UserFactory()
        WorkspaceMemberFactory(workspace=workspace, member=stranger)
        client.force_authenticate(stranger)
        assert client.get(url).status_code == 403
        ProjectMember.objects.create(project=issue.project, member=stranger, role=5)
        assert client.get(url).status_code == 200


@pytest.mark.unit
def test_duplicate_keys_missing_parent_and_invalid_dates_are_rejected(source_csv):
    with source_csv.open(encoding="utf-8-sig", newline="") as stream:
        original = list(csv.reader(stream))
    for column, value, message in [
        (1, "TST-1", "Duplicate"),
        (16, "TST-999", "parent"),
        (10, "bad-date", "invalid date"),
    ]:
        data = deepcopy(original)
        data[2][column] = value
        with source_csv.open("w", encoding="utf-8-sig", newline="") as stream:
            csv.writer(stream).writerows(data)
        with pytest.raises(ValueError, match=message):
            read_jira_csv(source_csv)
