from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import OperationalError, transaction
from django.utils import timezone

from plane.db.models import (
    Issue,
    IssueAssignee,
    IssueComment,
    IssueRelation,
    IssueType,
    ProjectIssueType,
    ProjectAutomationRule,
    ProjectAutomationEvent,
    ProjectAutomationExecution,
    State,
    Label,
    IssueLabel,
)
from plane.services.automation_definition import TRIGGERS, ACTIONS, OPERATORS
from plane.services.automation_events import bulk_create_relations
from plane.services.automation_runtime import capture_context, emit_event, process_event
from plane.services.automation_schedule import dispatch_schedules
from plane.tests.unit.services.test_automation_runtime import runtime as runtime_fixture, make_event
from plane.tests.factories import UserFactory, ProjectMemberFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]
runtime = runtime_fixture


def rule_for(runtime, trigger, options=None, actions=None, conditions=None):
    project, actor, _ = runtime
    return ProjectAutomationRule.objects.create(
        project=project,
        execution_actor=actor,
        enabled=True,
        enabled_at=timezone.now() - timedelta(days=2),
        definition={
            "name": "Extended",
            "trigger": trigger,
            "trigger_options": options or {},
            "conditions": conditions or [],
            "actions": actions or [{"type": "add_comment", "text": "Event received"}],
        },
    )


def test_public_catalog_has_exact_scope():
    assert len(TRIGGERS) == 8
    assert len(ACTIONS) == 9
    assert len(OPERATORS) == 7
    assert "completed" not in TRIGGERS


@pytest.mark.parametrize(
    "field,selected,expected", [("name", "name", True), ("name", "priority", False), ("priority", None, True)]
)
def test_updated_selected_fields_and_unchanged_values(runtime, field, selected, expected):
    project, _, issue = runtime
    rule_for(runtime, "updated", {"field": selected} if selected else {})
    before = capture_context(project.id, issue)
    assert emit_event(issue, before) is None
    setattr(issue, field, "urgent" if field == "priority" else "New title")
    issue.save()
    event = emit_event(issue, before)
    process_event(event.id)
    assert IssueComment.objects.filter(issue=issue).exists() is expected


@pytest.mark.parametrize("match", [True, False])
def test_state_trigger_compares_real_old_and_new_ids(runtime, match):
    project, _, issue = runtime
    done = State.objects.create(project=project, name="Complete", group="completed", color="#123456")
    rule_for(
        runtime, "state_changed", {"from_state": str(issue.state_id if match else done.id), "to_state": str(done.id)}
    )
    before = capture_context(project.id, issue)
    old = issue.state_id
    issue.state = done
    issue.save()
    event = emit_event(issue, before)
    assert event.before_snapshot["state"] == str(old)
    assert event.snapshot["state"] == str(done.id)
    process_event(event.id)
    assert IssueComment.objects.filter(issue=issue).exists() is match


def test_priority_old_new_and_multi_assignee_sets(runtime):
    project, actor, issue = runtime
    rule_for(runtime, "priority_changed", {"from_priority": "none", "to_priority": "urgent"})
    rule_for(runtime, "assignee_changed", {"previous_assignee": "unassigned", "new_assignee": str(actor.id)})
    before = capture_context(project.id, issue)
    issue.priority = "urgent"
    issue.save()
    IssueAssignee.objects.create(project=project, issue=issue, assignee=actor)
    event = emit_event(issue, before)
    process_event(event.id)
    assert IssueComment.objects.filter(issue=issue).count() == 2
    assert ProjectAutomationExecution.objects.filter(event=event).count() == 2


@pytest.mark.parametrize("replace", [True, False])
def test_assignment_preserves_existing_members_unless_replace_selected(runtime, replace):
    project, actor, issue = runtime
    other = UserFactory()
    ProjectMemberFactory(project=project, member=other, role=15)
    IssueAssignee.objects.create(project=project, issue=issue, assignee=other)
    _, event = make_event(
        runtime,
        [
            {
                "type": "assign_user",
                "mode": "specific_member",
                "member_id": str(actor.id),
                "only_if_unassigned": False,
                "replace_assignees": replace,
            }
        ],
    )
    process_event(event.id)
    ids = set(IssueAssignee.objects.filter(issue=issue).values_list("assignee_id", flat=True))
    assert ids == ({actor.id} if replace else {actor.id, other.id})


