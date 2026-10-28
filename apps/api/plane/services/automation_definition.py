"""Strict configuration contract. Legacy aliases are read, never advertised."""

from copy import deepcopy
from datetime import date, time
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers
from plane.services.automation_config import MAX_ACTIONS, MAX_CONDITIONS

TRIGGERS = (
    "created",
    "updated",
    "state_changed",
    "assignee_changed",
    "priority_changed",
    "comment_added",
    "work_item_linked",
    "scheduled",
)
PRIORITIES = ("none", "low", "medium", "high", "urgent")
STATE_GROUPS = ("backlog", "unstarted", "started", "completed", "cancelled")
UPDATE_FIELDS = (
    "name",
    "description_html",
    "work_item_type",
    "state",
    "priority",
    "assignee",
    "label",
    "start_date",
    "target_date",
    "parent_id",
    "estimate_point",
)
RELATIONS = (
    "blocking",
    "blocked_by",
    "relates_to",
    "duplicate",
    "start_before",
    "start_after",
    "finish_before",
    "finish_after",
    "implemented_by",
    "implements",
)
OPERATORS = {
    "work_item_type": ("equals", "not_equals", "is_empty", "is_not_empty"),
    "state": ("equals", "not_equals", "is_empty", "is_not_empty"),
    "priority": ("equals", "not_equals", "is_empty", "is_not_empty"),
    "assignee": ("equals", "not_equals", "contains", "does_not_contain", "is_empty", "is_not_empty"),
    "label": ("equals", "not_equals", "contains", "does_not_contain", "is_empty", "is_not_empty"),
    "due_date": ("equals", "not_equals", "is_empty", "is_not_empty", "overdue", "within_next_days"),
    "ALL_SUBTASKS_COMPLETED": ("is_true",),
}
ACTIONS = (
    "assign_user",
    "change_state",
    "change_priority",
    "manage_labels",
    "add_comment",
    "set_due_date",
    "create_work_item",
    "add_dependency",
    "remove_dependency",
)


def require_uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise serializers.ValidationError("Select a valid resource ID.") from exc


def normalize_definition(data):
    result = deepcopy(data)
    if not isinstance(result, dict):
        return result
    legacy = result.get("trigger")
    if legacy in ("completed", "SUBTASK_COMPLETED"):
        result["trigger"] = "state_changed"
        result["trigger_options"] = {"to_group": "completed", "enter_group_only": True}
        if legacy == "SUBTASK_COMPLETED":
            result["trigger_options"]["subtask_only"] = True
    for action in result.get("actions", []):
        if action.get("type") == "CHANGE_PARENT_STATE":
            action.update(type="change_state", target="parent")
        elif action.get("type") == "add_label":
            action.update(type="manage_labels", operation="add")
    return result


class StrictInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected a configuration object.")
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({name: "Unknown configuration field." for name in sorted(unknown)})
        return super().to_internal_value(data)


class ConditionInput(StrictInput):
    field = serializers.ChoiceField(choices=tuple(OPERATORS))
    operator = serializers.CharField()
    value = serializers.CharField(required=False, allow_blank=False)

    def validate(self, attrs):
        field, operator = attrs["field"], attrs["operator"]
        if operator not in OPERATORS[field]:
            raise serializers.ValidationError({"operator": "Unsupported operator for this field."})
        if operator in ("is_empty", "is_not_empty", "overdue", "is_true"):
            if "value" in attrs:
                raise serializers.ValidationError("This operator does not accept a value.")
        elif "value" not in attrs:
            raise serializers.ValidationError({"value": "Select a comparison value."})
        elif field == "priority":
            if attrs["value"] not in PRIORITIES:
                raise serializers.ValidationError("Unknown priority.")
        elif field == "due_date":
            try:
                if operator == "within_next_days":
                    if not 0 <= int(attrs["value"]) <= 3650:
                        raise ValueError
                else:
                    date.fromisoformat(attrs["value"])
            except ValueError as exc:
                raise serializers.ValidationError("Select a valid date or day count.") from exc
        elif field == "state" and attrs["value"].startswith("group:"):
            if attrs["value"][6:] not in STATE_GROUPS:
                raise serializers.ValidationError("Unknown state group.")
        else:
            attrs["value"] = require_uuid(attrs["value"])
        return attrs


