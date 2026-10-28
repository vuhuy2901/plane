from datetime import timedelta

import pytest
from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from plane.db.models import (
    Issue,
    IssueAssignee,
    IssueComment,
    IssueLabel,
    IssueType,
    ProjectIssueType,
    Label,
    ProjectAutomationRule,
    ProjectAutomationEvent,
    ProjectAutomationExecution,
    State,
)
from plane.services.automation_runtime import capture_context, emit_event, process_event
from plane.services.automation_rules import validate_definition
from plane.tests.factories import ProjectFactory, ProjectMemberFactory, UserFactory


@pytest.fixture
def runtime():
    actor = UserFactory()
    project = ProjectFactory(workspace__owner=actor)
    ProjectMemberFactory(project=project, member=actor, role=20)
    state = State.objects.create(project=project, name="To Do", color="#123456", group="unstarted")
    issue = Issue.objects.create(project=project, name="Automation item", state=state)
    Issue.objects.filter(pk=issue.id).update(created_by=actor)
    issue.refresh_from_db()
    return project, actor, issue


def make_event(runtime, actions, conditions=None, trigger="created"):
    project, actor, issue = runtime
    rule = ProjectAutomationRule.objects.create(
        project=project,
        enabled=True,
        enabled_at=timezone.now(),
        execution_actor=actor,
        definition={"name": "Test", "trigger": trigger, "conditions": conditions or [], "actions": actions},
    )
    event = emit_event(issue, capture_context(project.id))
    return rule, event


def test_unchanged_label_condition_is_present_in_updated_event(runtime):
    project, actor, issue = runtime
    label = Label.objects.create(project=project, name="Needs review")
    IssueLabel.objects.create(project=project, issue=issue, label=label)
    ProjectAutomationRule.objects.create(
        project=project,
        enabled=True,
        enabled_at=timezone.now(),
        execution_actor=actor,
        definition={
            "name": "Label on title update",
            "trigger": "updated",
            "trigger_options": {"field": "name"},
            "conditions": [{"field": "label", "operator": "contains", "value": str(label.id)}],
            "actions": [{"type": "change_priority", "priority": "high"}],
        },
    )
    context = capture_context(project.id, issue, {"name"})
    issue.name = "Updated title"
    issue.save(update_fields=["name"])
    event = emit_event(issue, context)
    assert event is not None
    process_event(event.id)
    issue.refresh_from_db()
    assert issue.priority == "high"


def test_create_action_does_not_require_initial_state(runtime):
    project, _, issue = runtime
    issue_type = IssueType.objects.create(workspace=project.workspace, name="Bug")
    ProjectIssueType.objects.create(project=project, issue_type=issue_type)
    definition = {
        "name": "Create bug",
        "trigger": "created",
        "actions": [
            {
                "type": "create_work_item",
                "type_id": str(issue_type.id),
                "title": "Bug",
                "priority": "high",
            }
        ],
    }
    assert "state_id" not in validate_definition(project, definition)["actions"][0]


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
def test_local_eager_mode_delivers_event_after_transaction_commit(
    runtime, mocker, django_capture_on_commit_callbacks
):
    project, actor, issue = runtime
    ProjectAutomationRule.objects.create(
        project=project,
        enabled=True,
        enabled_at=timezone.now(),
        execution_actor=actor,
        definition={
            "name": "Local delivery",
            "trigger": "created",
            "conditions": [],
            "actions": [{"type": "change_priority", "priority": "high"}],
        },
    )
    delay = mocker.patch("plane.bgtasks.project_automation_task.run_project_automation.delay")

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with transaction.atomic():
            event = emit_event(issue, capture_context(project.id))
            delay.assert_not_called()

    assert len(callbacks) == 1
    delay.assert_called_once_with(str(event.id))


pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize("mode", ["specific_member", "project_lead", "creator"])
def test_assignment_modes_and_no_loop(runtime, mode):
    project, actor, issue = runtime
    project.project_lead = actor
    project.save()
    action = {"type": "assign_user", "mode": mode, "only_if_unassigned": True}
    if mode == "specific_member":
        action["member_id"] = str(actor.id)
    _, event = make_event(runtime, [action])
    process_event(event.id)
    assert list(IssueAssignee.objects.filter(issue=issue).values_list("assignee_id", flat=True)) == [actor.id]
    assert ProjectAutomationExecution.objects.get(event=event).status == "success"
    assert ProjectAutomationEvent.objects.count() == 1


def test_add_label_and_urgent_priority(runtime):
    project, _, issue = runtime
    label = Label.objects.create(project=project, name="Bug")
    _, event = make_event(
        runtime, [{"type": "add_label", "label_id": str(label.id)}, {"type": "change_priority", "priority": "urgent"}]
    )
    process_event(event.id)
    issue.refresh_from_db()
    assert issue.priority == "urgent"
    assert IssueLabel.objects.filter(issue=issue, label=label).exists()


def test_comment_is_escaped_and_duplicate_delivery_does_not_repeat_actions(runtime):
    _, _, issue = runtime
    _, event = make_event(runtime, [{"type": "add_comment", "text": "Nghiệm thu <script>alert(1)</script>"}])
    process_event(event.id)
    ProjectAutomationEvent.objects.filter(pk=event.id).update(processed_at=None)
    process_event(event.id)
    assert IssueComment.objects.filter(issue=issue).count() == 1
    assert "<script>" not in IssueComment.objects.get(issue=issue).comment_html
    assert ProjectAutomationExecution.objects.filter(event=event).count() == 1


