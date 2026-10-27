import pytest

from plane.db.models import (
    Issue,
    IssueType,
    ProjectIssueType,
    State,
    Workflow,
    WorkflowIssueTypeMapping,
    WorkflowVersion,
    WorkflowVersionState,
    WorkflowStateLayout,
    IssueImportMetadata,
)
from plane.tests.factories import ProjectFactory, ProjectMemberFactory


@pytest.fixture
def assignment(workspace, create_user, monkeypatch):
    monkeypatch.setattr("celery.app.task.Task.delay", lambda *args, **kwargs: None)
    project = ProjectFactory(workspace=workspace, identifier="WT")
    ProjectMemberFactory(project=project, member=create_user, role=20)
    state = State.objects.create(project=project, name="To Do", group="unstarted", color="#3E63DD")
    original = IssueType.objects.create(workspace=workspace, name="Jira Task")
    custom = IssueType.objects.create(workspace=workspace, name="Custom task", color="#DC2626")
    for kind in [original, custom]:
        ProjectIssueType.objects.create(project=project, issue_type=kind)
    issue = Issue.objects.create(project=project, name="Imported task", state=state, type=original)
    IssueImportMetadata.objects.create(
        project=project,
        issue=issue,
        source_issue_id="123",
        source_issue_key="JIRA-1",
        file_sha256="a" * 64,
        source_timezone="Asia/Bangkok",
        fields=[{"name": "Issue Type", "value": "Task", "column_index": 0}],
    )
    workflow = Workflow.objects.create(project=project, name="Custom workflow")
    version = WorkflowVersion.objects.create(project=project, workflow=workflow, version=1, status="published")
    node = WorkflowVersionState.objects.create(
        project=project,
        workflow_version=version,
        state=state,
        name=state.name,
        group=state.group,
        color=state.color,
        is_start=True,
        is_end=True,
    )
    WorkflowStateLayout.objects.create(project=project, workflow_state=node)
    workflow.active_version = version
    workflow.save(update_fields=["active_version"])
    WorkflowIssueTypeMapping.objects.create(project=project, issue_type=custom, workflow=workflow)
    base = f"/api/workspaces/{workspace.slug}/projects/{project.id}"
    return project, issue, original, custom, workflow, base


def find_issue(value, issue_id):
    if isinstance(value, dict):
        if value.get("id") == str(issue_id):
            return value
        for child in value.values():
            found = find_issue(child, issue_id)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_issue(child, issue_id)
            if found:
                return found
    return None


@pytest.mark.contract
@pytest.mark.django_db
class TestWorkTypeAssignment:
    @pytest.mark.parametrize(
        "path",
        [
            "issues/",
            "issues/?group_by=state_id",
            "v2/issues/",
            "issues/list/?issues={id}",
            "issues/{id}/",
            "issues-detail/",
        ],
    )
    @pytest.mark.parametrize("kind", ["Bug", "Epic", "Task", "Sub-task"])
    def test_read_paths_keep_the_assigned_type(self, session_client, assignment, path, kind):
        _, issue, original, _, _, base = assignment
        original.name = kind
        original.save(update_fields=["name"])
        response = session_client.get(f"{base}/{path.format(id=issue.id)}")
        assert response.status_code == 200, response.data
        item = find_issue(response.json(), issue.id)
        assert item is not None, response.data
        assert item["type_id"] == str(original.id)

    @pytest.mark.parametrize("kind", ["Bug", "Epic", "Task", "Sub-task"])
    def test_expanded_child_tasks_keep_their_own_type(self, session_client, assignment, kind):
        project, parent, original, _, _, base = assignment
        original.name = kind
        original.save(update_fields=["name"])
        child = Issue.objects.create(
            project=project, parent=parent, name="Child item", type=original, state=parent.state
        )
        response = session_client.get(f"{base}/issues/{parent.id}/sub-issues/")
        assert response.status_code == 200, response.data
        item = find_issue(response.json(), child.id)
        assert item is not None, response.data
        assert item["type_id"] == str(original.id)

    def test_custom_type_assignment_persists_and_uses_its_workflow(self, session_client, assignment):
        _, issue, _, custom, workflow, base = assignment
        before = issue.import_metadata.fields
        response = session_client.patch(f"{base}/issues/{issue.id}/", {"type_id": str(custom.id)}, format="json")
        assert response.status_code == 204, response.data
        issue.refresh_from_db()
        assert issue.type_id == custom.id
        assert issue.import_metadata.fields == before
        assert session_client.get(f"{base}/issues/{issue.id}/").json()["type_id"] == str(custom.id)
        preview = session_client.get(f"{base}/work-items/{issue.id}/workflow/").json()
        assert preview["workflow"]["id"] == str(workflow.id)

    def test_new_task_uses_the_selected_custom_type(self, session_client, assignment):
        _, issue, _, custom, _, base = assignment
        response = session_client.post(
            f"{base}/issues/", {"name": "Created task", "type_id": str(custom.id)}, format="json"
        )
        assert response.status_code == 201, response.data
        created = Issue.objects.get(pk=response.json()["id"])
        assert created.type_id == custom.id
        assert created.state_id == issue.state_id
        assert response.json()["type_id"] == str(custom.id)

    def test_foreign_project_type_is_rejected(self, session_client, workspace, assignment):
        _, issue, original, _, _, base = assignment
        foreign = IssueType.objects.create(workspace=workspace, name="Other project type")
        response = session_client.patch(f"{base}/issues/{issue.id}/", {"type_id": str(foreign.id)}, format="json")
        assert response.status_code == 400
        issue.refresh_from_db()
        assert issue.type_id == original.id