def test_comment_event_is_transactional_and_automation_comment_does_not_chain(runtime):
    project, actor, issue = runtime
    rule_for(
        runtime,
        "comment_added",
        {"author_id": str(actor.id)},
        [{"type": "add_comment", "text": "Reply to {work_item_identifier}: {actor_name}"}],
    )
    with pytest.raises(ValueError), transaction.atomic():
        IssueComment.objects.create(project=project, issue=issue, actor=actor, comment_html="<p>Rollback</p>")
        raise ValueError
    assert not ProjectAutomationEvent.objects.exists()
    IssueComment.objects.create(project=project, issue=issue, actor=actor, comment_html="<p>Hello</p>")
    event = ProjectAutomationEvent.objects.get()
    process_event(event.id)
    assert IssueComment.objects.filter(issue=issue).count() == 2
    assert ProjectAutomationEvent.objects.count() == 1


def test_real_relation_event_preserves_blocking_direction_and_deduplicates(runtime):
    project, actor, task = runtime
    bug = Issue.objects.create(project=project, name="Bug", state=task.state)
    rule_for(
        runtime, "work_item_linked", {"relation_type": "blocking", "source_id": str(bug.id), "target_id": str(task.id)}
    )
    for _ in range(2):
        bulk_create_relations(
            [
                IssueRelation(
                    project=project,
                    workspace=project.workspace,
                    issue=task,
                    related_issue=bug,
                    relation_type="blocked_by",
                    created_by=actor,
                )
            ],
            ignore_conflicts=True,
        )
    event = ProjectAutomationEvent.objects.get()
    assert event.context["source_id"] == str(bug.id)
    assert event.context["stored_issue_id"] == str(task.id)
    process_event(event.id)
    assert IssueComment.objects.filter(issue=task).count() == 1
    assert not IssueComment.objects.filter(issue=bug).exists()


def create_bug_rule(runtime):
    project, _, issue = runtime
    bug_type = IssueType.objects.create(workspace=project.workspace, name="Bug")
    ProjectIssueType.objects.create(project=project, issue_type=bug_type)
    testing = State.objects.create(project=project, name="In Testing", group="started", color="#123456")
    issue.state = testing
    issue.save()
    rule = rule_for(
        runtime,
        "state_changed",
        {"from_state": str(testing.id)},
        [
            {
                "type": "create_work_item",
                "type_id": str(bug_type.id),
                "title": "Bug: {work_item_title}",
                "description": "Failure <script>x</script>",
                "priority": "high",
                "state_id": str(testing.id),
                "relation": "blocking",
            }
        ],
    )
    before = capture_context(project.id, issue)
    issue.state = State.objects.create(project=project, name="In Progress", group="started", color="#123456")
    issue.save()
    return rule, emit_event(issue, before)


def test_failed_testing_creates_bug_blocks_source_without_completing_source(runtime):
    _, _, issue = runtime
    _, event = create_bug_rule(runtime)
    process_event(event.id)
    process_event(event.id)
    bug = Issue.objects.get(name="Bug: Automation item")
    assert IssueRelation.objects.filter(issue=issue, related_issue=bug, relation_type="blocked_by").count() == 1
    issue.refresh_from_db()
    assert issue.state.group == "started"
    assert ProjectAutomationExecution.objects.get(event=event).status == "success"
    assert ProjectAutomationEvent.objects.count() == 1


def test_relation_failure_retries_existing_bug_instead_of_creating_another(runtime):
    _, event = create_bug_rule(runtime)
    with patch(
        "plane.services.automation_runtime.create_relation", side_effect=OperationalError("Temporary relation failure")
    ):
        with pytest.raises(OperationalError):
            process_event(event.id)
    created_id = Issue.objects.get(name="Bug: Automation item").id
    assert not IssueRelation.objects.exists()
    process_event(event.id)
    assert Issue.objects.get(name="Bug: Automation item").id == created_id
    assert IssueRelation.objects.count() == 1


def test_add_and_remove_dependency_actions_are_directional_and_idempotent(runtime):
    project, _, source = runtime
    target = Issue.objects.create(project=project, name="Target", state=source.state)
    actions = [
        {
            "type": "add_dependency",
            "relation_type": "blocking",
            "source_mode": "triggering",
            "target_mode": "specific",
            "target_id": str(target.id),
        },
        {
            "type": "remove_dependency",
            "relation_type": "blocking",
            "source_mode": "triggering",
            "target_mode": "specific",
            "target_id": str(target.id),
        },
    ]
    _, event = make_event(runtime, actions)

    process_event(event.id)

    assert not IssueRelation.objects.filter(issue=target, related_issue=source, relation_type="blocked_by").exists()
    execution = ProjectAutomationExecution.objects.get(event=event)
    assert execution.status == "success"
    assert execution.snapshot["steps"][str(execution.rule_id)]["0"]["source_issue_id"] == str(source.id)


