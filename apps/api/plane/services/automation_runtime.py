"""Durable project automation events and transactionally idempotent executions."""

import os
import logging
from contextvars import ContextVar
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction, connection
from django.db import OperationalError
from django.db.models import F
from django.utils import timezone
from django.utils.html import escape
from rest_framework.exceptions import ValidationError

from plane.db.models import (
    Issue,
    IssueAssignee,
    IssueLabel,
    IssueComment,
    ProjectMember,
    ProjectAutomationRule,
    ProjectAutomationEvent,
    ProjectAutomationExecution,
)
from plane.services.automation_rules import validate_definition
from plane.services.automation_definition import normalize_definition, UPDATE_FIELDS
from plane.services.automation_config import RETRIES
from plane.services.workflow import WorkflowRuleError, get_available_transitions
from plane.services.automation_family import FamilySkipped, completed_parent, type_name, lock_family_write

automation_origin = ContextVar("project_automation_origin", default=False)
logger = logging.getLogger("plane.worker")


def module_enabled():
    return os.environ.get("PROJECT_AUTOMATIONS_ENABLED", "1") == "1"


def schedule_event_delivery(event):
    """Deliver request-created events in local eager mode where no Beat process exists."""

    if event is None or not getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        return event

    event_id = str(event.id)

    def deliver():
        from plane.bgtasks.project_automation_task import run_project_automation

        run_project_automation.delay(event_id)

    transaction.on_commit(deliver)
    return event


def snapshot(issue, fields=None):
    fields = set(fields or UPDATE_FIELDS) | {"id", "name", "sequence_id", "parent_id", "work_item_type", "state_group"}
    result = {
        "id": str(issue.id),
        "name": issue.name,
        "sequence_id": issue.sequence_id,
        "parent_id": str(issue.parent_id) if issue.parent_id else None,
        "work_item_type": str(issue.type_id) if issue.type_id else None,
        "state": str(issue.state_id) if issue.state_id else None,
        "state_group": issue.state.group if issue.state_id else None,
        "priority": issue.priority,
        "description_html": issue.description_html if "description_html" in fields else None,
        "start_date": issue.start_date.isoformat() if "start_date" in fields and issue.start_date else None,
        "target_date": issue.target_date.isoformat() if "target_date" in fields and issue.target_date else None,
        "estimate_point": str(issue.estimate_point_id)
        if "estimate_point" in fields and issue.estimate_point_id
        else None,
    }
    if "assignee" in fields:
        result["assignee"] = sorted(
            str(v) for v in IssueAssignee.objects.filter(issue=issue).values_list("assignee_id", flat=True)
        )
    if "label" in fields:
        result["label"] = sorted(
            str(v) for v in IssueLabel.objects.filter(issue=issue).values_list("label_id", flat=True)
        )
    return result


def capture_context(project_id, issue=None, changed_fields=None):
    if not module_enabled() or automation_origin.get():
        return None
    candidates = list(
        ProjectAutomationRule.objects.filter(project_id=project_id, enabled=True).values("id", "revision", "definition")
    )
    if not candidates:
        return None
    # Conditions inspect the current snapshot even when their field was not changed.
    # Include every candidate's required fields alongside the edited fields.
    requested = set(changed_fields or ()) | snapshot_fields(candidates)
    requested = {
        "assignee" if field in {"assignee_ids", "assignees"} else "label" if field in {"label_ids", "labels"} else field
        for field in requested
    }
    return {
        "candidates": [{"id": str(v["id"]), "revision": v["revision"]} for v in candidates],
        "before": snapshot(issue, requested) if issue else None,
        "snapshot_fields": sorted(requested),
    }


