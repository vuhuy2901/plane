import statistics
import time

import pytest
from django.utils import timezone

from plane.db.models import (
    Issue,
    IssueAssignee,
    ProjectAutomationRule,
    ProjectAutomationEvent,
    ProjectAutomationExecution,
)
from plane.services.automation_runtime import process_event
from plane.tests.factories import ProjectFactory, ProjectMemberFactory


@pytest.fixture
def event_project(workspace, create_user):
    project = ProjectFactory(workspace=workspace, identifier="EVT")
    ProjectMemberFactory(project=project, member=create_user, role=20)
    rule = ProjectAutomationRule.objects.create(
        project=project,
        enabled=True,
        enabled_at=timezone.now(),
        execution_actor=create_user,
        definition={
            "name": "Assign",
            "trigger": "created",
            "conditions": [],
            "actions": [
                {
                    "type": "assign_user",
                    "mode": "specific_member",
                    "member_id": str(create_user.id),
                    "only_if_unassigned": True,
                }
            ],
        },
    )
    return project, rule


pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.mark.parametrize("token", [False, True])
def test_api_create_is_async_then_worker_assigns_and_disable_stops_new_events(
    session_client, api_key_client, workspace, event_project, create_user, token, monkeypatch
):
    project, rule = event_project
    client = api_key_client if token else session_client
    base = (
        f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/"
        if token
        else f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/"
    )

    def broker_unavailable(*args, **kwargs):
        raise AssertionError("Task request must not contact the automation broker")

    monkeypatch.setattr("plane.bgtasks.project_automation_task.run_project_automation.delay", broker_unavailable)
    response = client.post(base, {"name": "New task"}, format="json")
    assert response.status_code == 201, response.data
    issue = Issue.objects.get(project=project, name="New task")
    assert not IssueAssignee.objects.filter(issue=issue).exists()
    event = ProjectAutomationEvent.objects.get(issue=issue)
    process_event(event.id)
    assert IssueAssignee.objects.filter(issue=issue, assignee=create_user).exists()
    assert ProjectAutomationExecution.objects.get(event=event).status == "success"
    rule.enabled = False
    rule.save()
    assert client.post(base, {"name": "After disabling"}, format="json").status_code == 201
    assert ProjectAutomationEvent.objects.count() == 1


def test_api_latency_disabled_vs_event_capture(session_client, workspace, event_project, monkeypatch):
    project, _ = event_project
    url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/"
    samples = {}
    update_samples = {}
    for enabled in ("0", "1"):
        monkeypatch.setenv("PROJECT_AUTOMATIONS_ENABLED", enabled)
        elapsed = []
        updated_elapsed = []
        for index in range(12):
            started = time.perf_counter()
            response = session_client.post(url, {"name": f"Latency {enabled}-{index}"}, format="json")
            elapsed.append((time.perf_counter() - started) * 1000)
            assert response.status_code == 201, response.data
            started = time.perf_counter()
            updated = session_client.patch(url + f"{response.data['id']}/", {"priority": "high"}, format="json")
            updated_elapsed.append((time.perf_counter() - started) * 1000)
            assert updated.status_code == 204, updated.data
        samples[enabled] = round(statistics.median(elapsed[2:]), 2)
        update_samples[enabled] = round(statistics.median(updated_elapsed[2:]), 2)
    print(
        f"AUTOMATION_CREATE_LATENCY_MS disabled={samples['0']} enabled={samples['1']} "
        f"overhead={round(samples['1'] - samples['0'], 2)}"
    )
    print(f"AUTOMATION_UPDATE_LATENCY_MS disabled={update_samples['0']} enabled={update_samples['1']}")
    assert ProjectAutomationEvent.objects.count() == 24
