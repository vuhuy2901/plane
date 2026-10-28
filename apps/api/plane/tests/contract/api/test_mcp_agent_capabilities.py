"""Real PAT coverage for the API routes exposed by the expanded MCP tools."""

import pytest
from rest_framework.test import APIClient

from plane.db.models import Issue, Project, ProjectMember, State


@pytest.mark.contract
@pytest.mark.django_db
def test_pat_report_has_estimates_and_only_accessible_projects(api_key_client, workspace, create_user):
    visible = Project.objects.create(name="Visible", identifier="VIS", workspace=workspace)
    hidden = Project.objects.create(name="Hidden", identifier="HID", workspace=workspace)
    ProjectMember.objects.create(project=visible, workspace=workspace, member=create_user, role=20)
    for project in (visible, hidden):
        state = State.objects.create(name="Todo", group="unstarted", project=project, workspace=workspace)
        Issue.objects.create(name="Item", project=project, workspace=workspace, state=state)
    url = f"/api/v1/workspaces/{workspace.slug}/analytics-report/"
    response = api_key_client.get(url)
    assert response.status_code == 200, response.data
    assert response.data["totals"]["total"] == 1
    assert "estimates" in response.data
    assert [str(row["id"]) for row in response.data["projects"]] == [str(visible.id)]
    assert APIClient().get(url).status_code in (401, 403)
    assert api_key_client.get(url, {"date_from": "bad", "date_to": "bad"}).status_code == 400


@pytest.mark.contract
@pytest.mark.django_db
def test_pat_delete_respects_project_role(api_key_client, workspace, create_user, mocker):
    mocker.patch("plane.api.views.issue.issue_activity.delay")
    project = Project.objects.create(name="Delete test", identifier="DEL", workspace=workspace)
    membership = ProjectMember.objects.create(project=project, workspace=workspace, member=create_user, role=15)
    state = State.objects.create(name="Todo", group="unstarted", project=project, workspace=workspace)
    issue = Issue.objects.create(name="Test deletion only", project=project, workspace=workspace, state=state)
    url = f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/{issue.id}/"
    assert api_key_client.delete(url).status_code == 403
    assert Issue.objects.filter(id=issue.id).exists()
    membership.role = 20
    membership.save(update_fields=["role"])
    response = api_key_client.delete(url)
    assert response.status_code == 204, response.data
    assert not Issue.issue_objects.filter(id=issue.id).exists()
