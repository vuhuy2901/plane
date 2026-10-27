from copy import deepcopy
from uuid import uuid4

import pytest
from rest_framework.exceptions import ValidationError

from plane.services.automation_definition import AutomationDefinitionInput, TEMPLATES, instantiate_template

pytestmark = pytest.mark.unit


def definition():
    return {"name": "New rule", "trigger": "created", "actions": [{"type": "assign_user", "mode": "project_lead"}]}


def validate(data):
    serializer = AutomationDefinitionInput(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


@pytest.mark.parametrize("trigger", ["created", "state_changed", "priority_changed", "assignee_changed", "completed"])
def test_all_five_triggers_default_to_disabled(trigger):
    rule = validate({**definition(), "trigger": trigger})
    assert rule["enabled"] is False
    assert rule["actions"][0]["only_if_unassigned"] is True


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda item: item["id"])
def test_six_templates_are_valid_disabled_and_do_not_mutate_catalog(template):
    before = deepcopy(TEMPLATES)
    params = {
        "type_id": str(uuid4()),
        "label_id": str(uuid4()),
        "member_id": str(uuid4()),
        "state_id": str(uuid4()),
        "days": 3,
        "bug_type_id": str(uuid4()),
        "from_state": str(uuid4()),
        "to_state": str(uuid4()),
    }
    rule = instantiate_template(template["id"], params)
    assert not rule["enabled"]
    assert len(rule["conditions"]) <= 3
    assert len(rule["actions"]) <= 2
    assert TEMPLATES == before


@pytest.mark.parametrize(
    "patch",
    [
        {"trigger": ["created", "completed"]},
        {"trigger": "webhook"},
        {"actions": []},
        {"conditions": [{"field": "assignee", "operator": "is_empty"}] * 4},
        {"actions": [{"type": "change_priority", "priority": "high"}] * 3},
        {"conditions": [{"field": "priority", "operator": "contains", "value": "high"}]},
        {"conditions": [{"field": "state", "operator": "equals", "value": "invalid"}]},
        {"conditions": [{"field": "assignee", "operator": "is_empty", "value": str(uuid4())}]},
        {"actions": [{"type": "assign_user", "mode": "specific_member"}]},
        {"actions": [{"type": "set_due_date", "days": -1}]},
        {"actions": [{"type": "set_due_date", "days": "not a number"}]},
        {"actions": [{"type": "change_state", "state_id": str(uuid4()), "priority": "urgent"}]},
        {"actions": [{"type": "add_comment", "text": ""}]},
        {"branches": []},
        {"operator": "OR"},
    ],
)
def test_unsupported_or_incomplete_configurations_are_rejected(patch):
    with pytest.raises(ValidationError):
        validate({**definition(), **patch})


@pytest.mark.parametrize("mode", ["specific_member", "project_lead", "creator"])
def test_assignment_modes(mode):
    action = {"type": "assign_user", "mode": mode, "only_if_unassigned": False}
    if mode == "specific_member":
        action["member_id"] = str(uuid4())
    rule = validate({**definition(), "actions": [action]})
    assert rule["actions"][0] == action


def test_template_requires_explicit_project_resources():
    with pytest.raises(ValidationError):
        instantiate_template("auto_assign_bug", {})
    with pytest.raises(ValidationError):
        instantiate_template("unknown", {})


@pytest.mark.parametrize(
    "patch",
    [
        {"actions": [{"type": "assign_user", "mode": "project_lead", "round_robin": True}]},
        {"conditions": [{"field": "assignee", "operator": "is_empty", "OR": []}]},
    ],
)
def test_nested_advanced_options_are_not_silently_dropped(patch):
    with pytest.raises(ValidationError):
        validate({**definition(), **patch})
