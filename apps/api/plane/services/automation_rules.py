from rest_framework.exceptions import ValidationError

from plane.db.models import Issue, Label, ProjectIssueType, ProjectMember, State
from plane.services.automation_definition import AutomationDefinitionInput, normalize_definition


def validate_definition(project, data):
    serializer = AutomationDefinitionInput(data=data)
    serializer.is_valid(raise_exception=True)
    definition = dict(serializer.validated_data)
    definition.pop("enabled", None)
    options = definition.get("trigger_options", {})
    resources = list(definition["conditions"]) + list(options.get("filters", []))
    for key, field in {
        "type_id": "work_item_type",
        "from_state": "state",
        "to_state": "state",
        "author_id": "assignee",
        "previous_assignee": "assignee",
        "new_assignee": "assignee",
    }.items():
        if options.get(key) and options[key] != "unassigned":
            resources.append({"field": field, "value": options[key]})
    for key in ("source_id", "target_id"):
        if key in options and not Issue.objects.filter(project=project, pk=options[key]).exists():
            raise ValidationError("The linked Work Item does not belong to this project.")
    for action in definition["actions"]:
        for key, field in {
            "type_id": "work_item_type",
            "state_id": "state",
            "label_id": "label",
            "member_id": "assignee",
        }.items():
            if key in action:
                resources.append({"field": field, "value": action[key]})
    for condition in resources:
        field, value = condition["field"], condition.get("value")
        if value is None or field in {"priority", "due_date"} or (field == "state" and value.startswith("group:")):
            continue
        if field == "work_item_type":
            valid = ProjectIssueType.objects.filter(
                project=project, issue_type_id=value, issue_type__is_active=True
            ).exists()
        elif field == "state":
            valid = State.objects.filter(project=project, pk=value).exists()
        elif field == "label":
            valid = Label.objects.filter(project=project, pk=value).exists()
        else:
            valid = ProjectMember.objects.filter(
                project=project, member_id=value, is_active=True, member__is_active=True
            ).exists()
        if not valid:
            raise ValidationError({"conditions": f"Invalid or inactive project resource for {field}."})
    for action in definition["actions"]:
        if "member_id" in action:
            if not ProjectMember.objects.filter(
                project=project, member_id=action["member_id"], is_active=True, member__is_active=True, role__gte=15
            ).exists():
                raise ValidationError({"actions": "Select an active project member with work item access."})
        if (
            action["type"] in {"change_state", "CHANGE_PARENT_STATE"}
            and not State.objects.filter(project=project, pk=action["state_id"]).exists()
        ):
            raise ValidationError({"actions": "The state does not belong to this project."})
        if (
            action["type"] == "manage_labels"
            and not Label.objects.filter(project=project, pk=action["label_id"]).exists()
        ):
            raise ValidationError({"actions": "The label does not belong to this project."})
    return definition


def rule_data(rule):
    return {
        **normalize_definition(rule.definition),
        "id": str(rule.id),
        "enabled": rule.enabled,
        "enabled_at": rule.enabled_at,
        "revision": rule.revision,
        "execution_actor_id": str(rule.execution_actor_id),
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
        "execution_count": getattr(rule, "execution_count", 0),
    }
