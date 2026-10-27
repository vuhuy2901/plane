import pytest

from plane.db.models import IssueType
from plane.tests.factories import ProjectFactory, ProjectMemberFactory


@pytest.fixture
def type_url(workspace, create_user):
    project = ProjectFactory(workspace=workspace, identifier="TC")
    ProjectMemberFactory(project=project, member=create_user, role=20)
    return f"/api/workspaces/{workspace.slug}/projects/{project.id}/workflow-issue-types/"


@pytest.mark.contract
@pytest.mark.django_db
class TestWorkTypeColors:
    @pytest.mark.parametrize("name", ["EPIC", "Task", "Bug", "Sub-task"])
    def test_color_change_allows_an_unchanged_name_with_legacy_duplicates(
        self, session_client, type_url, workspace, name
    ):
        created = session_client.post(type_url, {"name": name, "color": "#3E63DD"}, format="json")
        assert created.status_code == 201, created.data
        duplicate = IssueType.objects.create(workspace=workspace, name=name.swapcase(), color="#DC2626")
        response = session_client.patch(
            f"{type_url}{created.json()['id']}/", {"name": name, "color": "#059669"}, format="json"
        )
        assert response.status_code == 200, response.data
        assert response.json()["name"] == name
        assert response.json()["color"] == "#059669"
        assert IssueType.objects.get(pk=created.json()["id"]).color == "#059669"
        duplicate.refresh_from_db()
        assert duplicate.name == name.swapcase()
        assert duplicate.color == "#DC2626"

    def test_renaming_to_another_existing_type_is_still_rejected(self, session_client, type_url):
        created = session_client.post(type_url, {"name": "Bug", "color": "#DC2626"}, format="json").json()
        assert session_client.post(type_url, {"name": "Task"}, format="json").status_code == 201
        response = session_client.patch(
            f"{type_url}{created['id']}/", {"name": "Task", "color": "#059669"}, format="json"
        )
        assert response.status_code == 400
        issue_type = IssueType.objects.get(pk=created["id"])
        assert issue_type.name == "Bug"
        assert issue_type.color == "#DC2626"

    def test_color_is_saved_returned_and_can_be_changed(self, session_client, type_url):
        created = session_client.post(type_url, {"name": "Bug", "color": "#dc2626"}, format="json")
        assert created.status_code == 201, created.data
        data = created.json()
        assert data["color"] == "#DC2626"
        assert session_client.get(type_url).json()[0]["color"] == "#DC2626"
        updated = session_client.patch(f"{type_url}{data['id']}/", {"name": "Bug", "color": "#059669"}, format="json")
        assert updated.status_code == 200, updated.data
        assert updated.json()["color"] == "#059669"
        assert IssueType.objects.get(pk=data["id"]).color == "#059669"
        renamed = session_client.patch(f"{type_url}{data['id']}/", {"name": "Defect"}, format="json")
        assert renamed.status_code == 200
        assert renamed.json()["color"] == "#059669"

    @pytest.mark.parametrize("color", [None, "red", "#123", "#gggggg", "url(bad)", "#12345678"])
    def test_invalid_colors_are_rejected_without_changing_existing_type(self, session_client, type_url, color):
        created = session_client.post(type_url, {"name": "Task", "color": "#3E63DD"}, format="json").json()
        response = session_client.patch(
            f"{type_url}{created['id']}/", {"name": "Changed", "color": color}, format="json"
        )
        assert response.status_code == 400
        item = IssueType.objects.get(pk=created["id"])
        assert item.name == "Task"
        assert item.color == "#3E63DD"
        assert session_client.post(type_url, {"name": "Bad", "color": color}, format="json").status_code == 400

    def test_older_clients_can_still_create_types_without_a_color(self, session_client, type_url):
        response = session_client.post(type_url, {"name": "Task"}, format="json")
        assert response.status_code == 201
        assert response.json()["color"] == "#3E63DD"
