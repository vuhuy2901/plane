"""Regression coverage for explainable evaluations and durable create actions."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from django.db import OperationalError
from django.utils import timezone

from plane.db.models import (
    Issue,
    IssueAssignee,
    IssueComment,
    IssueLabel,
    IssueRelation,
    IssueType,
    Label,
    ProjectAutomationEvent,
    ProjectAutomationExecution,
    ProjectIssueType,
    State,
)
from plane.services import automation_runtime
from plane.tests.unit.services.test_automation_extended import create_bug_rule, rule_for
from plane.tests.unit.services.test_automation_runtime import runtime as runtime_fixture

pytestmark = [pytest.mark.unit, pytest.mark.django_db]
runtime = runtime_fixture


def assert_check(check, *, expected, actual, matched):
    assert {"field", "operator", "expected", "actual", "matched"} <= check.keys()
    assert check["field"]
    assert check["operator"]
    assert check["expected"] == expected
    assert check["actual"] == actual
    assert check["matched"] is matched


def test_wrong_event_kind_reports_trigger_instead_of_condition_failure(runtime):
    project, _, issue = runtime
    rule = rule_for(runtime, "created")
    before = automation_runtime.capture_context(project.id, issue)
    issue.priority = "high"
    issue.save()
    event = automation_runtime.emit_event(issue, before)

    automation_runtime.process_event(event.id)

    execution = ProjectAutomationExecution.objects.get(event=event, rule=rule)
    assert execution.status == "skipped"
    assert "trigger" in execution.detail.lower()
    assert "created" in execution.detail
    assert "updated" in execution.detail
    evaluation = execution.snapshot["evaluation"]
    assert evaluation["matched"] is False
    assert evaluation["trigger"]["matched"] is False
    assert evaluation["trigger"]["expected"] == "created"
    assert evaluation["trigger"]["actual"] == event.triggers
    assert evaluation["conditions"] == []
    assert not IssueComment.objects.filter(issue=issue).exists()


def test_state_trigger_mismatch_records_expected_and_actual_old_state(runtime):
    project, _, issue = runtime
    initial = str(issue.state_id)
    expected = State.objects.create(project=project, name="In Testing", group="started", color="#123456")
    destination = State.objects.create(project=project, name="In Progress", group="started", color="#123456")
    rule = rule_for(runtime, "state_changed", {"from_state": str(expected.id), "to_state": str(destination.id)})
    before = automation_runtime.capture_context(project.id, issue)
    issue.state = destination
    issue.save()
    event = automation_runtime.emit_event(issue, before)

    automation_runtime.process_event(event.id)

    execution = ProjectAutomationExecution.objects.get(event=event, rule=rule)
    assert execution.status == "skipped"
    assert "trigger" in execution.detail.lower()
    assert str(expected.id) in execution.detail
    assert initial in execution.detail
    evaluation = execution.snapshot["evaluation"]
    assert evaluation["matched"] is False
    assert evaluation["trigger"]["matched"] is False
    checks = evaluation["trigger"]["checks"]
    mismatch = next(check for check in checks if check["expected"] == str(expected.id))
    assert_check(mismatch, expected=str(expected.id), actual=initial, matched=False)
    match = next(check for check in checks if check["expected"] == str(destination.id))
    assert_check(match, expected=str(destination.id), actual=str(destination.id), matched=True)
    assert not IssueComment.objects.filter(issue=issue).exists()


def test_updated_trigger_reports_unchanged_selected_field(runtime):
    project, _, issue = runtime
    rule = rule_for(runtime, "updated", {"field": "name"})
    before = automation_runtime.capture_context(project.id, issue)
    issue.priority = "high"
    issue.save()
    event = automation_runtime.emit_event(issue, before)

    automation_runtime.process_event(event.id)

    execution = ProjectAutomationExecution.objects.get(event=event, rule=rule)
    assert execution.status == "skipped"
    assert "trigger" in execution.detail.lower()
    assert "name" in execution.detail
    evaluation = execution.snapshot["evaluation"]
    assert evaluation["matched"] is False
    assert evaluation["trigger"]["matched"] is False
    assert any(check["matched"] is False for check in evaluation["trigger"]["checks"])
    assert not IssueComment.objects.filter(issue=issue).exists()


def test_all_condition_diagnostics_survive_first_mismatch_and_are_read_only(runtime):
    project, _, issue = runtime
    label = Label.objects.create(project=project, name="Review")
    IssueLabel.objects.create(project=project, issue=issue, label=label)
    conditions = [
        {"field": "priority", "operator": "equals", "value": "urgent"},
        {"field": "label", "operator": "contains", "value": str(label.id)},
        {"field": "assignee", "operator": "is_empty"},
    ]
    rule = rule_for(runtime, "created", conditions=conditions)
    event = automation_runtime.emit_event(issue, automation_runtime.capture_context(project.id))
    original_definition, original_snapshot = deepcopy(rule.definition), deepcopy(event.snapshot)

    evaluation = automation_runtime.evaluate_rule(rule.definition, event, issue)

    assert evaluation["matched"] is False
    assert evaluation["trigger"]["matched"] is True
    assert len(evaluation["conditions"]) == 3
    priority, labels, assignees = evaluation["conditions"]
    assert_check(priority, expected="urgent", actual="none", matched=False)
    assert priority["field"] == "priority"
    assert priority["operator"] == "equals"
    assert_check(labels, expected=str(label.id), actual=[str(label.id)], matched=True)
    assert_check(assignees, expected=None, actual=[], matched=True)
    assert rule.definition == original_definition
    assert event.snapshot == original_snapshot
    assert not ProjectAutomationExecution.objects.exists()
    assert not IssueComment.objects.filter(issue=issue).exists()

    automation_runtime.process_event(event.id)

    execution = ProjectAutomationExecution.objects.get(event=event, rule=rule)
    assert execution.status == "skipped"
    assert "condition" in execution.detail.lower()
    assert "priority" in execution.detail
    assert "urgent" in execution.detail
    assert "none" in execution.detail
    assert execution.snapshot["evaluation"] == evaluation


def test_deleted_source_is_distinguished_from_trigger_or_condition_mismatch(runtime):
    project, _, issue = runtime
    rule = rule_for(runtime, "created")
    event = automation_runtime.emit_event(issue, automation_runtime.capture_context(project.id))
    # Model the event FK after the source's hard deletion without invoking live deletion tasks.
    ProjectAutomationEvent.objects.filter(pk=event.pk).update(issue=None)

    automation_runtime.process_event(event.id)

    execution = ProjectAutomationExecution.objects.get(event=event, rule=rule)
    assert execution.status == "skipped"
    assert any(word in execution.detail.lower() for word in ("missing", "no longer exists", "not found", "removed"))
    assert "conditions were not met" not in execution.detail.lower()
    assert not IssueComment.objects.filter(issue=issue).exists()


def test_created_type_filter_uses_actual_type_even_when_conditions_match(runtime):
    project, _, issue = runtime
    task = IssueType.objects.create(workspace=project.workspace, name="Task")
    bug = IssueType.objects.create(workspace=project.workspace, name="Bug")
    for kind in (task, bug):
        ProjectIssueType.objects.create(project=project, issue_type=kind)
    issue.type = task
    issue.save()
    rule = rule_for(runtime, "created", {"type_id": str(bug.id)})
    event = SimpleNamespace(
        snapshot=automation_runtime.snapshot(issue),
        before_snapshot=None,
        triggers=["created"],
        context={},
        created_at=timezone.now(),
        issue_id=issue.id,
    )

    evaluation = automation_runtime.evaluate_rule(rule.definition, event, issue)

    assert evaluation["matched"] is False
    assert evaluation["trigger"]["matched"] is False
    assert evaluation["conditions"] == []
    check = next(check for check in evaluation["trigger"]["checks"] if check["expected"] == str(bug.id))
    assert_check(check, expected=str(bug.id), actual=str(task.id), matched=False)


def test_matches_conditions_preserves_lazy_family_check_after_mismatch(runtime, monkeypatch):
    project, _, issue = runtime
    definition = {
        "conditions": [
            {"field": "priority", "operator": "equals", "value": "urgent"},
            {"field": "ALL_SUBTASKS_COMPLETED", "operator": "is_true"},
        ]
    }
    event = SimpleNamespace(snapshot=automation_runtime.snapshot(issue), issue_id=issue.id)

    def unexpected_family_check(*args, **kwargs):
        pytest.fail("A prior condition mismatch must short-circuit the legacy family check.")

    monkeypatch.setattr(automation_runtime, "completed_parent", unexpected_family_check)
    assert automation_runtime.matches_conditions(definition, event, project) is False


def test_family_skip_is_persisted_as_condition_diagnostic_instead_of_failure(runtime):
    project, _, issue = runtime
    rule = rule_for(runtime, "created", conditions=[{"field": "ALL_SUBTASKS_COMPLETED", "operator": "is_true"}])
    event = automation_runtime.emit_event(issue, automation_runtime.capture_context(project.id))

    automation_runtime.process_event(event.id)

    execution = ProjectAutomationExecution.objects.get(event=event, rule=rule)
    assert execution.status == "skipped"
    evaluation = execution.snapshot["evaluation"]
    assert evaluation["matched"] is False
    assert evaluation["trigger"]["matched"] is True
    check = evaluation["conditions"][0]
    assert check["field"] == "ALL_SUBTASKS_COMPLETED"
    assert_check(check, expected=True, actual=False, matched=False)
    assert "parent" in check["reason"].lower()
    assert execution.detail == check["reason"]
    assert not IssueComment.objects.filter(issue=issue).exists()


def test_bug_creation_persists_checkpoint_relation_and_success_on_redelivery(runtime):
    _, actor, issue = runtime
    rule, event = create_bug_rule(runtime)
    source_state = issue.state_id

    automation_runtime.process_event(event.id)
    event.refresh_from_db()
    checkpoint = event.progress[str(rule.id)]["0"]
    bug = Issue.objects.get(pk=checkpoint["created_issue_id"])
    assert bug.name == "Bug: Automation item"
    assert bug.type.name == "Bug"
    assert bug.priority == "high"
    assert bug.created_by_id == bug.updated_by_id == actor.id
    assert checkpoint["done"] is True
    assert checkpoint["changed"] is True
    assert IssueRelation.objects.filter(issue=issue, related_issue=bug, relation_type="blocked_by").count() == 1
    execution = ProjectAutomationExecution.objects.get(event=event, rule=rule)
    assert execution.status == "success"
    assert execution.snapshot["evaluation"]["matched"] is True
    assert execution.snapshot["steps"] == event.progress
    assert event.processed_at is not None

    # Exercise durable execution deduplication as well as the processed-event shortcut.
    ProjectAutomationEvent.objects.filter(pk=event.pk).update(processed_at=None)
    automation_runtime.process_event(event.id)
    automation_runtime.process_event(event.id)

    assert Issue.objects.filter(project=issue.project).count() == 2
    assert IssueRelation.objects.count() == 1
    assert ProjectAutomationExecution.objects.filter(event=event).count() == 1
    assert ProjectAutomationEvent.objects.count() == 1
    assert not IssueAssignee.objects.filter(issue=issue).exists()
    issue.refresh_from_db()
    assert issue.state_id == source_state


def test_relation_retry_keeps_committed_created_checkpoint(runtime, monkeypatch):
    _, _, issue = runtime
    rule, event = create_bug_rule(runtime)
    create_relation = automation_runtime.create_relation

    def fail_relation(*args, **kwargs):
        raise OperationalError("Temporary relation failure")

    monkeypatch.setattr(automation_runtime, "create_relation", fail_relation)
    with pytest.raises(OperationalError, match="Temporary relation failure"):
        automation_runtime.process_event(event.id)

    event.refresh_from_db()
    checkpoint = event.progress[str(rule.id)]["0"]
    bug_id = checkpoint["created_issue_id"]
    assert checkpoint["changed"] is True
    assert not checkpoint.get("done")
    assert Issue.objects.filter(pk=bug_id, name="Bug: Automation item").exists()
    assert not IssueRelation.objects.exists()
    assert not ProjectAutomationExecution.objects.filter(event=event).exists()
    assert event.processed_at is None

    monkeypatch.setattr(automation_runtime, "create_relation", create_relation)
    automation_runtime.process_event(event.id)

    event.refresh_from_db()
    assert event.progress[str(rule.id)]["0"]["created_issue_id"] == bug_id
    assert event.progress[str(rule.id)]["0"]["done"] is True
    assert Issue.objects.filter(project=issue.project).count() == 2
    assert IssueRelation.objects.filter(issue=issue, related_issue_id=bug_id, relation_type="blocked_by").count() == 1
    assert ProjectAutomationExecution.objects.get(event=event).status == "success"


def test_two_create_actions_finish_both_checkpoints_before_event_is_processed(runtime):
    project, _, issue = runtime
    bug = IssueType.objects.create(workspace=project.workspace, name="Bug")
    ProjectIssueType.objects.create(project=project, issue_type=bug)
    actions = [
        {
            "type": "create_work_item",
            "type_id": str(bug.id),
            "title": title,
            "priority": "high",
            "relation": "blocking",
        }
        for title in ("First regression Bug", "Second regression Bug")
    ]
    rule = rule_for(runtime, "created", actions=actions)
    event = automation_runtime.emit_event(issue, automation_runtime.capture_context(project.id))

    automation_runtime.process_event(event.id)

    event.refresh_from_db()
    assert event.processed_at is not None
    steps = event.progress[str(rule.id)]
    assert set(steps) == {"0", "1"}
    created_ids = {step["created_issue_id"] for step in steps.values()}
    assert len(created_ids) == 2
    assert all(step["done"] is True and step["changed"] is True for step in steps.values())
    assert set(Issue.objects.filter(pk__in=created_ids).values_list("name", flat=True)) == {
        "First regression Bug",
        "Second regression Bug",
    }
    assert (
        IssueRelation.objects.filter(issue=issue, related_issue_id__in=created_ids, relation_type="blocked_by").count()
        == 2
    )
    assert ProjectAutomationExecution.objects.get(event=event, rule=rule).status == "success"

    ProjectAutomationEvent.objects.filter(pk=event.pk).update(processed_at=None)
    automation_runtime.process_event(event.id)
    assert Issue.objects.filter(project=project).count() == 3
    assert IssueRelation.objects.count() == 2
    assert ProjectAutomationExecution.objects.filter(event=event).count() == 1
