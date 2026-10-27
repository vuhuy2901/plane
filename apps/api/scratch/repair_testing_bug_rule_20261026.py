"""Preview/apply the user's exact Task testing-rejected rule, without replaying events."""

import json
import os
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from plane.db.models import Issue, ProjectAutomationEvent, ProjectAutomationRule
from plane.services.automation_rules import validate_definition
from plane.services.automation_runtime import evaluate_rule, evaluation_detail, prepare_actions


with transaction.atomic():
    rule = ProjectAutomationRule.objects.select_for_update().select_related("project", "execution_actor").get(
        pk=UUID("4c8a5ab8-74d8-4b3c-8483-abe6681244d5"),
        project_id=UUID("46fdbf9a-9260-4a15-a64a-a2cefe169142"),
    )
    original = {"definition": rule.definition, "enabled": rule.enabled, "revision": rule.revision}
    definition = validate_definition(rule.project, {
        "name": rule.definition["name"],
        "trigger": "state_changed",
        "trigger_options": {
            "from_state": "36183b96-9867-4faa-9417-9137d12466f0",
            "to_state": "c6bfe1d2-8684-4200-9594-62dea2824ce6",
        },
        "conditions": [{
            "field": "work_item_type", "operator": "equals", "value": "5a0b5aea-8332-4236-875e-c0cbc71f4fbc",
        }],
        "actions": [{
            "type": "create_work_item",
            "type_id": "a6a3e934-04d6-4b10-aa61-6dd89d049a5f",
            "title": "Bug: {work_item_title}",
            "description": "Testing rejected for {work_item_identifier}: {previous_state} -> {new_state}.",
            "priority": "medium",
            "relation": "relates_to",
        }],
    })
    issue = Issue.objects.select_related("project", "type", "state").get(
        pk=UUID("f006acaf-4b3f-4b6a-ac6a-b4f70d519694"), project=rule.project,
    )
    # Use the actual recorded testing -> progress event. Preview only; do not replay it.
    event = ProjectAutomationEvent.objects.filter(
        issue=issue,
        project=rule.project,
        before_snapshot__state=definition["trigger_options"]["from_state"],
        snapshot__state=definition["trigger_options"]["to_state"],
    ).order_by("-created_at").first()
    if event is None:
        raise RuntimeError("No recorded IN TESTING -> InProgress event exists to verify this repair.")
    rule.definition = definition
    evaluation = evaluate_rule(definition, event, issue)
    if not evaluation["matched"]:
        raise RuntimeError(evaluation_detail(evaluation))
    actions = prepare_actions(rule, issue, event)
    if len(actions) != 1 or actions[0][0] != "create":
        raise RuntimeError("The repaired rule must prepare exactly one Bug creation.")
    apply = os.environ.get("APPLY_TESTING_BUG_REPAIR") == "1"
    if apply and original["definition"] != definition:
        if original["revision"] != 3:
            raise RuntimeError("Rule was edited since diagnosis; inspect the new revision first.")
        rule.revision += 1
        rule.enabled = True
        rule.enabled_at = timezone.now()
        rule.schedule_cursor = {}
        rule.save(update_fields=["definition", "revision", "enabled", "enabled_at", "schedule_cursor", "updated_at"])
    print(json.dumps({
        "applied": apply,
        "rule_id": str(rule.id),
        "original": original,
        "definition": definition,
        "evaluation": evaluation,
        "preview_event_id": str(event.id),
        "action_count": len(actions),
        "created_bugs": 0,
        "enabled": rule.enabled,
        "revision": rule.revision,
    }, ensure_ascii=False, default=str))