def emit_event(issue, context):
    if context is None or automation_origin.get():
        return None
    after = snapshot(issue, context.get("snapshot_fields"))
    before = context["before"]
    triggers = ["created"] if before is None else []
    if before is not None:
        if any(before.get(field) != after.get(field) for field in UPDATE_FIELDS):
            triggers.append("updated")
        for field in ("state", "priority", "assignee"):
            if before.get(field) != after.get(field):
                triggers.append(f"{field}_changed")
        if "state_changed" in triggers and after["state_group"] == "completed" and before["state_group"] != "completed":
            triggers.append("completed")
            if issue.parent_id and type_name(issue) == "subtask":
                triggers.append("SUBTASK_COMPLETED")
    if not triggers:
        return None
    return schedule_event_delivery(
        ProjectAutomationEvent.objects.create(
            project=issue.project,
            issue=issue,
            snapshot=after,
            before_snapshot=before,
            context={
                "actor_id": str(issue.updated_by_id or issue.created_by_id)
                if (issue.updated_by_id or issue.created_by_id)
                else None
            },
            candidates=context["candidates"],
            triggers=triggers,
        )
    )


def snapshot_fields(candidates):
    fields = set()
    for candidate in candidates:
        definition = normalize_definition(candidate.get("definition", {}))
        trigger = definition.get("trigger")
        options = definition.get("trigger_options", {})
        if trigger == "updated":
            fields.update(UPDATE_FIELDS if not options.get("field") else {options["field"]})
        elif trigger == "state_changed":
            fields.update({"state"})
        elif trigger == "priority_changed":
            fields.update({"priority"})
        elif trigger == "assignee_changed":
            fields.update({"assignee"})
        for condition in definition.get("conditions", []):
            fields.add(condition.get("field"))
        for action in definition.get("actions", []):
            if action.get("type") == "manage_labels":
                fields.add("label")
    return {field for field in fields if field in UPDATE_FIELDS}


def matches_trigger(definition, event, issue):
    return evaluate_trigger(definition, event, issue)["matched"]


def evaluate_trigger(definition, event, issue):
    """Use the same checks for execution and read-only previews."""
    definition = normalize_definition(definition)
    trigger, options = definition["trigger"], definition.get("trigger_options", {})
    checks = []

    def check(field, expected, actual, operator="equals"):
        matched = (
            expected in actual
            if operator == "contains"
            else actual != expected
            if operator == "not_equals"
            else actual == expected
        )
        checks.append(
            {"field": field, "operator": operator, "expected": expected, "actual": actual, "matched": matched}
        )

    check("trigger", trigger, event.triggers, "contains")
    old, new = getattr(event, "before_snapshot", None) or {}, event.snapshot
    context = getattr(event, "context", {})
    if trigger == "created":
        if options.get("type_id"):
            check("work_item_type", options["type_id"], new.get("work_item_type"))
    elif trigger == "updated":
        field = options.get("field")
        if field:
            check(field, old.get(field), new.get(field), "not_equals")
        else:
            check("changed_fields", True, any(old.get(k) != new.get(k) for k in UPDATE_FIELDS))
    elif trigger == "state_changed":
        for key, actual in (
            ("from_state", old.get("state")),
            ("to_state", new.get("state")),
            ("from_group", old.get("state_group")),
            ("to_group", new.get("state_group")),
        ):
            if key in options:
                check(key, options[key], actual)
        if options.get("enter_group_only"):
            check("state_group", old.get("state_group"), new.get("state_group"), "not_equals")
        if options.get("subtask_only"):
            check("subtask_only", True, bool(issue.parent_id and type_name(issue) == "subtask"))
    elif trigger == "priority_changed":
        for key, actual in (("from_priority", old.get("priority")), ("to_priority", new.get("priority"))):
            if key in options:
                check(key, options[key], actual)
    elif trigger == "assignee_changed":
        for key, actual in (
            ("previous_assignee", old.get("assignee", [])),
            ("new_assignee", new.get("assignee", [])),
        ):
            if key in options:
                check(
                    key,
                    [] if options[key] == "unassigned" else options[key],
                    actual,
                    "equals" if options[key] == "unassigned" else "contains",
                )
    elif trigger == "comment_added":
        if options.get("author_id"):
            check("author_id", options["author_id"], context.get("author_id"))
    elif trigger == "work_item_linked":
        if options.get("relation_type"):
            check("relation_type", options["relation_type"], context.get("relation_types", []), "contains")
        for key in ("source_id", "target_id"):
            if key in options:
                check(key, options[key], context.get(key))
    return {
        "matched": all(c["matched"] for c in checks),
        "expected": trigger,
        "actual": event.triggers,
        "checks": checks,
    }