class ActionInput(StrictInput):
    type = serializers.ChoiceField(choices=ACTIONS)
    mode = serializers.CharField(required=False)
    member_id = serializers.UUIDField(required=False)
    only_if_unassigned = serializers.BooleanField(required=False)
    replace_assignees = serializers.BooleanField(required=False)
    state_id = serializers.UUIDField(required=False)
    priority = serializers.ChoiceField(choices=PRIORITIES, required=False)
    label_id = serializers.UUIDField(required=False)
    operation = serializers.ChoiceField(choices=("add", "remove"), required=False)
    text = serializers.CharField(max_length=10000, required=False)
    days = serializers.IntegerField(min_value=0, max_value=3650, required=False)
    date = serializers.DateField(required=False)
    timezone = serializers.CharField(required=False)
    target = serializers.ChoiceField(choices=("current", "parent"), required=False)
    type_id = serializers.UUIDField(required=False)
    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(max_length=50000, required=False, allow_blank=True)
    relation = serializers.ChoiceField(choices=RELATIONS, required=False)
    parent_mode = serializers.ChoiceField(choices=("none", "source"), required=False)
    relation_type = serializers.ChoiceField(choices=RELATIONS, required=False)
    source_mode = serializers.ChoiceField(choices=("triggering", "parent", "created", "specific"), required=False)
    source_id = serializers.UUIDField(required=False)
    target_mode = serializers.ChoiceField(choices=("triggering", "parent", "created", "specific"), required=False)
    target_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        kind = attrs["type"]
        fields = {
            "assign_user": {"mode", "member_id", "only_if_unassigned", "replace_assignees"},
            "change_state": {"state_id", "target"},
            "change_priority": {"priority"},
            "manage_labels": {"label_id", "operation"},
            "add_comment": {"text"},
            "set_due_date": {"mode", "days", "date", "timezone"},
            "create_work_item": {
                "type_id",
                "title",
                "description",
                "priority",
                "state_id",
                "member_id",
                "relation",
                "parent_mode",
            },
            "add_dependency": {"relation_type", "source_mode", "source_id", "target_mode", "target_id"},
            "remove_dependency": {"relation_type", "source_mode", "source_id", "target_mode", "target_id"},
        }[kind]
        if attrs.get("target") == "current" and kind != "change_state":
            attrs.pop("target")
        if set(attrs) - fields - {"type"}:
            raise serializers.ValidationError("This action contains parameters for a different action.")
        required = {
            "assign_user": {"mode"},
            "change_state": {"state_id"},
            "change_priority": {"priority"},
            "manage_labels": {"label_id", "operation"},
            "add_comment": {"text"},
            "set_due_date": set(),
            "create_work_item": {"type_id", "title", "priority"},
            "add_dependency": {"relation_type", "source_mode", "target_mode"},
            "remove_dependency": {"relation_type", "source_mode", "target_mode"},
        }[kind]
        if not required.issubset(attrs):
            raise serializers.ValidationError("Complete the required action parameters.")
        if kind == "assign_user":
            mode = attrs["mode"]
            if mode not in ("specific_member", "project_lead", "creator"):
                raise serializers.ValidationError("Select an assignment mode.")
            if (mode == "specific_member") != ("member_id" in attrs):
                raise serializers.ValidationError("Select a member only for Specific Member assignment.")
            attrs.setdefault("only_if_unassigned", True)
        if kind == "set_due_date":
            mode = attrs.get("mode", "relative")
            if mode not in ("fixed", "relative") or ("date" if mode == "fixed" else "days") not in attrs:
                raise serializers.ValidationError("Select a fixed date or a relative day count.")
            if (mode == "fixed" and "days" in attrs) or (mode == "relative" and "date" in attrs):
                raise serializers.ValidationError("Select only one due date mode.")
        if "timezone" in attrs:
            validate_zone(attrs["timezone"])
        if kind in ("add_dependency", "remove_dependency"):
            for side in ("source", "target"):
                mode = attrs[f"{side}_mode"]
                has_id = f"{side}_id" in attrs
                if (mode == "specific") != has_id:
                    raise serializers.ValidationError(
                        {f"{side}_id": f"Select a Work Item only for the Specific {side.title()} mode."}
                    )
            if attrs["source_mode"] == attrs["target_mode"] and attrs["source_mode"] != "specific":
                raise serializers.ValidationError("Source and target must resolve to different Work Items.")
            if attrs.get("source_id") and attrs.get("source_id") == attrs.get("target_id"):
                raise serializers.ValidationError("Source and target must be different Work Items.")
        return {key: str(value) if isinstance(value, (UUID, date)) else value for key, value in attrs.items()}


def validate_zone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise serializers.ValidationError("Select a valid time zone.") from exc


