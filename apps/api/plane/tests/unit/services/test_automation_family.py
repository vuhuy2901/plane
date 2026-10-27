from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from django.db import close_old_connections, transaction
from django.utils import timezone

from plane.db.models import (
    Issue,
    IssueType,
    ProjectIssueType,
    State,
    Workflow,
    WorkflowVersion,
    WorkflowVersionState,
    WorkflowTransition,
    WorkflowIssueTypeMapping,
    ProjectAutomationRule,
    ProjectAutomationEvent,
    ProjectAutomationExecution,
    WorkflowTransitionAudit,
)
from plane.services.automation_runtime import capture_context, emit_event, process_event, snapshot
from plane.services.automation_family import completed_parent, FamilySkipped
from plane.tests.factories import ProjectFactory, ProjectMemberFactory, UserFactory


@pytest.fixture
def family():
    actor = UserFactory()
    project = ProjectFactory(workspace__owner=actor)
    ProjectMemberFactory(project=project, member=actor, role=20)
    kinds = []
    for level, name in [(1, "Task"), (2, "Subtask")]:
        kind = IssueType.objects.create(workspace=project.workspace, name=name)
        ProjectIssueType.objects.create(project=project, issue_type=kind, level=level)
        kinds.append(kind)
    opened = State.objects.create(project=project, name="Working", group="started", color="#123456")
    done = State.objects.create(project=project, name="Hoàn tất", group="completed", color="#123456")
    review = State.objects.create(project=project, name="Acceptance", group="started", color="#123456")
    parent = Issue.objects.create(project=project, name="Parent", type=kinds[0], state=opened)
    children = [
        Issue.objects.create(project=project, name=f"Child {i}", parent=parent, type=kinds[1], state=opened)
        for i in range(3)
    ]
    wf = Workflow.objects.create(project=project, name="Task flow")
    version = WorkflowVersion.objects.create(project=project, workflow=wf, version=1, status="published")
    a = WorkflowVersionState.objects.create(project=project, workflow_version=version, state=opened, name=opened.name)
    b = WorkflowVersionState.objects.create(project=project, workflow_version=version, state=review, name=review.name)
    edge = WorkflowTransition.objects.create(
        project=project, workflow_version=version, source=a, target=b, name="Review"
    )
    wf.active_version = version
    wf.save()
    WorkflowIssueTypeMapping.objects.create(project=project, workflow=wf, issue_type=kinds[0])
    rule = ProjectAutomationRule.objects.create(
        project=project,
        execution_actor=actor,
        enabled=True,
        enabled_at=timezone.now(),
        definition={
            "name": "Review parent",
            "trigger": "SUBTASK_COMPLETED",
            "conditions": [{"field": "ALL_SUBTASKS_COMPLETED", "operator": "is_true"}],
            "actions": [{"type": "CHANGE_PARENT_STATE", "state_id": str(review.id), "target": "parent"}],
        },
    )
    return project, parent, children, opened, done, review, rule, edge


def complete(family, index):
    project, _, children, _, done, *_ = family
    child = children[index]
    context = capture_context(project.id, child)
    child.state = done
    child.save()
    return emit_event(child, context)


pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_two_of_three_skip_then_last_moves_parent_once(family):
    _, parent, children, opened, _, review, _, _ = family
    for i in (0, 1):
        event = complete(family, i)
        assert "SUBTASK_COMPLETED" in event.triggers
        process_event(event.id)
        assert ProjectAutomationExecution.objects.get(event=event).status == "skipped"
    parent.refresh_from_db()
    assert parent.state_id == opened.id
    event = complete(family, 2)
    process_event(event.id)
    process_event(event.id)
    parent.refresh_from_db()
    assert parent.state_id == review.id
    assert WorkflowTransitionAudit.objects.filter(issue=parent).count() == 1
    assert ProjectAutomationExecution.objects.get(event=event).status == "success"
    assert ProjectAutomationEvent.objects.count() == 3  # Parent update cannot cascade.
    context = capture_context(parent.project_id, children[2])
    children[2].name = "Edit completed Subtask"
    children[2].save()
    edited = emit_event(children[2], context)
    assert edited.triggers == ["updated"]
    process_event(edited.id)
    assert ProjectAutomationExecution.objects.get(event=edited).status == "skipped"


