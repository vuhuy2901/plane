"""Dry runs explain recorded events without executing or inventing transitions."""

import re
from copy import deepcopy
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from plane.db.models import (
    Issue,
    IssueAssignee,
    IssueRelation,
    IssueType,
    ProjectAutomationEvent,
    ProjectAutomationExecution,
    ProjectAutomationRule,
    ProjectIssueType,
    State,
)
from plane.services.automation_runtime import evaluate_rule, process_event, snapshot
from plane.tests.contract.app.test_automation_rules_api import automation_api as automation_api_fixture
from plane.tests.factories import ProjectFactory, UserFactory

pytestmark = [pytest.mark.contract, pytest.mark.django_db]
automation_api = automation_api_fixture


def create_rule(automation_api, **overrides):
    client, _, base, _ = automation_api
    response = client.post(
        base + "rules/",
        {
            "name": "Diagnostic preview",
            "trigger": "created",
            "conditions": [],
            "actions": [{"type": "add_comment", "text": "Preview only"}],
            **overrides,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    return ProjectAutomationRule.objects.get(pk=response.data["id"])


def preview(automation_api, rule, payload):
    client, _, base, _ = automation_api
    with CaptureQueriesContext(connection) as queries:
        response = client.post(base + f"rules/{rule.id}/test/", payload, format="json")
    writes = [query["sql"] for query in queries if re.match(r"\s*(INSERT|UPDATE|DELETE)\b", query["sql"], re.I)]
    assert writes == [], "A dry run must not execute database writes, even writes later rolled back."
    return response


def recorded_event(project, issue, *, before=None, after=None, triggers=None, context=None):
    return ProjectAutomationEvent.objects.create(
        project=project,
        issue=issue,
        snapshot=after if after is not None else snapshot(issue),
        before_snapshot=before,
        triggers=triggers or ["created"],
        context=context or {},
        processed_at=timezone.now(),
    )


@pytest.mark.parametrize("matching_type", [True, False])
def test_simulated_created_checks_type_filter_without_creating_bug(automation_api, matching_type):
    _, project, _, _ = automation_api
    task = IssueType.objects.create(workspace=project.workspace, name="Task")
    bug = IssueType.objects.create(workspace=project.workspace, name="Bug")
    for kind in (task, bug):
        ProjectIssueType.objects.create(project=project, issue_type=kind)
    issue = Issue.objects.create(project=project, type=task, name="Existing Task")
    selected_type = task if matching_type else bug
    rule = create_rule(
        automation_api,
        trigger_options={"type_id": str(selected_type.id)},
        actions=[
            {
                "type": "create_work_item",
                "type_id": str(bug.id),
                "title": "Bug",
                "priority": "high",
                "relation": "blocking",
            }
        ],
    )
    original_issue = Issue.objects.filter(pk=issue.pk).values().get()
    original_rule = ProjectAutomationRule.objects.filter(pk=rule.pk).values().get()

    response = preview(automation_api, rule, {"issue_id": str(issue.id)})

    assert response.status_code == 200, response.data
    data = response.data
    assert data["valid"] is True
    assert data["preview_mode"] == "simulated_created"
    assert data.get("event_id") is None
    assert data["trigger_match"] is matching_type
    assert data["conditions_match"] is True
    assert data["evaluation"]["matched"] is matching_type
    assert data["evaluation"]["trigger"]["expected"] == "created"
    assert data["evaluation"]["trigger"]["actual"] == ["created"]
    check = next(check for check in data["evaluation"]["trigger"]["checks"] if check["field"] == "work_item_type")
    assert check["expected"] == str(selected_type.id)
    assert check["actual"] == str(task.id)
    assert check["matched"] is matching_type
    assert data["action_count"] == int(matching_type)
    assert data["writes"] == 0
    assert Issue.objects.filter(pk=issue.pk).values().get() == original_issue
    assert ProjectAutomationRule.objects.filter(pk=rule.pk).values().get() == original_rule
    assert Issue.objects.filter(project=project).count() == 1
    assert not IssueRelation.objects.exists()
    assert not ProjectAutomationEvent.objects.exists()
    assert not ProjectAutomationExecution.objects.exists()


def test_condition_failure_returns_diagnostics_and_zero_actions(automation_api):
    _, project, _, _ = automation_api
    issue = Issue.objects.create(project=project, name="Normal priority", priority="none")
    rule = create_rule(
        automation_api,
        conditions=[
            {"field": "priority", "operator": "equals", "value": "urgent"},
            {"field": "assignee", "operator": "is_empty"},
        ],
    )

    response = preview(automation_api, rule, {"issue_id": str(issue.id)})

    assert response.status_code == 200, response.data
    data = response.data
    assert data["trigger_match"] is True
    assert data["conditions_match"] is False
    assert data["evaluation"]["matched"] is False
    priority, assignee = data["evaluation"]["conditions"]
    assert priority == {
        "field": "priority",
        "operator": "equals",
        "expected": "urgent",
        "actual": "none",
        "matched": False,
    }
    assert assignee["matched"] is True
    assert "priority" in data["reason"]
    assert "urgent" in data["reason"]
    assert "none" in data["reason"]
    assert data["action_count"] == data["writes"] == 0


@pytest.mark.parametrize(
    "trigger,options",
    [
        ("updated", {"field": "name"}),
        ("state_changed", {"to_group": "started"}),
        ("priority_changed", {"to_priority": "urgent"}),
        ("assignee_changed", {"previous_assignee": "unassigned"}),
        ("comment_added", {}),
        ("work_item_linked", {"relation_type": "blocking"}),
        ("scheduled", {"frequency": "daily", "time": "00:00", "timezone": "UTC", "filters": []}),
    ],
)
def test_current_snapshot_does_not_invent_non_created_events(automation_api, trigger, options):
    _, project, _, _ = automation_api
    state = State.objects.create(project=project, name="InProgress", group="started", color="#123456")
    issue = Issue.objects.create(project=project, name="Current item", priority="urgent", state=state)
    rule = create_rule(automation_api, trigger=trigger, trigger_options=options)

    response = preview(automation_api, rule, {"issue_id": str(issue.id)})

    assert response.status_code == 200, response.data
    data = response.data
    assert data["preview_mode"] == "current_snapshot"
    assert data.get("event_id") is None
    assert data["trigger_match"] is False
    assert data["evaluation"]["matched"] is False
    assert data["evaluation"]["trigger"]["actual"] == []
    assert data["action_count"] == data["writes"] == 0
    assert "trigger" in data["reason"].lower()
    assert not ProjectAutomationEvent.objects.exists()
    assert not ProjectAutomationExecution.objects.exists()


def test_latest_recorded_transition_and_explicit_older_event_use_frozen_snapshots(automation_api):
    _, project, _, _ = automation_api
    testing = State.objects.create(project=project, name="IN TESTING", group="started", color="#123456")
    progress = State.objects.create(project=project, name="InProgress", group="started", color="#123456")
    issue = Issue.objects.create(project=project, name="Task", state=testing)
    rule = create_rule(
        automation_api,
        trigger="state_changed",
        trigger_options={"from_state": str(testing.id), "to_state": str(progress.id)},
    )
    before = snapshot(issue)
    after = {**before, "state": str(progress.id)}
    older = recorded_event(project, issue, before=before, after=after, triggers=["updated", "state_changed"])
    latest = recorded_event(project, issue, before=after, after=before, triggers=["updated", "state_changed"])
    original_events = list(ProjectAutomationEvent.objects.order_by("id").values())

    latest_response = preview(automation_api, rule, {"issue_id": str(issue.id)})
    older_response = preview(automation_api, rule, {"issue_id": str(issue.id), "event_id": str(older.id)})

    for response, event, matched in ((latest_response, latest, False), (older_response, older, True)):
        assert response.status_code == 200, response.data
        data = response.data
        assert data["preview_mode"] == "recorded_event"
        assert data["event_id"] == str(event.id)
        assert data["trigger_match"] is matched
        assert data["evaluation"] == evaluate_rule(rule.definition, event, issue)
        assert data["action_count"] == int(matched)
        assert data["writes"] == 0
    assert list(ProjectAutomationEvent.objects.order_by("id").values()) == original_events
    issue.refresh_from_db()
    assert issue.state_id == testing.id
    assert not ProjectAutomationExecution.objects.exists()


def test_created_rule_does_not_replace_recorded_update_with_simulated_creation(automation_api):
    _, project, _, _ = automation_api
    issue = Issue.objects.create(project=project, name="Task")
    rule = create_rule(automation_api)
    event = recorded_event(project, issue, before=snapshot(issue), triggers=["updated"])

    response = preview(automation_api, rule, {"issue_id": str(issue.id)})

    assert response.status_code == 200, response.data
    assert response.data["preview_mode"] == "recorded_event"
    assert response.data["event_id"] == str(event.id)
    assert response.data["trigger_match"] is False
    assert response.data["action_count"] == 0


def test_latest_recorded_event_is_scoped_to_requested_issue_and_project(automation_api):
    _, project, _, _ = automation_api
    issue = Issue.objects.create(project=project, name="Requested Task")
    rule = create_rule(automation_api)
    selected = recorded_event(project, issue)
    other = Issue.objects.create(project=project, name="Other Task")
    recorded_event(project, other, triggers=["updated"])
    foreign_project = ProjectFactory(workspace=project.workspace, identifier="FOREIGN")
    foreign_issue = Issue.objects.create(project=foreign_project, name="Foreign Task")
    recorded_event(foreign_project, foreign_issue, triggers=["updated"])

    response = preview(automation_api, rule, {"issue_id": str(issue.id)})

    assert response.status_code == 200, response.data
    assert response.data["event_id"] == str(selected.id)
    assert response.data["trigger_match"] is True


@pytest.mark.parametrize("foreign_project", [False, True])
def test_explicit_event_from_another_issue_or_project_is_rejected(automation_api, foreign_project):
    _, project, _, _ = automation_api
    issue = Issue.objects.create(project=project, name="Requested Task")
    rule = create_rule(automation_api)
    other_project = ProjectFactory(workspace=project.workspace, identifier="FOREIGN") if foreign_project else project
    other = Issue.objects.create(project=other_project, name="Other Task")
    event = recorded_event(other_project, other)

    response = preview(automation_api, rule, {"issue_id": str(issue.id), "event_id": str(event.id)})

    assert response.status_code == 404, response.data


@pytest.mark.parametrize("payload", [{}, {"issue_id": "invalid"}, {"issue_id": str(uuid4())}])
def test_preview_requires_valid_existing_project_issue(automation_api, payload):
    rule = create_rule(automation_api)
    response = preview(automation_api, rule, payload)
    assert response.status_code == (404 if payload.get("issue_id") not in (None, "invalid") else 400), response.data


def test_invalid_event_id_is_rejected(automation_api):
    _, project, _, _ = automation_api
    issue = Issue.objects.create(project=project, name="Task")
    rule = create_rule(automation_api)
    response = preview(automation_api, rule, {"issue_id": str(issue.id), "event_id": "invalid"})
    assert response.status_code == 400, response.data


@pytest.mark.parametrize("include_comment", [False, True])
def test_action_count_excludes_already_assigned_skip(automation_api, create_user, include_comment):
    _, project, _, _ = automation_api
    issue = Issue.objects.create(project=project, name="Assigned Task")
    IssueAssignee.objects.create(project=project, issue=issue, assignee=create_user)
    actions = [
        {
            "type": "assign_user",
            "mode": "specific_member",
            "member_id": str(create_user.id),
            "only_if_unassigned": True,
        }
    ]
    if include_comment:
        actions.append({"type": "add_comment", "text": "Would execute"})
    rule = create_rule(automation_api, actions=actions)

    response = preview(automation_api, rule, {"issue_id": str(issue.id)})

    assert response.status_code == 200, response.data
    assert response.data["trigger_match"] is True
    assert response.data["conditions_match"] is True
    assert response.data["action_count"] == int(include_comment)
    assert response.data["writes"] == 0
    assert IssueAssignee.objects.filter(issue=issue).count() == 1
    if not include_comment:
        assert "already assigned" in response.data["reason"].lower()


def test_matching_rule_with_invalid_execution_actor_is_not_reported_as_success(automation_api):
    _, project, _, _ = automation_api
    issue = Issue.objects.create(project=project, name="Task")
    rule = create_rule(automation_api)
    rule.execution_actor = UserFactory(is_active=False)
    rule.save(update_fields=["execution_actor"])

    response = preview(automation_api, rule, {"issue_id": str(issue.id)})

    assert response.status_code == 200, response.data
    assert response.data["valid"] is False
    assert response.data["evaluation"]["matched"] is True
    assert response.data["trigger_match"] is True
    assert response.data["conditions_match"] is True
    assert "actor" in response.data["reason"].lower()
    assert response.data["action_count"] == response.data["writes"] == 0
    assert not ProjectAutomationEvent.objects.exists()
    assert not ProjectAutomationExecution.objects.exists()


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("parent_mode", [None, "source"])
def test_task_testing_to_inprogress_creates_bug_only_when_enabled(automation_api, enabled, parent_mode):
    client, project, base, _ = automation_api
    task_type = IssueType.objects.create(workspace=project.workspace, name="Task")
    bug_type = IssueType.objects.create(workspace=project.workspace, name="Bug")
    epic_type = IssueType.objects.create(workspace=project.workspace, name="Epic", is_epic=True)
    for kind in (task_type, bug_type, epic_type):
        ProjectIssueType.objects.create(project=project, issue_type=kind)
    testing = State.objects.create(project=project, name="IN TESTING", group="started", color="#123456")
    progress = State.objects.create(project=project, name="InProgress", group="started", color="#123456")
    epic = Issue.objects.create(project=project, type=epic_type, name="Parent Epic", state=testing)
    issue = Issue.objects.create(project=project, type=task_type, name="Task fails testing", state=testing, parent=epic)
    rule = create_rule(
        automation_api,
        trigger="state_changed",
        trigger_options={"from_state": str(testing.id), "to_state": str(progress.id)},
        conditions=[{"field": "work_item_type", "operator": "equals", "value": str(task_type.id)}],
        actions=[
            {
                "type": "create_work_item",
                "type_id": str(bug_type.id),
                "title": "Bug: {work_item_title}",
                "priority": "high",
                "relation": "blocking",
                **({"parent_mode": parent_mode} if parent_mode else {}),
            }
        ],
    )
    if enabled:
        response = client.post(base + f"rules/{rule.id}/status/", {"enabled": True}, format="json")
        assert response.status_code == 200, response.data
    issue_url = f"/api/workspaces/{project.workspace.slug}/projects/{project.id}/issues/{issue.id}/"

    response = client.patch(issue_url, {"state_id": str(progress.id)}, format="json")

    assert response.status_code == 204, response.data
    issue.refresh_from_db()
    assert issue.state_id == progress.id
    assert not Issue.objects.filter(project=project, type=bug_type).exists()
    if enabled:
        event = ProjectAutomationEvent.objects.get(issue=issue)
        assert event.before_snapshot["state"] == str(testing.id)
        assert event.snapshot["state"] == str(progress.id)
        assert {"updated", "state_changed"} <= set(event.triggers)
        frozen_event = deepcopy(event.snapshot)
        process_event(event.id)
        process_event(event.id)
        bug = Issue.objects.get(project=project, type=bug_type)
        assert bug.name == "Bug: Task fails testing"
        assert bug.priority == "high"
        assert bug.parent_id == (issue.id if parent_mode == "source" else None)
        children = client.get(issue_url + "sub-issues/")
        assert children.status_code == 200, children.data
        assert {str(child["id"]) for child in children.data["sub_issues"]} == (
            {str(bug.id)} if parent_mode == "source" else set()
        )
        assert IssueRelation.objects.filter(issue=issue, related_issue=bug, relation_type="blocked_by").count() == 1
        execution = ProjectAutomationExecution.objects.get(event=event, rule=rule)
        assert execution.status == "success"
        assert execution.snapshot["evaluation"]["matched"] is True
        event.refresh_from_db()
        assert event.snapshot == frozen_event
        assert event.progress[str(rule.id)]["0"]["created_issue_id"] == str(bug.id)
        assert ProjectAutomationEvent.objects.count() == 1
        assert ProjectAutomationExecution.objects.count() == 1
    else:
        assert not ProjectAutomationEvent.objects.exists()
        assert not ProjectAutomationExecution.objects.exists()
    issue.refresh_from_db()
    assert issue.state_id == progress.id
    assert issue.parent_id == epic.id
    assert not IssueAssignee.objects.filter(issue=issue).exists()