def validate_trigger(trigger, options):
    allowed = {
        "created": {"type_id"},
        "updated": {"field"},
        "state_changed": {"from_state", "to_state", "from_group", "to_group", "enter_group_only", "subtask_only"},
        "priority_changed": {"from_priority", "to_priority"},
        "assignee_changed": {"previous_assignee", "new_assignee"},
        "comment_added": {"author_id"},
        "work_item_linked": {"relation_type", "source_id", "target_id"},
        "scheduled": {"frequency", "time", "timezone", "weekday", "filters"},
    }[trigger]
    if set(options) - allowed:
        raise serializers.ValidationError("Unsupported trigger configuration.")
    for key, value in options.items():
        if key in {"type_id", "from_state", "to_state", "author_id", "source_id", "target_id"}:
            options[key] = require_uuid(value)
        elif key in {"previous_assignee", "new_assignee"} and value != "unassigned":
            options[key] = require_uuid(value)
        elif key in {"from_priority", "to_priority"} and value not in PRIORITIES:
            raise serializers.ValidationError("Unknown priority.")
        elif key in {"from_group", "to_group"} and value not in STATE_GROUPS:
            raise serializers.ValidationError("Unknown state group.")
        elif key in {"enter_group_only", "subtask_only"} and type(value) is not bool:
            raise serializers.ValidationError("Expected true or false.")
        elif key == "field" and value not in UPDATE_FIELDS:
            raise serializers.ValidationError("Unsupported updated field.")
        elif key == "relation_type" and value not in RELATIONS:
            raise serializers.ValidationError("Unsupported work item relation.")
    if trigger == "scheduled":
        try:
            if options.get("frequency") not in ("daily", "weekly"):
                raise ValueError
            clock = time.fromisoformat(options.get("time", ""))
            if clock.tzinfo or clock.second or clock.microsecond:
                raise ValueError
            if options["frequency"] == "weekly" and (
                type(options.get("weekday")) is not int or not 0 <= options["weekday"] <= 6
            ):
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError(
                "Configure a daily or weekly schedule with a valid execution time."
            ) from exc
        validate_zone(options.get("timezone"))
        filters = ConditionInput(data=options.get("filters", []), many=True, max_length=MAX_CONDITIONS)
        filters.is_valid(raise_exception=True)
        if any(c["field"] == "ALL_SUBTASKS_COMPLETED" for c in filters.validated_data):
            raise serializers.ValidationError("Scheduled filters cannot evaluate parent completion.")
        options["filters"] = list(filters.validated_data)
    return options


class AutomationDefinitionInput(StrictInput):
    schema_version = serializers.ChoiceField(choices=(1,), default=1)
    name = serializers.CharField(max_length=255)
    enabled = serializers.BooleanField(default=False)
    trigger = serializers.ChoiceField(choices=TRIGGERS)
    trigger_options = serializers.DictField(required=False)
    conditions = ConditionInput(many=True, max_length=MAX_CONDITIONS, default=list)
    actions = ActionInput(many=True, min_length=1, max_length=MAX_ACTIONS)

    def to_internal_value(self, data):
        return super().to_internal_value(normalize_definition(data))

    def validate(self, attrs):
        if "trigger_options" in attrs or attrs["trigger"] == "scheduled":
            attrs["trigger_options"] = validate_trigger(attrs["trigger"], attrs.get("trigger_options", {}))
        parent = any(a["type"] == "change_state" and a.get("target") == "parent" for a in attrs["actions"])
        family = any(c["field"] == "ALL_SUBTASKS_COMPLETED" for c in attrs["conditions"])
        if (parent or family) and attrs["trigger"] != "state_changed":
            raise serializers.ValidationError("Parent automation requires a State Changed trigger.")
        if parent and not family:
            raise serializers.ValidationError("Changing parent state requires All Subtasks Completed.")
        created_available = False
        for index, action in enumerate(attrs["actions"]):
            if action["type"] == "create_work_item":
                created_available = True
            if (
                action["type"] in ("add_dependency", "remove_dependency")
                and "created"
                in (
                    action["source_mode"],
                    action["target_mode"],
                )
                and not created_available
            ):
                raise serializers.ValidationError(
                    {"actions": {index: "Created Work Item requires a Create Work Item action earlier in the rule."}}
                )
        return attrs


