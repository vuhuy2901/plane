from uuid import uuid4

import pytest
from rest_framework import status

from plane.db.models import (
    Issue,
    IssueType,
    ProjectIssueType,
    State,
    Workflow,
    WorkflowIssueTypeMapping,
    WorkflowVersion,
)
from plane.tests.factories import ProjectFactory, ProjectMemberFactory


@pytest.fixture
def project(workspace, create_user):
    project = ProjectFactory(workspace=workspace, identifier="WD")
    ProjectMemberFactory(project=project, member=create_user, role=20)
    return project


@pytest.mark.contract
@pytest.mark.django_db
class TestWorkflowDesignerAPI:
    def test_new_project_has_no_custom_workflow(self, project):
        assert not Workflow.objects.filter(project=project).exists()

    def test_user_can_publish_five_states_and_seven_transitions(self, session_client, workspace, project):
        base = f"/api/workspaces/{workspace.slug}/projects/{project.id}/workflows/"
        created = session_client.post(base, {"name": "Release flow"}, format="json")
        assert created.status_code == status.HTTP_201_CREATED, created.json()
        workflow_id = created.json()["id"]

        keys = [str(uuid4()) for _ in range(5)]
        states = [
            {
                "key": key,
                "name": f"User state {index}",
                "color": "#60646C",
                "group": "completed" if index == 3 else "unstarted",
                "is_start": index == 0,
                "is_end": index in {3, 4},
                "layout": {"position_x": index * 180, "position_y": index * 40},
            }
            for index, key in enumerate(keys)
        ]
        pairs = [(0, 1), (0, 2), (1, 2), (2, 3), (2, 4), (4, 2), (3, 1)]
        transitions = [
            {
                "source_key": keys[source],
                "target_key": keys[target],
                "name": f"Move {index}",
                "conditions": [],
                "permissions": {},
                "validators": [],
                "post_actions": [],
            }
            for index, (source, target) in enumerate(pairs)
        ]

        saved = session_client.put(
            f"{base}{workflow_id}/draft/",
            {"states": states, "transitions": transitions},
            format="json",
        )
        assert saved.status_code == status.HTTP_200_OK, saved.json()
        assert len(saved.json()["states"]) == 5
        assert len(saved.json()["transitions"]) == 7

        validated = session_client.post(f"{base}{workflow_id}/validate/", {}, format="json")
        assert validated.status_code == status.HTTP_200_OK, validated.json()
        assert validated.json()["valid"] is True

        published = session_client.post(f"{base}{workflow_id}/publish/", {}, format="json")
        assert published.status_code == status.HTTP_200_OK, published.json()
        assert published.json()["version"]["status"] == "published"
        assert State.objects.filter(project=project, name__startswith="User state").count() == 5

        published_version_id = published.json()["version"]["id"]
        current_draft = session_client.get(f"{base}{workflow_id}/draft/")
        assert current_draft.status_code == status.HTTP_200_OK

        unconfirmed_rollback = session_client.post(
            f"{base}{workflow_id}/versions/{published_version_id}/rollback/", {}, format="json"
        )
        assert unconfirmed_rollback.status_code == status.HTTP_400_BAD_REQUEST

        rollback = session_client.post(
            f"{base}{workflow_id}/versions/{published_version_id}/rollback/",
            {"replace_draft": True},
            format="json",
        )
        assert rollback.status_code == status.HTTP_201_CREATED, rollback.json()
        assert rollback.json()["status"] == "draft"
        assert len(rollback.json()["states"]) == 5
        assert len(rollback.json()["transitions"]) == 7

    def test_workflow_url_cannot_cross_project_scope(self, session_client, workspace, project, create_user):
        other = ProjectFactory(workspace=workspace, identifier="OT")
        ProjectMemberFactory(project=other, member=create_user, role=20)
        workflow = Workflow.objects.create(project=project, name="Private graph")

        response = session_client.get(
            f"/api/workspaces/{workspace.slug}/projects/{other.id}/workflows/{workflow.id}/"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.parametrize("published", [False, True])
    def test_workflow_name_can_be_changed_and_unmapped_workflow_deleted(
        self, session_client, workspace, project, monkeypatch, published
    ):
        monkeypatch.setattr("plane.db.mixins.soft_delete_related_objects.delay", lambda *args, **kwargs: None)
        base = f"/api/workspaces/{workspace.slug}/projects/{project.id}/workflows/"
        workflow = Workflow.objects.create(project=project, name="Old name")
        version = WorkflowVersion.objects.create(
            project=project,
            workflow=workflow,
            version=1,
            status=WorkflowVersion.Status.PUBLISHED if published else WorkflowVersion.Status.DRAFT,
        )
        if published:
            workflow.active_version = version
            workflow.save(update_fields=["active_version"])

        renamed = session_client.patch(f"{base}{workflow.id}/", {"name": "New name"}, format="json")
        assert renamed.status_code == status.HTTP_200_OK, renamed.json()
        assert renamed.json()["name"] == "New name"

        deleted = session_client.delete(f"{base}{workflow.id}/")
        assert deleted.status_code == status.HTTP_204_NO_CONTENT
        assert not Workflow.objects.filter(pk=workflow.id).exists()

    def test_mapped_workflow_cannot_be_deleted(self, session_client, workspace, project):
        workflow = Workflow.objects.create(project=project, name="Mapped")
        issue_type = IssueType.objects.create(workspace=workspace, name="Task")
        WorkflowIssueTypeMapping.objects.create(project=project, workflow=workflow, issue_type=issue_type)
        url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/workflows/{workflow.id}/"

        response = session_client.delete(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert Workflow.objects.filter(pk=workflow.id).exists()

    def test_work_item_type_can_be_renamed_and_deleted(self, session_client, workspace, project, monkeypatch):
        monkeypatch.setattr("plane.db.mixins.soft_delete_related_objects.delay", lambda *args, **kwargs: None)
        issue_type = IssueType.objects.create(workspace=workspace, name="Bug")
        ProjectIssueType.objects.create(project=project, issue_type=issue_type)
        workflow = Workflow.objects.create(project=project, name="Bug flow")
        WorkflowIssueTypeMapping.objects.create(project=project, workflow=workflow, issue_type=issue_type)
        url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/workflow-issue-types/{issue_type.id}/"

        renamed = session_client.patch(url, {"name": "Defect"}, format="json")
        assert renamed.status_code == status.HTTP_200_OK, renamed.json()
        assert renamed.json()["name"] == "Defect"

        deleted = session_client.delete(url)
        assert deleted.status_code == status.HTTP_204_NO_CONTENT
        assert not ProjectIssueType.objects.filter(project=project, issue_type=issue_type).exists()
        assert not WorkflowIssueTypeMapping.objects.filter(project=project, issue_type=issue_type).exists()

    def test_work_item_type_with_existing_item_cannot_be_deleted(self, session_client, workspace, project):
        issue_type = IssueType.objects.create(workspace=workspace, name="Feature")
        ProjectIssueType.objects.create(project=project, issue_type=issue_type)
        Issue.objects.create(project=project, name="Existing item", type=issue_type)
        url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/workflow-issue-types/{issue_type.id}/"

        response = session_client.delete(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert ProjectIssueType.objects.filter(project=project, issue_type=issue_type).exists()
