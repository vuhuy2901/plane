import pytest
from rest_framework import status

from plane.db.models import (
    Issue,
    IssueType,
    ProjectIssueType,
    State,
    Workflow,
    WorkflowIssueTypeMapping,
    WorkflowTransition,
    WorkflowTransitionAudit,
    WorkflowVersion,
    WorkflowVersionState,
)
from plane.tests.factories import ProjectFactory, ProjectMemberFactory


@pytest.fixture
def workflow_issue(workspace, create_user):
    project = ProjectFactory(workspace=workspace, identifier="WF")
    ProjectMemberFactory(project=project, member=create_user, role=20)
    issue_type = IssueType.objects.create(workspace=workspace, name="Task")
    ProjectIssueType.objects.create(project=project, issue_type=issue_type, is_default=True)
    source = State.objects.create(project=project, name="Open", color="#000000", group="unstarted")
    forbidden = State.objects.create(project=project, name="Forbidden", color="#ffffff", group="completed")
    workflow = Workflow.objects.create(project=project, name="Strict")
    version = WorkflowVersion.objects.create(
        project=project,
        workflow=workflow,
        version=1,
        status=WorkflowVersion.Status.PUBLISHED,
    )
    WorkflowVersionState.objects.create(
        project=project,
        workflow_version=version,
        state=source,
        name=source.name,
        color=source.color,
        group=source.group,
        is_start=True,
    )
    WorkflowVersionState.objects.create(
        project=project,
        workflow_version=version,
        state=forbidden,
        name=forbidden.name,
        color=forbidden.color,
        group=forbidden.group,
        is_end=True,
    )
    workflow.active_version = version
    workflow.save(update_fields=["active_version"])
    WorkflowIssueTypeMapping.objects.create(project=project, issue_type=issue_type, workflow=workflow)
    issue = Issue.objects.create(project=project, type=issue_type, state=source, name="Cannot bypass")
    return project, issue, source, forbidden


@pytest.mark.contract
@pytest.mark.django_db
class TestWorkflowTransitionBypass:
    @pytest.mark.parametrize("token", [False, True])
    def test_changing_type_in_the_same_patch_cannot_skip_the_current_graph(
        self, session_client, api_key_client, workspace, workflow_issue, token
    ):
        project, issue, source, forbidden = workflow_issue
        other_type = IssueType.objects.create(workspace=workspace, name="Unmapped bug")
        ProjectIssueType.objects.create(project=project, issue_type=other_type)
        client = api_key_client if token else session_client
        url = (
            f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/{issue.id}/"
            if token
            else f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{issue.id}/"
        )
        data = (
            {"state": str(forbidden.id), "type": str(other_type.id)}
            if token
            else {"state_id": str(forbidden.id), "type_id": str(other_type.id)}
        )
        response = client.patch(url, data, format="json")
        assert response.status_code == 400, response.data
        issue.refresh_from_db()
        assert issue.state_id == source.id
        assert issue.type_id != other_type.id

    def test_published_forward_and_return_edges_are_the_only_available_choices(
        self, session_client, workspace, workflow_issue
    ):
        project, issue, source, done = workflow_issue
        version = WorkflowVersion.objects.get(project=project)
        ready = State.objects.create(project=project, name="Ready for Acceptance", color="#123456", group="started")
        ready_node = WorkflowVersionState.objects.create(
            project=project, workflow_version=version, state=ready, name=ready.name, group="started"
        )
        source_node = version.states.get(state=source)
        done_node = version.states.get(state=done)
        forward = WorkflowTransition.objects.create(
            project=project, workflow_version=version, source=source_node, target=ready_node, name="Review"
        )
        back = WorkflowTransition.objects.create(
            project=project, workflow_version=version, source=ready_node, target=source_node, name="Request changes"
        )
        accept = WorkflowTransition.objects.create(
            project=project, workflow_version=version, source=ready_node, target=done_node, name="Accept"
        )
        base = f"/api/workspaces/{workspace.slug}/projects/{project.id}"
        choices_url = f"{base}/work-items/{issue.id}/workflow-transitions/"
        update_url = f"{base}/issues/{issue.id}/"
        assert {edge["id"] for edge in session_client.get(choices_url).json()["transitions"]} == {str(forward.id)}
        assert session_client.patch(update_url, {"state_id": str(ready.id)}, format="json").status_code == 204
        assert {edge["id"] for edge in session_client.get(choices_url).json()["transitions"]} == {
            str(back.id),
            str(accept.id),
        }
        assert session_client.patch(update_url, {"state_id": str(source.id)}, format="json").status_code == 204
        assert WorkflowTransitionAudit.objects.filter(issue=issue).count() == 2

    def test_web_api_cannot_patch_an_undeclared_state_change(self, session_client, workspace, workflow_issue):
        project, issue, source, forbidden = workflow_issue
        response = session_client.patch(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{issue.id}/",
            {"state_id": str(forbidden.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST, response.json()
        issue.refresh_from_db()
        assert issue.state_id == source.id

    def test_token_api_cannot_patch_an_undeclared_state_change(self, api_key_client, workspace, workflow_issue):
        project, issue, source, forbidden = workflow_issue
        response = api_key_client.patch(
            f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/{issue.id}/",
            {"state": str(forbidden.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST, response.data
        issue.refresh_from_db()
        assert issue.state_id == source.id
