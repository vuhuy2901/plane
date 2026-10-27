import resource
import statistics
import time

import pytest
from django.utils import timezone

from plane.db.models import (
    Issue,
    IssueComment,
    IssueRelation,
    ProjectAutomationRule,
    ProjectAutomationEvent,
    ProjectAutomationExecution,
)
from plane.services.automation_runtime import process_event
from plane.tests.factories import ProjectFactory, ProjectMemberFactory

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.mark.parametrize("token", [False, True])
def test_comment_and_relation_api_emit_committed_events(session_client, api_key_client, workspace, create_user, token):
    project = ProjectFactory(workspace=workspace, identifier="LINK")
    ProjectMemberFactory(project=project, member=create_user, role=20)
    source = Issue.objects.create(project=project, name="Task")
    bug = Issue.objects.create(project=project, name="Bug")
    client = api_key_client if token else session_client
    base = (
        f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/"
        if token
        else f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/"
    )
    for trigger in ("comment_added", "work_item_linked"):
        ProjectAutomationRule.objects.create(
            project=project,
            execution_actor=create_user,
            enabled=True,
            enabled_at=timezone.now(),
            definition={
                "name": trigger,
                "trigger": trigger,
                "conditions": [],
                "actions": [{"type": "change_priority", "priority": "urgent"}],
            },
        )
    response = client.post(base + f"{source.id}/comments/", {"comment_html": "<p>Comment event</p>"}, format="json")
    assert response.status_code == 201, response.data
    relation_url = base + f"{bug.id}/" + ("relations/" if token else "issue-relation/")
    response = client.post(relation_url, {"relation_type": "blocking", "issues": [str(source.id)]}, format="json")
    assert response.status_code == 201, response.data
    assert IssueRelation.objects.filter(issue=source, related_issue=bug, relation_type="blocked_by").exists()
    assert ProjectAutomationEvent.objects.count() == 2
    for event in ProjectAutomationEvent.objects.all():
        process_event(event.id)
    source.refresh_from_db()
    assert source.priority == "urgent"
    assert IssueComment.objects.count() == 1
    assert ProjectAutomationExecution.objects.filter(status="success").count() == 2


def test_interleaved_write_latency_cpu_memory(session_client, workspace, create_user, monkeypatch):
    """Comparable local API benchmark; print p95 and resources, not a production-load claim."""
    project = ProjectFactory(workspace=workspace, identifier="PERF")
    ProjectMemberFactory(project=project, member=create_user, role=20)
    ProjectAutomationRule.objects.create(
        project=project,
        execution_actor=create_user,
        enabled=True,
        enabled_at=timezone.now(),
        definition={
            "name": "Measure",
            "trigger": "updated",
            "conditions": [],
            "actions": [{"type": "change_priority", "priority": "urgent"}],
        },
    )
    url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/"
    samples = {mode: {"create": [], "update": [], "cpu_ms": []} for mode in ("0", "1")}
    for index in range(45):
        for mode in ("0", "1") if index % 2 else ("1", "0"):
            monkeypatch.setenv("PROJECT_AUTOMATIONS_ENABLED", mode)
            cpu = time.process_time()
            started = time.perf_counter()
            response = session_client.post(url, {"name": f"Benchmark {index}-{mode}"}, format="json")
            created = (time.perf_counter() - started) * 1000
            assert response.status_code == 201, response.data
            started = time.perf_counter()
            updated = session_client.patch(url + f"{response.data['id']}/", {"priority": "high"}, format="json")
            elapsed = (time.perf_counter() - started) * 1000
            assert updated.status_code == 204, updated.data
            if index >= 5:
                samples[mode]["create"].append(created)
                samples[mode]["update"].append(elapsed)
                samples[mode]["cpu_ms"].append((time.process_time() - cpu) * 1000)
    for operation in ("create", "update"):
        baseline, enabled = [statistics.quantiles(samples[mode][operation], n=100)[94] for mode in ("0", "1")]
        print(
            f"AUTOMATION_P95_{operation.upper()} baseline_ms={baseline:.2f} enabled_ms={enabled:.2f} increase_percent={(enabled / baseline - 1) * 100:.2f}"
        )
    print(
        f"AUTOMATION_CPU_PER_CREATE_UPDATE_MS baseline={statistics.mean(samples['0']['cpu_ms']):.2f} enabled={statistics.mean(samples['1']['cpu_ms']):.2f} process_peak_rss_mib={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.2f}"
    )