TEMPLATES = (
    {
        "id": "auto_assign",
        "name": "Auto Assign New Work Item",
        "description": "Assign an unassigned new Work Item to a selected member.",
        "category": "Assignment",
        "requires": ["member_id"],
        "trigger": "created",
        "conditions": [{"field": "assignee", "operator": "is_empty"}],
        "actions": [
            {"type": "assign_user", "mode": "specific_member", "member_id": "$member_id", "only_if_unassigned": True}
        ],
    },
    {
        "id": "critical_bug",
        "name": "Escalate Critical Bug",
        "description": "Escalate Bugs with the selected critical label to Urgent.",
        "category": "Priority",
        "requires": ["type_id", "label_id"],
        "trigger": "created",
        "conditions": [
            {"field": "work_item_type", "operator": "equals", "value": "$type_id"},
            {"field": "label", "operator": "contains", "value": "$label_id"},
        ],
        "actions": [{"type": "change_priority", "priority": "urgent"}],
    },
    {
        "id": "testing_rejected",
        "name": "Testing Rejected – Create Bug",
        "description": "Create a Bug that blocks the source Task after testing is rejected. "
        "The Bug is a child of the source Task. Select the Task type, Bug type and actual workflow states.",
        "category": "Quality",
        "requires": ["type_id", "bug_type_id", "from_state", "to_state"],
        "trigger": "state_changed",
        "trigger_options": {"from_state": "$from_state", "to_state": "$to_state"},
        "conditions": [{"field": "work_item_type", "operator": "equals", "value": "$type_id"}],
        "actions": [
            {
                "type": "create_work_item",
                "type_id": "$bug_type_id",
                "title": "Testing rejected: {work_item_title}",
                "parent_mode": "source",
                "description": "Follow up on {work_item_identifier}.",
                "priority": "high",
                "relation": "blocking",
            }
        ],
    },
    {
        "id": "all_subtasks_completed",
        "name": "All Subtasks Completed",
        "description": "Move the Parent Work Item to your selected valid acceptance state "
        "when every direct Subtask is completed.",
        "category": "Parent and Subtasks",
        "requires": ["type_id", "state_id"],
        "trigger": "state_changed",
        "trigger_options": {"to_group": "completed", "enter_group_only": True, "subtask_only": True},
        "conditions": [
            {"field": "work_item_type", "operator": "equals", "value": "$type_id"},
            {"field": "ALL_SUBTASKS_COMPLETED", "operator": "is_true"},
        ],
        "actions": [{"type": "change_state", "target": "parent", "state_id": "$state_id"}],
    },
    {
        "id": "request_acceptance",
        "name": "Request Acceptance",
        "description": "Request review when a Work Item enters the selected acceptance state.",
        "category": "Review",
        "requires": ["state_id"],
        "trigger": "state_changed",
        "trigger_options": {"to_state": "$state_id"},
        "conditions": [],
        "actions": [{"type": "add_comment", "text": "This work item is ready for review."}],
    },
    {
        "id": "blocking_dependency",
        "name": "Notify on New Blocking Dependency",
        "description": "Comment on the blocked Work Item when a blocking dependency is created.",
        "category": "Dependencies",
        "requires": [],
        "trigger": "work_item_linked",
        "trigger_options": {"relation_type": "blocking"},
        "conditions": [],
        "actions": [{"type": "add_comment", "text": "A new blocking dependency affects {work_item_identifier}."}],
    },
    {
        "id": "overdue_followup",
        "name": "Overdue Work Item Follow-up",
        "description": "Comment once per daily occurrence on overdue, incomplete Work Items.",
        "category": "Schedules",
        "requires": [],
        "trigger": "scheduled",
        "trigger_options": {"frequency": "daily", "time": "09:00", "timezone": "Asia/Bangkok", "filters": []},
        "conditions": [
            {"field": "due_date", "operator": "overdue"},
            {"field": "state", "operator": "not_equals", "value": "group:completed"},
        ],
        "actions": [{"type": "add_comment", "text": "This work item is overdue and requires attention."}],
    },
)


def instantiate_template(template_id, parameters):
    template = next((item for item in TEMPLATES if item["id"] == template_id), None)
    if template is None:
        raise serializers.ValidationError("Unknown automation template.")
    missing = set(template["requires"]) - set(parameters)
    if missing:
        raise serializers.ValidationError({name: "Configure this template parameter." for name in sorted(missing)})

    def resolve(value):
        if isinstance(value, str) and value.startswith("$"):
            return parameters[value[1:]]
        if isinstance(value, dict):
            return {key: resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve(item) for item in value]
        return value

    data = resolve({key: value for key, value in template.items() if key in AutomationDefinitionInput().fields})
    serializer = AutomationDefinitionInput(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data