def test_due_date_uses_event_date_in_project_timezone(runtime):
    project, _, issue = runtime
    project.timezone = "Asia/Bangkok"
    project.save()
    _, event = make_event(runtime, [{"type": "set_due_date", "days": 3}])
    process_event(event.id)
    issue.refresh_from_db()
    from zoneinfo import ZoneInfo

    assert issue.target_date == event.created_at.astimezone(ZoneInfo(project.timezone)).date() + timedelta(days=3)


def test_disabled_or_condition_mismatch_are_skipped(runtime):
    _, _, issue = runtime
    rule, event = make_event(runtime, [{"type": "change_priority", "priority": "urgent"}])
    rule.enabled = False
    rule.save()
    process_event(event.id)
    assert ProjectAutomationExecution.objects.get(event=event).status == "skipped"
    _, second = make_event(
        runtime,
        [{"type": "change_priority", "priority": "urgent"}],
        [{"field": "priority", "operator": "equals", "value": "urgent"}],
    )
    process_event(second.id)
    assert ProjectAutomationExecution.objects.get(event=second).status == "skipped"
    issue.refresh_from_db()
    assert issue.priority != "urgent"


def test_rule_failure_rolls_back_prior_comment(runtime):
    project, _, issue = runtime
    # A removed resource invalidates the definition before any action executes.
    label = Label.objects.create(project=project, name="Temporary")
    _, event = make_event(
        runtime, [{"type": "add_comment", "text": "Must rollback"}, {"type": "add_label", "label_id": str(label.id)}]
    )
    Label.objects.filter(pk=label.id).delete()
    process_event(event.id)
    assert not IssueComment.objects.filter(issue=issue).exists()
    assert ProjectAutomationExecution.objects.get(event=event).status == "failed"


def test_kill_switch_and_unassigned_only(runtime, monkeypatch):
    project, actor, issue = runtime
    IssueAssignee.objects.create(project=project, issue=issue, assignee=actor)
    _, event = make_event(
        runtime,
        [{"type": "assign_user", "mode": "specific_member", "member_id": str(actor.id), "only_if_unassigned": True}],
    )
    process_event(event.id)
    assert ProjectAutomationExecution.objects.get(event=event).status == "skipped"
    monkeypatch.setenv("PROJECT_AUTOMATIONS_ENABLED", "0")
    assert capture_context(project.id, issue) is None


def test_completed_event_is_derived_only_when_entering_completed(runtime):
    project, _, issue = runtime
    make_event(runtime, [{"type": "add_comment", "text": "Done"}], trigger="completed")
    context = capture_context(project.id, issue)
    done = State.objects.create(project=project, name="Done", color="#123456", group="completed")
    issue.state = done
    issue.save()
    event = emit_event(issue, context)
    assert "completed" in event.triggers
    assert "state_changed" in event.triggers


def test_second_action_failure_rolls_back_first_action_and_records_failure(runtime, monkeypatch):
    from rest_framework.exceptions import ValidationError

    _, _, issue = runtime
    _, event = make_event(
        runtime, [{"type": "add_comment", "text": "Rollback me"}, {"type": "change_priority", "priority": "urgent"}]
    )

    def fail_update(*args, **kwargs):
        raise ValidationError("Injected failure in second action")

    monkeypatch.setattr("plane.app.serializers.issue.IssueCreateSerializer.update", fail_update)
    process_event(event.id)
    assert not IssueComment.objects.filter(issue=issue).exists()
    assert ProjectAutomationExecution.objects.get(event=event).status == "failed"


def test_temporary_error_retries_without_duplicating_comment(runtime, monkeypatch):
    from django.db import OperationalError
    from plane.app.serializers.issue import IssueCreateSerializer

    _, _, issue = runtime
    _, event = make_event(
        runtime, [{"type": "add_comment", "text": "Exactly once"}, {"type": "change_priority", "priority": "urgent"}]
    )
    original = IssueCreateSerializer.update

    def fail_update(*args, **kwargs):
        raise OperationalError("Temporary database failure")

    monkeypatch.setattr(IssueCreateSerializer, "update", fail_update)
    with pytest.raises(OperationalError):
        process_event(event.id)
    assert not IssueComment.objects.filter(issue=issue).exists()
    monkeypatch.setattr(IssueCreateSerializer, "update", original)
    process_event(event.id)
    assert IssueComment.objects.filter(issue=issue).count() == 1
    assert ProjectAutomationExecution.objects.get(event=event).status == "success"


def test_automation_cannot_skip_a_published_workflow_transition(runtime):
    from plane.db.models import (
        IssueType,
        ProjectIssueType,
        Workflow,
        WorkflowVersion,
        WorkflowVersionState,
        WorkflowIssueTypeMapping,
    )

    project, _, issue = runtime
    kind = IssueType.objects.create(workspace=project.workspace, name="Task")
    ProjectIssueType.objects.create(project=project, issue_type=kind)
    issue.type = kind
    issue.save()
    workflow = Workflow.objects.create(project=project, name="Strict")
    version = WorkflowVersion.objects.create(project=project, workflow=workflow, version=1, status="published")
    done = State.objects.create(project=project, name="Accepted", color="#123456", group="completed")
    for state in (issue.state, done):
        WorkflowVersionState.objects.create(project=project, workflow_version=version, state=state, name=state.name)
    workflow.active_version = version
    workflow.save()
    WorkflowIssueTypeMapping.objects.create(project=project, workflow=workflow, issue_type=kind)
    _, event = make_event(runtime, [{"type": "change_state", "state_id": str(done.id)}])
    source = issue.state_id
    process_event(event.id)
    issue.refresh_from_db()
    assert issue.state_id == source
    assert ProjectAutomationExecution.objects.get(event=event).status == "failed"