def matches_conditions(definition, event, project):
    return all(check["matched"] for check in condition_checks(definition, event, project))


def condition_checks(definition, event, project):
    for condition in definition["conditions"]:
        field, operator = condition["field"], condition["operator"]
        expected = condition.get("value")
        actual = None
        if field == "ALL_SUBTASKS_COMPLETED":
            source = Issue.objects.select_related("type").filter(pk=event.issue_id, project=project).first()
            if source is None:
                raise FamilySkipped("Source Subtask no longer exists.")
            completed_parent(source, event)
            matched = True
            actual = True
        elif field == "project_member":
            matched = ProjectMember.objects.filter(
                project=project, member_id=expected, is_active=True, member__is_active=True
            ).exists()
            actual = matched
        else:
            actual = event.snapshot.get("target_date" if field == "due_date" else field)
            if field == "state" and expected and expected.startswith("group:"):
                actual, expected = event.snapshot.get("state_group"), expected[6:]
            if operator in ("is_empty", "is_not_empty"):
                matched = not actual
                if operator == "is_not_empty":
                    matched = not matched
            elif field == "due_date" and operator in ("overdue", "within_next_days"):
                from datetime import datetime

                context = getattr(event, "context", {})
                instant = (
                    datetime.fromisoformat(context["scheduled_for"])
                    if context.get("scheduled_for")
                    else event.created_at
                )
                today = instant.astimezone(ZoneInfo(context.get("timezone", project.timezone))).date()
                due = date.fromisoformat(actual) if actual else None
                matched = bool(
                    due
                    and (
                        due < today if operator == "overdue" else today <= due <= today + timedelta(days=int(expected))
                    )
                )
            else:
                matched = expected in actual if isinstance(actual, list) else actual == expected
        if operator in ("not_equals", "does_not_contain"):
            matched = not matched
        yield {"field": field, "operator": operator, "expected": expected, "actual": actual, "matched": matched}


def evaluate_rule(definition, event, issue):
    definition = normalize_definition(definition)
    trigger = evaluate_trigger(definition, event, issue)
    checks = []
    # Family checks acquire locks and can fail closed. Evaluate only after a matching trigger.
    if trigger["matched"]:
        try:
            for check in condition_checks(definition, event, issue.project):
                checks.append(check)
        except FamilySkipped as error:
            checks.append(
                {
                    "field": "ALL_SUBTASKS_COMPLETED",
                    "operator": "is_true",
                    "expected": True,
                    "actual": False,
                    "matched": False,
                    "reason": str(error),
                }
            )
    return {
        "matched": trigger["matched"] and all(c["matched"] for c in checks),
        "trigger": trigger,
        "conditions": checks,
    }


def evaluation_detail(evaluation):
    if not evaluation["trigger"]["matched"]:
        trigger = evaluation["trigger"]
        if trigger["expected"] not in trigger["actual"]:
            return (
                f"Trigger mismatch: rule expects '{trigger['expected']}', "
                f"but this event is {', '.join(trigger['actual']) or 'no recorded change'}."
            )
        failed = next(c for c in trigger["checks"] if not c["matched"])
        return (
            f"Trigger filter '{failed['field']}' did not match: "
            f"expected {failed['expected']}, actual {failed['actual']}."
        )
    failed = next((c for c in evaluation["conditions"] if not c["matched"]), None)
    if failed:
        return failed.get("reason") or (
            f"Condition '{failed['field']}' ({failed['operator']}) did not match: "
            f"expected {failed['expected']}, actual {failed['actual']}."
        )
    return "Trigger and conditions match."


