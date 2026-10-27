from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError

from plane.db.models import (
    Issue,
    IssueActivity,
    IssueType,
    ProjectIssueType,
    State,
    Workflow,
    WorkflowIssueTypeMapping,
    WorkflowVersion,
    WorkflowVersionState,
)
from plane.services.workflow_mapping import preview_workflow_mappings, save_workflow_mappings
from plane.tests.factories import ProjectFactory, ProjectMemberFactory, UserFactory


@pytest.fixture
def scenario():
    actor = UserFactory()
    project = ProjectFactory(workspace__owner=actor)
    kind = IssueType.objects.create(workspace=project.workspace, name="Epic")
    ProjectIssueType.objects.create(project=project, issue_type=kind)
    old = State.objects.create(project=project, name="To Do", color="#60646C", group="unstarted")
    target = State.objects.create(project=project, name="ToDo", color="#60646C", group="started")
    workflow = Workflow.objects.create(project=project, name="Epic workflow")
    version = WorkflowVersion.objects.create(project=project, workflow=workflow, version=1, status="published")
    WorkflowVersionState.objects.create(
        project=project,
        workflow_version=version,
        state=target,
        name=target.name,
        color=target.color,
        group=target.group,
        is_start=True,
    )
    workflow.active_version = version
    workflow.save()
    issue = Issue.objects.create(project=project, type=kind, state=old, name="Imported Jira Epic")
    untouched = Issue.objects.create(project=project, state=old, name="Other type")
    payload = {"mappings": [{"issue_type_id": str(kind.pk), "workflow_id": str(workflow.pk)}]}
    return actor, project, kind, old, target, workflow, version, issue, untouched, payload


def confirm(payload, conflict, target):
    return {
        **payload,
        "state_migrations": [
            {
                "issue_type_id": conflict["issue_type_id"],
                "workflow_version_id": conflict["workflow_version_id"],
                "source_state_id": conflict["source_state_id"],
                "target_state_id": str(target.pk),
                "work_item_count": conflict["work_item_count"],
            }
        ],
    }


@pytest.mark.unit
@pytest.mark.django_db
class TestWorkflowMappingMigration:
    def test_api_preview_then_confirm_and_project_admin_permission(self, scenario):
        actor, project, kind, old, target, workflow, version, issue, untouched, payload = scenario
        ProjectMemberFactory(project=project, member=actor, role=20)
        client = APIClient()
        client.force_authenticate(actor)
        url = f"/api/workspaces/{project.workspace.slug}/projects/{project.pk}/workflows/mappings/"
        preview = client.post(url, payload, format="json")
        assert preview.status_code == 200
        assert preview.data["work_item_count"] == 1
        assert client.put(url, payload, format="json").status_code == 400
        saved = client.put(url, confirm(payload, preview.data["conflicts"][0], target), format="json")
        assert saved.status_code == 200, saved.data
        assert saved.data == payload["mappings"]
        client.force_authenticate(UserFactory())
        assert client.post(url, payload, format="json").status_code == 403

    def test_preview_explains_all_conflicts_without_writing_and_save_requires_choice(self, scenario):
        actor, project, kind, old, target, workflow, version, issue, untouched, payload = scenario
        preview = preview_workflow_mappings(project, payload)
        assert preview["work_item_count"] == 1
        conflict = preview["conflicts"][0]
        assert conflict["source_state_name"] == "To Do"
        assert conflict["suggested_target_id"] is None  # groups differ; do not silently change meaning
        assert conflict["target_states"][0]["id"] == str(target.pk)
        with pytest.raises(ValidationError):
            save_workflow_mappings(project, payload, actor)
        issue.refresh_from_db()
        assert issue.state_id == old.pk
        assert not WorkflowIssueTypeMapping.objects.filter(project=project).exists()
        assert not IssueActivity.objects.filter(project=project).exists()

    def test_explicit_migration_saves_mapping_and_audits_only_affected_type(self, scenario):
        actor, project, kind, old, target, workflow, version, issue, untouched, payload = scenario
        conflict = preview_workflow_mappings(project, payload)["conflicts"][0]
        save_workflow_mappings(project, confirm(payload, conflict, target), actor)
        issue.refresh_from_db()
        untouched.refresh_from_db()
        assert issue.state_id == target.pk
        assert untouched.state_id == old.pk
        assert WorkflowIssueTypeMapping.objects.get(project=project, issue_type=kind).workflow_id == workflow.pk
        audit = IssueActivity.objects.get(issue=issue)
        assert (audit.old_identifier, audit.new_identifier, audit.actor_id) == (old.pk, target.pk, actor.pk)
        assert preview_workflow_mappings(project, payload)["conflicts"] == []
        save_workflow_mappings(project, payload, actor)  # repeat save does not migrate or audit twice
        assert IssueActivity.objects.filter(issue=issue).count() == 1

    def test_failure_rolls_back_states_audit_and_mapping(self, scenario):
        actor, project, kind, old, target, workflow, version, issue, untouched, payload = scenario
        conflict = preview_workflow_mappings(project, payload)["conflicts"][0]
        with patch.object(WorkflowIssueTypeMapping.objects, "create", side_effect=RuntimeError("fail")):
            with pytest.raises(RuntimeError):
                save_workflow_mappings(project, confirm(payload, conflict, target), actor)
        issue.refresh_from_db()
        assert issue.state_id == old.pk
        assert not IssueActivity.objects.filter(project=project).exists()

    def test_rejects_foreign_target_and_stale_counts_and_versions(self, scenario):
        actor, project, kind, old, target, workflow, version, issue, untouched, payload = scenario
        conflict = preview_workflow_mappings(project, payload)["conflicts"][0]
        invalid = confirm(payload, conflict, target)
        invalid["state_migrations"][0]["target_state_id"] = str(uuid4())
        with pytest.raises(ValidationError):
            save_workflow_mappings(project, invalid, actor)
        invalid = confirm(payload, conflict, target)
        invalid["state_migrations"][0]["workflow_version_id"] = str(uuid4())
        with pytest.raises(ValidationError):
            save_workflow_mappings(project, invalid, actor)
        Issue.objects.create(project=project, type=kind, state=old, name="New work item after preview")
        with pytest.raises(ValidationError):
            save_workflow_mappings(project, confirm(payload, conflict, target), actor)
        assert not WorkflowIssueTypeMapping.objects.filter(project=project).exists()

    def test_completed_date_is_preserved_for_completed_to_completed_migration(self, scenario):
        actor, project, kind, old, target, workflow, version, issue, untouched, payload = scenario
        State.objects.filter(pk__in=[old.pk, target.pk]).update(group="completed")
        done_at = timezone.now() - timezone.timedelta(days=15)
        Issue.objects.filter(pk=issue.pk).update(completed_at=done_at)
        conflict = preview_workflow_mappings(project, payload)["conflicts"][0]
        save_workflow_mappings(project, confirm(payload, conflict, target), actor)
        issue.refresh_from_db()
        assert issue.completed_at == done_at

    @pytest.mark.parametrize("mappings", [None, [{}], [{"issue_type_id": "bad", "workflow_id": "bad"}]])
    def test_malformed_requests_are_validation_errors(self, scenario, mappings):
        actor, project, *rest = scenario
        with pytest.raises(ValidationError):
            save_workflow_mappings(project, {"mappings": mappings}, actor)