def test_dependency_action_can_use_work_item_created_by_previous_action(runtime):
    project, _, source = runtime
    bug_type = IssueType.objects.create(workspace=project.workspace, name="Regression Bug")
    ProjectIssueType.objects.create(project=project, issue_type=bug_type)
    actions = [
        {
            "type": "create_work_item",
            "type_id": str(bug_type.id),
            "title": "Created dependency",
            "priority": "high",
        },
        {
            "type": "add_dependency",
            "relation_type": "blocking",
            "source_mode": "created",
            "target_mode": "triggering",
        },
    ]
    _, event = make_event(runtime, actions)

    process_event(event.id)

    created = Issue.objects.get(name="Created dependency")
    assert IssueRelation.objects.filter(issue=source, related_issue=created, relation_type="blocked_by").exists()


def test_remove_label_and_fixed_due_date(runtime):
    project, _, issue = runtime
    label = Label.objects.create(project=project, name="Review")
    IssueLabel.objects.create(project=project, issue=issue, label=label)
    _, event = make_event(
        runtime,
        [
            {"type": "manage_labels", "operation": "remove", "label_id": str(label.id)},
            {"type": "set_due_date", "mode": "fixed", "date": "2027-12-15"},
        ],
    )
    process_event(event.id)
    issue.refresh_from_db()
    assert str(issue.target_date) == "2027-12-15"
    assert not IssueLabel.objects.filter(issue=issue).exists()


@pytest.mark.parametrize(
    "days,operator,value,expected",
    [
        (-1, "overdue", None, True),
        (1, "overdue", None, False),
        (2, "within_next_days", "3", True),
        (4, "within_next_days", "3", False),
        (None, "is_empty", None, True),
    ],
)
def test_due_date_conditions(runtime, days, operator, value, expected):
    project, _, issue = runtime
    from zoneinfo import ZoneInfo

    issue.target_date = (
        timezone.now().astimezone(ZoneInfo(project.timezone)).date() + timedelta(days=days)
        if days is not None
        else None
    )
    issue.save()
    condition = {"field": "due_date", "operator": operator}
    if value is not None:
        condition["value"] = value
    _, event = make_event(runtime, [{"type": "change_priority", "priority": "urgent"}], [condition])
    process_event(event.id)
    issue.refresh_from_db()
    assert (issue.priority == "urgent") is expected


def test_scheduled_bounded_batches_stable_occurrence_and_no_retroactive_enable(runtime):
    project, _, issue = runtime
    now = timezone.now()
    Issue.objects.filter(pk=issue.pk).update(created_at=now - timedelta(days=3))
    rule = rule_for(runtime, "scheduled", {"frequency": "daily", "time": "00:00", "timezone": "UTC", "filters": []})
    dispatch_schedules(now)
    dispatch_schedules(now)
    event = ProjectAutomationEvent.objects.get()
    process_event(event.id)
    dispatch_schedules(now)
    assert IssueComment.objects.filter(issue=issue).count() == 1
    assert ProjectAutomationEvent.objects.count() == 1
    rule.enabled_at = now
    rule.schedule_cursor = {}
    rule.revision += 1
    rule.save()
    dispatch_schedules(now)
    assert ProjectAutomationEvent.objects.count() == 1


def test_schedule_processes_only_one_bounded_batch_at_a_time(runtime):
    project, _, issue = runtime
    now = timezone.now()
    for index in range(4):
        Issue.objects.create(project=project, state=issue.state, name=f"Batch {index}")
    Issue.objects.filter(project=project).update(created_at=now - timedelta(days=3))
    rule_for(runtime, "scheduled", {"frequency": "daily", "time": "00:00", "timezone": "UTC", "filters": []})
    with patch("plane.services.automation_schedule.BATCH_SIZE", 2):
        dispatch_schedules(now)
        assert ProjectAutomationEvent.objects.count() == 2
        dispatch_schedules(now)
        assert ProjectAutomationEvent.objects.count() == 4
        dispatch_schedules(now)
        assert ProjectAutomationEvent.objects.count() == 5