def prepare_actions(rule, issue, event, action_index=None):
    from plane.app.serializers.issue import IssueCreateSerializer

    definition = validate_definition(issue.project, rule.definition)
    actor = rule.execution_actor
    if (
        not actor.is_active
        or not ProjectMember.objects.filter(project=issue.project, member=actor, is_active=True, role__gte=15).exists()
    ):
        raise ValidationError("The execution actor no longer has project work item access.")
    prepared = []
    for index, action in enumerate(definition["actions"]):
        if action_index is not None and index != action_index:
            continue
        kind, data = action["type"], None
        target_issue = issue
        if kind == "change_state" and action.get("target") == "parent":
            target_issue = completed_parent(issue, event)
            if str(target_issue.state_id) == action["state_id"]:
                prepared.append(("skip", f"Parent {target_issue.id} is already in the target state."))
                continue
        if kind == "assign_user":
            if action.get("only_if_unassigned", True) and IssueAssignee.objects.filter(issue=issue).exists():
                prepared.append(("skip", "Already assigned"))
                continue
            member_id = (
                action.get("member_id")
                if action["mode"] == "specific_member"
                else issue.project.project_lead_id
                if action["mode"] == "project_lead"
                else issue.created_by_id
            )
            if (
                not member_id
                or not ProjectMember.objects.filter(
                    project=issue.project, member_id=member_id, member__is_active=True, is_active=True, role__gte=15
                ).exists()
            ):
                raise ValidationError("The assignment target is not an active project member.")
            current = set(
                str(v) for v in IssueAssignee.objects.filter(issue=issue).values_list("assignee_id", flat=True)
            )
            # Existing multi-assignees are preserved unless replacement is explicit.
            data = {
                "assignee_ids": [str(member_id)]
                if action.get("replace_assignees")
                else sorted(current | {str(member_id)})
            }
        elif kind in {"change_state", "CHANGE_PARENT_STATE"}:
            data = {"state_id": action["state_id"]}
            available = get_available_transitions(target_issue, actor)
            if (
                str(target_issue.state_id) != action["state_id"]
                and available is not None
                and not any(str(edge.target.state_id) == action["state_id"] for edge in available)
            ):
                raise ValidationError("This transition is not allowed by the current workflow.")
            if str(target_issue.state_id) == action["state_id"]:
                prepared.append(("skip", "The Work Item is already in the destination state."))
                continue
        elif kind == "change_priority":
            data = {"priority": action["priority"]}
        elif kind == "manage_labels":
            labels = [str(v) for v in IssueLabel.objects.filter(issue=issue).values_list("label_id", flat=True)]
            data = {
                "label_ids": sorted(set(labels) | {action["label_id"]})
                if action["operation"] == "add"
                else sorted(set(labels) - {action["label_id"]})
            }
        elif kind == "set_due_date":
            due = (
                date.fromisoformat(action["date"])
                if action.get("mode") == "fixed"
                else event.created_at.astimezone(ZoneInfo(action.get("timezone", issue.project.timezone))).date()
                + timedelta(days=action["days"])
            )
            if issue.start_date and due < issue.start_date:
                raise ValidationError("The due date would precede the work item's start date.")
            data = {"target_date": due.isoformat()}
        elif kind == "add_comment":
            prepared.append(("comment", render_text(action["text"], issue, event)))
            continue
        elif kind == "create_work_item":
            from plane.services.workflow import get_workflow_start_state

            start = get_workflow_start_state(issue.project_id, action["type_id"])
            initial_state_id = str(start.id) if start else action.get("state_id")
            serializer = IssueCreateSerializer(
                data={
                    "type": action["type_id"],
                    "name": render_text(action["title"], issue, event)[:255],
                    "description_html": f"<p>{escape(render_text(action.get('description', ''), issue, event))}</p>",
                    "priority": action["priority"],
                    **({"parent_id": str(issue.id)} if action.get("parent_mode") == "source" else {}),
                    # Legacy rules may carry a state; active type workflows always win.
                    **({"state_id": initial_state_id} if initial_state_id else {}),
                    "assignee_ids": [action["member_id"]] if action.get("member_id") else [],
                },
                context={
                    "project_id": str(issue.project_id),
                    "workspace_id": str(issue.workspace_id),
                    "default_assignee_id": None,
                    "actor": actor,
                },
            )
            serializer.is_valid(raise_exception=True)
            prepared.append(("create", (serializer, action)))
            continue
        elif kind in {"add_dependency", "remove_dependency"}:
            if "parent" in (action["source_mode"], action["target_mode"]) and not issue.parent_id:
                prepared.append(("skip", "The triggering Work Item has no parent for this dependency action."))
                continue
            prepared.append(("dependency", action))
            continue
        serializer = IssueCreateSerializer(
            target_issue,
            data=data,
            partial=True,
            context={
                "project_id": str(issue.project_id),
                "workspace_id": str(issue.workspace_id),
                "actor": actor,
                "transition_source": "project_automation",
            },
        )
        serializer.is_valid(raise_exception=True)
        prepared.append(("update", serializer))
    return prepared


