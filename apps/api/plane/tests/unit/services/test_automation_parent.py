"""Created Bugs can retain their type while nesting under the source Task."""

from uuid import uuid4

import pytest
from rest_framework.exceptions import ValidationError

from plane.db.models import Issue, IssueType, ProjectIssueType, ProjectAutomationEvent, ProjectAutomationExecution
from plane.services.automation_definition import AutomationDefinitionInput, TEMPLATES
from plane.services.automation_runtime import process_event, prepare_actions
from plane.tests.unit.services.test_automation_runtime import runtime as runtime_fixture
from plane.tests.unit.services.test_automation_extended import create_bug_rule

runtime = runtime_fixture


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["none", "source"])
def test_create_action_accepts_explicit_placement(mode):
    serializer = AutomationDefinitionInput(
        data={
            "name": "Nested Bug",
            "trigger": "created",
            "actions": [
                {
                    "type": "create_work_item",
                    "type_id": str(uuid4()),
                    "title": "Bug",
                    "priority": "medium",
                    "parent_mode": mode,
                }
            ],
        }
    )
    serializer.is_valid(raise_exception=True)
    assert serializer.validated_data["actions"][0]["parent_mode"] == mode


@pytest.mark.unit
@pytest.mark.parametrize(
    "action",
    [
        {
            "type": "create_work_item",
            "type_id": str(uuid4()),
            "title": "Bug",
            "priority": "medium",
            "parent_mode": "arbitrary",
        },
        {"type": "assign_user", "mode": "project_lead", "parent_mode": "source"},
    ],
)
def test_placement_is_strict_and_only_valid_for_creation(action):
    serializer = AutomationDefinitionInput(
        data={"name": "Invalid placement", "trigger": "created", "actions": [action]}
    )
    with pytest.raises(ValidationError):
        serializer.is_valid(raise_exception=True)


@pytest.mark.unit
def test_testing_rejected_template_creates_child_bug():
    template = next(template for template in TEMPLATES if template["id"] == "testing_rejected")
    assert template["actions"][0]["parent_mode"] == "source"


@pytest.mark.unit
@pytest.mark.django_db
@pytest.mark.parametrize("mode", [None, "none", "source"])
def test_creation_placement_preserves_epic_task_bug_tree_and_deduplication(runtime, mode):
    project, _, source = runtime
    task_type = IssueType.objects.create(workspace=project.workspace, name="Task")
    epic_type = IssueType.objects.create(workspace=project.workspace, name="Epic", is_epic=True)
    for kind in (task_type, epic_type):
        ProjectIssueType.objects.create(project=project, issue_type=kind)
    epic = Issue.objects.create(project=project, type=epic_type, name="Epic", state=source.state)
    source.type, source.parent = task_type, epic
    source.save(update_fields=["type", "parent"])
    rule, event = create_bug_rule(runtime)
    if mode is not None:
        rule.definition["actions"][0]["parent_mode"] = mode
        rule.save(update_fields=["definition"])
    source_state = source.state_id

    # Preparing actions (including dry runs) does not create an issue or alter its parent.
    count = Issue.objects.count()
    prepared = prepare_actions(rule, source, event)
    assert Issue.objects.count() == count
    serializer, _ = prepared[0][1]
    assert getattr(serializer.validated_data.get("parent"), "id", None) == (source.id if mode == "source" else None)

    process_event(event.id)
    event.refresh_from_db()
    bug_id = event.progress[str(rule.id)]["0"]["created_issue_id"]
    bug = Issue.objects.select_related("parent").get(pk=bug_id)
    assert bug.type.name == "Bug"
    assert bug.parent_id == (source.id if mode == "source" else None)
    if mode == "source":
        assert bug.parent.parent_id == epic.id
        assert bug.project_id == source.project_id == epic.project_id
        assert Issue.issue_objects.filter(parent=source, id=bug.id).exists()
        assert not Issue.issue_objects.filter(parent__isnull=True, id=bug.id).exists()
    source.refresh_from_db()
    assert source.parent_id == epic.id
    assert source.state_id == source_state
    assert ProjectAutomationExecution.objects.get(event=event, rule=rule).status == "success"

    ProjectAutomationEvent.objects.filter(pk=event.pk).update(processed_at=None)
    process_event(event.id)
    assert Issue.objects.filter(project=project).count() == 3
    assert ProjectAutomationExecution.objects.filter(event=event, rule=rule).count() == 1
