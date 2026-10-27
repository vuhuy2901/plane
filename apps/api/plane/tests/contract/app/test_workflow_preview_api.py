import pytest

from plane.db.models import (
    Issue,
    IssueType,
    ProjectIssueType,
    ProjectMember,
    State,
    Workflow,
    WorkflowIssueTypeMapping,
    WorkflowStateLayout,
    WorkflowTransition,
    WorkflowVersion,
    WorkflowVersionState,
)
from plane.tests.factories import ProjectFactory, ProjectMemberFactory


@pytest.fixture
def preview_issue(workspace, create_user):
    project = ProjectFactory(workspace=workspace, identifier="PV")
    ProjectMemberFactory(project=project, member=create_user, role=15)
    issue_type = IssueType.objects.create(workspace=workspace, name="Preview task")
    ProjectIssueType.objects.create(project=project, issue_type=issue_type)
    state = State.objects.create(project=project, name="To Do", color="#3E63DD", group="unstarted")
    issue = Issue.objects.create(project=project, type=issue_type, state=state, name="Preview this workflow")
    workflow = Workflow.objects.create(project=project, name="Task flow")
    version = WorkflowVersion.objects.create(
        project=project, workflow=workflow, version=1, status=WorkflowVersion.Status.PUBLISHED
    )
    workflow.active_version = version
    workflow.save(update_fields=["active_version"])
    WorkflowIssueTypeMapping.objects.create(project=project, issue_type=issue_type, workflow=workflow)
    nodes = []
    for index, name in enumerate(["To Do", "Done"]):
        node = WorkflowVersionState.objects.create(
            project=project,
            workflow_version=version,
            state=state if index == 0 else None,
            name=name,
            color="#3E63DD",
            group="unstarted" if index == 0 else "completed",
            is_start=index == 0,
            is_end=index == 1,
        )
        WorkflowStateLayout.objects.create(project=project, workflow_state=node, position_x=index * 300, position_y=50)
        nodes.append(node)
    WorkflowTransition.objects.create(
        project=project,
        workflow_version=version,
        source=nodes[0],
        target=nodes[1],
        name="Complete",
        permissions={"source_handle": "right", "target_handle": "left", "roles": [20]},
        conditions=[{"field": "private_field", "value": "private value"}],
        post_actions=[{"secret": "private credential"}],
    )
    return issue, workflow, version


def preview_url(workspace, project_id, issue_id):
    return f"/api/workspaces/{workspace.slug}/projects/{project_id}/work-items/{issue_id}/workflow/"


@pytest.mark.contract
@pytest.mark.django_db
class TestWorkflowPreviewAPI:
    def test_member_sees_effective_published_graph_without_private_rules(
        self, session_client, workspace, preview_issue
    ):
        issue, workflow, version = preview_issue
        # A newer draft must never replace the published graph shown on a task.
        WorkflowVersion.objects.create(project=issue.project, workflow=workflow, version=2)
        response = session_client.get(preview_url(workspace, issue.project_id, issue.id))
        assert response.status_code == 200, response.data
        data = response.json()
        assert data["current_state_id"] == str(issue.state_id)
        assert data["workflow"]["id"] == str(workflow.id)
        assert data["workflow"]["version"] == version.version
        assert len(data["workflow"]["states"]) == 2
        assert data["workflow"]["states"][1]["layout"]["position_x"] == 300
        edge = data["workflow"]["transitions"][0]
        assert edge["source_handle"] == "right"
        assert edge["target_handle"] == "left"
        assert set(edge) == {"id", "source_key", "target_key", "source_handle", "target_handle", "name"}
        assert "private credential" not in response.content.decode()

    @pytest.mark.parametrize("untyped", [False, True])
    def test_legacy_items_have_an_explicit_empty_workflow(self, session_client, workspace, preview_issue, untyped):
        issue, workflow, _ = preview_issue
        if untyped:
            Issue.objects.filter(pk=issue.id).update(type=None)
        else:
            workflow.active_version = None
            workflow.save(update_fields=["active_version"])
        response = session_client.get(preview_url(workspace, issue.project_id, issue.id))
        assert response.status_code == 200
        assert response.json() == {"current_state_id": str(issue.state_id), "workflow": None}

    def test_does_not_create_or_change_drafts(self, session_client, workspace, preview_issue):
        issue, workflow, _ = preview_issue
        before = list(workflow.versions.values("id", "status", "revision"))
        response = session_client.get(preview_url(workspace, issue.project_id, issue.id))
        assert response.status_code == 200
        assert list(workflow.versions.values("id", "status", "revision")) == before

    def test_cannot_view_an_issue_through_a_different_project(
        self, session_client, workspace, create_user, preview_issue
    ):
        issue, _, _ = preview_issue
        other = ProjectFactory(workspace=workspace, identifier="OP")
        ProjectMemberFactory(project=other, member=create_user, role=15)
        assert session_client.get(preview_url(workspace, other.id, issue.id)).status_code == 404

    def test_nonmembers_cannot_view_the_graph(self, session_client, workspace, create_user, preview_issue):
        issue, _, _ = preview_issue
        ProjectMember.objects.filter(project=issue.project, member=create_user).update(is_active=False)
        assert session_client.get(preview_url(workspace, issue.project_id, issue.id)).status_code == 403