def render_text(text, issue, event):
    """Literal replacement only: no format expressions, evaluation, or attribute access."""
    from plane.db.models import State, User

    old = getattr(event, "before_snapshot", None) or {}
    states = {
        str(pk): name
        for pk, name in State.objects.filter(
            project=issue.project, pk__in=[v for v in (old.get("state"), event.snapshot.get("state")) if v]
        ).values_list("id", "name")
    }
    actor_id = getattr(event, "context", {}).get("actor_id")
    actor = User.objects.filter(pk=actor_id).first() if actor_id else None
    values = {
        "work_item_identifier": f"{issue.project.identifier}-{issue.sequence_id}",
        "work_item_title": event.snapshot.get("name", issue.name),
        "previous_state": states.get(old.get("state"), ""),
        "new_state": states.get(event.snapshot.get("state"), ""),
        "actor_name": actor.display_name or actor.email if actor else "",
    }
    import re

    return re.sub(
        r"\{(work_item_identifier|work_item_title|previous_state|new_state|actor_name)\}",
        lambda match: values[match.group(1)],
        text,
    )


def execute_candidate(event, candidate):
    # The rule lock serializes duplicate deliveries; completion and effects commit together.
    with transaction.atomic():
        rule = (
            ProjectAutomationRule.objects.select_for_update()
            .select_related("execution_actor")
            .filter(pk=candidate["id"], project=event.project)
            .first()
        )
        if ProjectAutomationExecution.objects.filter(event=event, rule_key=candidate["id"]).exists():
            return
        if event.context.get("skip_reason"):
            raise FamilySkipped(event.context["skip_reason"])
        status, detail = "skipped", "Rule was deleted, disabled or edited after this event."
        frozen = dict(rule.definition) if rule else {"name": "Deleted rule"}
        evaluation = None
        if (
            rule
            and rule.enabled
            and rule.revision == candidate["revision"]
            and rule.enabled_at
            and rule.enabled_at <= event.created_at
        ):
            family_rule = any(c["field"] == "ALL_SUBTASKS_COMPLETED" for c in rule.definition["conditions"])
            source = Issue.objects.filter(pk=event.issue_id, project=event.project).first()
            if source:
                lock_family_write(source)
            query = Issue.objects.all() if family_rule else Issue.objects.select_for_update(of=("self",))
            issue = query.select_related("project", "state").filter(pk=event.issue_id, project=event.project).first()
            if issue:
                evaluation = evaluate_rule(rule.definition, event, issue)
            if issue and evaluation["matched"]:
                prepared = prepare_actions(rule, issue, event)
                token = automation_origin.set(True)
                try:
                    progress = event.progress.setdefault(candidate["id"], {})
                    changed = any(step.get("changed") for step in progress.values())
                    for index, (kind, value) in enumerate(prepared):
                        step = progress.setdefault(str(index), {})
                        if step.get("done"):
                            continue
                        if index:
                            issue.refresh_from_db()
                            kind, value = prepare_actions(rule, issue, event, action_index=index)[0]
                        if kind == "comment":
                            IssueComment.objects.create(
                                project=issue.project,
                                issue=issue,
                                actor=rule.execution_actor,
                                comment_html=f"<p>{escape(value).replace(chr(10), '<br>')}</p>",
                            )
                            changed = True
                        elif kind == "update":
                            value.save()
                            changed = True
                        elif kind == "create":
                            serializer, action = value
                            if not step.get("created_issue_id"):
                                created = serializer.save()
                                Issue.objects.filter(pk=created.pk).update(
                                    created_by=rule.execution_actor, updated_by=rule.execution_actor
                                )
                                step["created_issue_id"] = str(created.id)
                                step["changed"] = True
                                ProjectAutomationEvent.objects.filter(pk=event.pk).update(progress=event.progress)
                                # Commit the creation checkpoint before attempting the relation.
                                return False
                            created = Issue.objects.filter(pk=step["created_issue_id"], project=issue.project).first()
                            if not created:
                                raise ValidationError("The created Work Item was removed; it will not be recreated.")
                            if action.get("relation"):
                                create_relation(created, issue, action["relation"], rule.execution_actor)
                            changed = True
                        elif kind == "dependency":
                            action = value
                            source = resolve_dependency_issue(action, "source", issue, progress, index)
                            target = resolve_dependency_issue(action, "target", issue, progress, index)
                            dependency_changed = mutate_dependency(
                                source,
                                target,
                                action["relation_type"],
                                add=action["type"] == "add_dependency",
                                actor=rule.execution_actor,
                            )
                            step.update(
                                source_issue_id=str(source.id),
                                target_issue_id=str(target.id),
                                relation_type=action["relation_type"],
                                changed=dependency_changed,
                            )
                            changed = changed or dependency_changed
                        step.update(done=True, changed=step.get("changed", kind != "skip"))
                    ProjectAutomationEvent.objects.filter(pk=event.pk).update(progress=event.progress)
                    status, detail = (
                        ("success", "Actions completed")
                        if changed
                        else (
                            "skipped",
                            "; ".join(str(v) for k, v in prepared if k == "skip") or "Actions made no changes.",
                        )
                    )
                finally:
                    automation_origin.reset(token)
            else:
                detail = evaluation_detail(evaluation) if evaluation else "The source Work Item no longer exists."
        ProjectAutomationExecution.objects.create(
            project=event.project,
            event=event,
            rule=rule,
            rule_key=candidate["id"],
            snapshot={**execution_snapshot(event, frozen), **({"evaluation": evaluation} if evaluation else {})},
            status=status,
            detail=detail,
        )
    return True


