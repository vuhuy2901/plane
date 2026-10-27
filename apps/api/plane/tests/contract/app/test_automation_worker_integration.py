import time

import pytest
from celery.contrib.testing.worker import start_worker
from django.utils import timezone

from plane.bgtasks.project_automation_task import run_project_automation
from plane.celery import app
from plane.db.models import Issue, IssueAssignee, ProjectAutomationRule, ProjectAutomationExecution
from plane.services.automation_runtime import capture_context, emit_event
from plane.tests.factories import ProjectFactory, ProjectMemberFactory, UserFactory


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_real_celery_worker_executes_assignment_once():
    actor = UserFactory()
    project = ProjectFactory(workspace__owner=actor)
    ProjectMemberFactory(project=project, member=actor, role=20)
    issue = Issue.objects.create(project=project, name="Worker integration")
    ProjectAutomationRule.objects.create(
        project=project,
        enabled=True,
        enabled_at=timezone.now(),
        execution_actor=actor,
        definition={
            "name": "Worker assignment",
            "trigger": "created",
            "conditions": [],
            "actions": [{"type": "assign_user", "mode": "specific_member", "member_id": str(actor.id)}],
        },
    )
    event = emit_event(issue, capture_context(project.id))
    queue = f"automation-test-{event.id}"
    with start_worker(app, perform_ping_check=False, pool="solo", shutdown_timeout=10, queues=[queue]):
        run_project_automation.apply_async(args=[str(event.id)], queue=queue)
        run_project_automation.apply_async(args=[str(event.id)], queue=queue)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if ProjectAutomationExecution.objects.filter(event=event, status="success").exists():
                break
            time.sleep(0.05)
        assert IssueAssignee.objects.filter(issue=issue, assignee=actor).count() == 1
    assert ProjectAutomationExecution.objects.filter(event=event).count() == 1
