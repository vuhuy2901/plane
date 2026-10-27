import pytest

from plane.db.models import (
    Issue,
    Label,
    ProjectAutomationRule,
    ProjectMember,
    WorkspaceMember,
    ProjectAutomationEvent,
    ProjectAutomationExecution,
    IssueType,
    ProjectIssueType,
    State,
)
from plane.tests.factories import ProjectFactory, ProjectMemberFactory


@pytest.fixture
def automation_api(session_client, workspace, create_user):
    project = ProjectFactory(workspace=workspace, identifier="AUTO")
    ProjectMemberFactory(project=project, member=create_user, role=20)
    base = f"/api/workspaces/{workspace.slug}/projects/{project.id}/automations/"
    data = {"name": "Assignment", "trigger": "created", "actions": [{"type": "assign_user", "mode": "project_lead"}]}
    return session_client, project, base, data


@pytest.mark.contract
@pytest.mark.django_db
class TestAutomationRuleAPI:
    def test_crud_duplicate_enable_and_reload(self, automation_api):
        client, project, base, data = automation_api
        created = client.post(base + "rules/", {**data, "enabled": True}, format="json")
        assert created.status_code == 201, created.data
        assert not created.data["enabled"]
        url = base + f"rules/{created.data['id']}/"
        assert client.get(url).data == client.get(base + "rules/").data[0]
        assert client.post(url + "validate/", {}, format="json").data == {"valid": True}
        enabled = client.post(url + "status/", {"enabled": True}, format="json")
        assert enabled.status_code == 200, enabled.data
        assert enabled.data["enabled_at"] is not None
        duplicate = client.post(url + "duplicate/", {}, format="json")
        assert duplicate.status_code == 201
        assert not duplicate.data["enabled"]
        assert duplicate.data["id"] != created.data["id"]
        update = client.put(
            url, {**data, "name": "Edited", "expected_revision": enabled.data["revision"]}, format="json"
        )
        assert update.status_code == 200, update.data
        assert update.data["name"] == "Edited"
        assert not update.data["enabled"]
        assert client.get(url).data["name"] == "Edited"
        assert client.delete(url).status_code == 204
        assert client.get(url).status_code == 404
        assert ProjectAutomationRule.objects.filter(project=project).count() == 1

    def test_project_scope(self, automation_api, workspace, create_user):
        client, _, base, data = automation_api
        rule = client.post(base + "rules/", data, format="json").data
        other = ProjectFactory(workspace=workspace, identifier="OT")
        ProjectMemberFactory(project=other, member=create_user, role=20)
        foreign = f"/api/workspaces/{workspace.slug}/projects/{other.id}/automations/rules/{rule['id']}/"
        for response in [
            client.get(foreign),
            client.delete(foreign),
            client.post(foreign + "status/", {"enabled": True}, format="json"),
        ]:
            assert response.status_code == 404

    def test_cross_project_action_reference_rejected(self, automation_api, workspace):
        client, _, base, data = automation_api
        other = ProjectFactory(workspace=workspace, identifier="OTHER")
        label = Label.objects.create(project=other, name="Bug")
        response = client.post(
            base + "rules/", {**data, "actions": [{"type": "add_label", "label_id": str(label.id)}]}, format="json"
        )
        assert response.status_code == 400
        assert not ProjectAutomationRule.objects.exists()

    def test_non_admin_cannot_manage_rules(self, automation_api, create_user):
        client, project, base, data = automation_api
        ProjectMember.objects.filter(project=project, member=create_user).update(role=15)
        WorkspaceMember.objects.filter(workspace=project.workspace, member=create_user).update(role=15)
        assert client.post(base + "rules/", data, format="json").status_code == 403

    def test_six_templates_and_invalid_configuration(self, automation_api):
        client, _, base, data = automation_api
        templates = client.get(base + "templates/")
        assert templates.status_code == 200
        assert len(templates.data) == 7
        assert client.post(base + "rules/", {**data, "trigger": "webhook"}, format="json").status_code == 400

    def test_stale_update_and_invalid_status_preserve_rule(self, automation_api):
        client, _, base, data = automation_api
        created = client.post(base + "rules/", data, format="json").data
        url = base + f"rules/{created['id']}/"
        assert client.put(url, {**data, "expected_revision": 42}, format="json").status_code == 409
        assert client.post(url + "status/", {"enabled": "true"}, format="json").status_code == 400
        assert client.get(url).data["revision"] == 0

    def test_rule_creation_does_not_touch_old_items(self, automation_api):
        client, project, base, data = automation_api
        issue = Issue.objects.create(project=project, name="Existing task")
        before = list(Issue.objects.filter(pk=issue.id).values())
        client.post(base + "rules/", data, format="json")
        assert list(Issue.objects.filter(pk=issue.id).values()) == before

    def test_resources_and_history_are_project_scoped(self, automation_api):
        client, project, base, _ = automation_api
        assert client.get(base + "resources/").status_code == 200
        assert client.get(base + "history/").data == {"results": [], "has_more": False}
        assert client.get(base + "history/?status=invalid").status_code == 400

    def test_resources_include_only_active_project_types_and_states(self, automation_api, workspace):
        client, project, base, _ = automation_api
        other = ProjectFactory(workspace=workspace, identifier="OTHER")
        task = IssueType.objects.create(workspace=workspace, name="Custom task")
        bug = IssueType.objects.create(workspace=workspace, name="Custom bug")
        inactive = IssueType.objects.create(workspace=workspace, name="Inactive", is_active=False)
        ProjectIssueType.objects.create(project=project, issue_type=task)
        ProjectIssueType.objects.create(project=project, issue_type=inactive)
        ProjectIssueType.objects.create(project=other, issue_type=bug)
        state = State.objects.create(project=project, name="Project A state", color="#123456", group="started")
        State.objects.create(project=other, name="Project B state", color="#123456", group="started")

        response = client.get(base + "resources/")
        assert response.status_code == 200, response.data
        assert {item["id"] for item in response.data["types"]} == {str(task.id)}
        assert {str(item["id"]) for item in response.data["states"]} == {str(state.id)}

    def test_test_rule_is_read_only(self, automation_api):
        client, project, base, data = automation_api
        created = client.post(
            base + "rules/", {**data, "actions": [{"type": "change_priority", "priority": "urgent"}]}, format="json"
        ).data
        issue = Issue.objects.create(project=project, name="Dry run")
        before = list(Issue.objects.filter(pk=issue.pk).values())
        response = client.post(base + f"rules/{created['id']}/test/", {"issue_id": str(issue.id)}, format="json")
        assert response.status_code == 200, response.data
        assert response.data["writes"] == 0
        assert list(Issue.objects.filter(pk=issue.pk).values()) == before
        assert not ProjectAutomationEvent.objects.exists()
        assert not ProjectAutomationExecution.objects.exists()