def test_reopened_sibling_prevents_parent_update(family):
    _, parent, children, opened, *_ = family
    for i in range(3):
        event = complete(family, i)
    children[0].state = opened
    children[0].save()
    process_event(event.id)
    parent.refresh_from_db()
    assert parent.state_id == opened.id
    assert "Not all" in ProjectAutomationExecution.objects.get(event=event).detail


@pytest.mark.parametrize(
    "scenario", ["target", "transition", "disabled", "foreign", "missing_state", "epic", "no_children"]
)
def test_family_safety_guards(family, scenario):
    project, parent, children, opened, _, review, rule, edge = family
    for i in range(3):
        event = complete(family, i)
    if scenario == "target":
        parent.state = review
        parent.save()
    elif scenario == "transition":
        WorkflowTransition.objects.filter(pk=edge.pk).delete()
    elif scenario == "disabled":
        rule.enabled = False
        rule.save()
    elif scenario == "foreign":
        other = ProjectFactory(workspace=project.workspace, identifier="FOREIGN")
        assert other.id != project.id
        assert Issue.all_objects.filter(pk=children[0].pk).update(project_id=other.id) == 1
        assert Issue.all_objects.get(pk=children[0].pk).parent_id == parent.id
    elif scenario == "missing_state":
        Issue.objects.filter(pk=children[0].pk).update(state=None)
    elif scenario == "epic":
        epic = IssueType.objects.create(workspace=project.workspace, name="Epic")
        parent.type = epic
        parent.save()
    else:
        Issue.objects.filter(parent=parent).delete()
        with transaction.atomic(), pytest.raises(FamilySkipped):
            completed_parent(children[2], SimpleNamespace(snapshot=snapshot(children[2])))
    before = parent.updated_at
    process_event(event.id)
    parent.refresh_from_db()
    assert parent.updated_at == before
    assert not WorkflowTransitionAudit.objects.filter(issue=parent).exists()
    assert ProjectAutomationExecution.objects.get(event=event).status in {"skipped", "failed"}


@pytest.mark.django_db(transaction=True)
def test_two_completions_in_parallel_update_parent_only_once(family):
    _, parent, _, _, _, review, _, _ = family
    complete(family, 0)
    events = [complete(family, i) for i in (1, 2)]

    def run(pk):
        close_old_connections()
        try:
            process_event(pk)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, [event.pk for event in events]))
    parent.refresh_from_db()
    assert parent.state_id == review.id
    assert WorkflowTransitionAudit.objects.filter(issue=parent).count() == 1
    assert sorted(ProjectAutomationExecution.objects.values_list("status", flat=True)) == ["skipped", "success"]


def test_parent_rule_api_reload_dry_run_and_history(family):
    from rest_framework.test import APIClient

    project, parent, children, _, _, review, rule, _ = family
    client = APIClient()
    client.force_authenticate(user=rule.execution_actor)
    base = f"/api/workspaces/{project.workspace.slug}/projects/{project.id}/automations/"
    created = client.post(base + "rules/", {**rule.definition, "enabled": True}, format="json")
    assert created.status_code == 201, created.data
    assert not created.data["enabled"]
    url = base + f"rules/{created.data['id']}/"
    assert client.get(url).data["actions"][0]["target"] == "parent"
    for i in range(3):
        event = complete(family, i)
    before = parent.updated_at
    dry = client.post(url + "test/", {"issue_id": str(children[2].id)}, format="json")
    assert dry.status_code == 200, dry.data
    assert dry.data["writes"] == 0
    parent.refresh_from_db()
    assert parent.updated_at == before
    process_event(event.id)
    history = client.get(base + "history/")
    assert history.status_code == 200
    assert history.data["results"][0]["status"] == "success"
    assert history.data["results"][0]["snapshot"]["parent_id"] == str(parent.id)