def execution_snapshot(event, definition):
    return {
        "definition": definition,
        "work_item": event.snapshot,
        "parent_id": event.snapshot.get("parent_id"),
        "before": event.before_snapshot,
        "trigger_details": event.context,
        "triggers": event.triggers,
        "steps": event.progress,
    }


def create_relation(created, source, relation, actor):
    mutate_dependency(created, source, relation, add=True, actor=actor)


def resolve_dependency_issue(action, side, triggering, progress, action_index):
    mode = action[f"{side}_mode"]
    if mode == "triggering":
        return triggering
    if mode == "parent":
        parent = Issue.issue_objects.filter(
            pk=triggering.parent_id,
            project=triggering.project,
            workspace=triggering.workspace,
        ).first()
        if parent is None:
            raise ValidationError(f"The triggering Work Item parent required by the {side} is no longer available.")
        return parent
    if mode == "specific":
        target = Issue.issue_objects.filter(
            pk=action[f"{side}_id"], project=triggering.project, workspace=triggering.workspace
        ).first()
        if target is None:
            raise ValidationError(f"The selected {side} Work Item is no longer available in this project.")
        return target
    for previous_index in range(action_index - 1, -1, -1):
        created_id = progress.get(str(previous_index), {}).get("created_issue_id")
        if created_id:
            target = Issue.issue_objects.filter(pk=created_id, project=triggering.project).first()
            if target:
                return target
    raise ValidationError(f"The {side} requires a Create Work Item action earlier in this rule.")


def canonical_dependency(source, target, relation_type, actor):
    from plane.db.models import IssueRelation
    from plane.db.models.issue import IssueRelationChoices

    pairs = dict(IssueRelationChoices._RELATION_PAIRS)
    reverse = {value: key for key, value in pairs.items() if value != key}
    left, right, stored = (
        (target, source, reverse[relation_type]) if relation_type in reverse else (source, target, relation_type)
    )
    return IssueRelation(
        issue=left,
        related_issue=right,
        project=left.project,
        workspace=left.workspace,
        relation_type=stored,
        created_by=actor,
        updated_by=actor,
    )


def mutate_dependency(source, target, relation_type, *, add, actor):
    from plane.db.models import IssueRelation
    from plane.services.automation_events import bulk_create_relations
    from plane.services.issue_relations import validate_relation_candidates

    if source.id == target.id:
        raise ValidationError("A Work Item cannot have a dependency with itself.")
    if source.workspace_id != target.workspace_id:
        raise ValidationError("Dependency Work Items must belong to the same workspace.")
    candidate = canonical_dependency(source, target, relation_type, actor)
    existing = IssueRelation.objects.filter(
        issue_id=candidate.issue_id,
        related_issue_id=candidate.related_issue_id,
        relation_type=candidate.relation_type,
    ).first()
    if not add:
        if existing is None:
            return False
        existing.delete()
        return True
    pending = validate_relation_candidates([candidate], allow_existing=True)
    if not pending:
        return False
    bulk_create_relations(pending, ignore_conflicts=True)
    return True


def process_event(event_id):
    # Session advisory locks are released on worker connection loss; duplicate jobs
    # never consume retry attempts or race the first delivery's history record.
    if not module_enabled():
        return
    key = f"project-automation:{event_id}"
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 0))", [key])
        acquired = cursor.fetchone()[0]
    if not acquired:
        return
    try:
        _process_event(event_id)
    finally:
        if connection.is_usable():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", [key])


def _process_event(event_id):
    if not module_enabled():
        return
    event = ProjectAutomationEvent.objects.select_related("project").get(pk=event_id)
    if event.processed_at:
        return
    ProjectAutomationEvent.objects.filter(pk=event.pk, processed_at__isnull=True).update(
        delivery_attempts=F("delivery_attempts") + 1
    )
    event.refresh_from_db()
    for candidate in event.candidates:
        try:
            if event.delivery_attempts > RETRIES + 1:
                raise ValidationError("Temporary delivery failures exhausted the retry limit.")
            for _ in range(5):
                if execute_candidate(event, candidate) is not False:
                    break
        except OperationalError as error:
            event.refresh_from_db(fields=["progress"])
            ProjectAutomationEvent.objects.filter(pk=event.pk).update(last_error=str(error)[:10000])
            raise
        except Exception as error:
            event.refresh_from_db(fields=["progress"])
            if not isinstance(error, (ValidationError, WorkflowRuleError, FamilySkipped)):
                logger.exception("Project automation failed for event %s rule %s", event.id, candidate["id"])
            rule = ProjectAutomationRule.objects.filter(pk=candidate["id"], project=event.project).first()
            ProjectAutomationExecution.objects.get_or_create(
                event=event,
                rule_key=candidate["id"],
                defaults={
                    "project": event.project,
                    "rule": rule,
                    "status": "skipped" if isinstance(error, FamilySkipped) else "failed",
                    "detail": str(error)[:10000],
                    "snapshot": execution_snapshot(event, rule.definition if rule else {}),
                },
            )
    ProjectAutomationEvent.objects.filter(pk=event.pk).update(processed_at=timezone.now())
