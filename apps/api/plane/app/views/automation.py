from copy import deepcopy

from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from plane.app.permissions import ProjectAdminPermission
from plane.app.views.workflow import WorkflowBaseAPIView
from plane.db.models import (
    Project,
    ProjectAutomationRule,
    ProjectAutomationExecution,
    ProjectAutomationEvent,
    ProjectIssueType,
    ProjectMember,
    State,
    Label,
    Issue,
)
from plane.services.automation_definition import TEMPLATES, TRIGGERS, ACTIONS, OPERATORS, RELATIONS, UPDATE_FIELDS
from plane.services.automation_config import MAX_ENABLED, MAX_ACTIONS, MAX_CONDITIONS
from plane.services.automation_rules import rule_data, validate_definition
from plane.services.workflow import get_workflow_start_state


class AutomationAPIView(WorkflowBaseAPIView):
    permission_classes = [ProjectAdminPermission]

    def project(self, slug, project_id):
        return get_object_or_404(Project, workspace__slug=slug, pk=project_id)


class AutomationRulesAPIView(AutomationAPIView):
    def get(self, request, slug, project_id):
        project = self.project(slug, project_id)
        rules = ProjectAutomationRule.objects.filter(project=project).annotate(
            execution_count=Count("projectautomationexecution")
        )
        return Response([rule_data(rule) for rule in rules])

    def post(self, request, slug, project_id):
        project = self.project(slug, project_id)
        definition = validate_definition(project, request.data)
        rule = ProjectAutomationRule.objects.create(
            project=project, definition=definition, execution_actor=request.user
        )
        return Response(rule_data(rule), status=201)


class AutomationRuleAPIView(AutomationAPIView):
    def get_rule(self, slug, project_id, rule_id, lock=False):
        query = ProjectAutomationRule.objects.select_related("project")
        if lock:
            query = query.select_for_update()
        return get_object_or_404(query, workspace__slug=slug, project_id=project_id, pk=rule_id)

    def get(self, request, slug, project_id, rule_id):
        return Response(rule_data(self.get_rule(slug, project_id, rule_id)))

    def put(self, request, slug, project_id, rule_id):
        with transaction.atomic():
            rule = self.get_rule(slug, project_id, rule_id, lock=True)
            data = dict(request.data)
            expected = data.pop("expected_revision", None)
            if expected != rule.revision:
                return Response({"detail": "Rule changed. Reload before saving."}, status=409)
            rule.definition = validate_definition(rule.project, data)
            rule.schedule_cursor = {}
            # Editing invalidates the previous approval; enabling is always explicit.
            rule.enabled, rule.enabled_at = False, None
            rule.execution_actor = request.user
            rule.revision += 1
            rule.save()
            return Response(rule_data(rule))

    def delete(self, request, slug, project_id, rule_id):
        with transaction.atomic():
            rule = self.get_rule(slug, project_id, rule_id, lock=True)
            rule.enabled, rule.enabled_at = False, None
            rule.save(update_fields=["enabled", "enabled_at", "updated_at"])
            # Queryset soft deletion avoids asynchronous cascades over future history.
            ProjectAutomationRule.objects.filter(pk=rule.pk).delete()
        return Response(status=204)


class AutomationRuleOperationAPIView(AutomationRuleAPIView):
    def post(self, request, slug, project_id, rule_id, operation):
        with transaction.atomic():
            rule = self.get_rule(slug, project_id, rule_id, lock=True)
            if operation == "duplicate":
                definition = deepcopy(rule.definition)
                definition["name"] = f"{definition['name'][:245]} (copy)"
                copy = ProjectAutomationRule.objects.create(
                    project=rule.project, definition=definition, execution_actor=request.user
                )
                return Response(rule_data(copy), status=201)
            if operation == "validate":
                validate_definition(rule.project, rule.definition)
                return Response({"valid": True})
            if operation == "test":
                from types import SimpleNamespace
                from plane.services.automation_definition import require_uuid
                from plane.services.automation_runtime import (
                    snapshot,
                    evaluate_rule,
                    evaluation_detail,
                    prepare_actions,
                )

                issue = get_object_or_404(Issue, pk=require_uuid(request.data.get("issue_id")), project=rule.project)
                validate_definition(rule.project, rule.definition)
                events = ProjectAutomationEvent.objects.filter(project=rule.project, issue=issue)
                event_id = request.data.get("event_id")
                if event_id:
                    event = get_object_or_404(events, pk=require_uuid(event_id))
                else:
                    event = events.order_by("-created_at", "-id").first()
                preview_mode = "recorded_event"
                if event is None:
                    current = snapshot(issue)
                    is_created = rule.definition["trigger"] == "created"
                    preview_mode = "simulated_created" if is_created else "current_snapshot"
                    event = SimpleNamespace(
                        snapshot=current,
                        before_snapshot=None if is_created else current,
                        triggers=["created"] if is_created else [],
                        context={},
                        created_at=timezone.now(),
                        issue_id=issue.id,
                    )
                evaluation = evaluate_rule(rule.definition, event, issue)
                from plane.services.automation_family import FamilySkipped
                from plane.services.workflow import WorkflowRuleError

                action_error = None
                try:
                    actions = prepare_actions(rule, issue, event) if evaluation["matched"] else []
                except (ValidationError, WorkflowRuleError, FamilySkipped) as error:
                    actions = []
                    action_error = str(error)
                reason = action_error or evaluation_detail(evaluation)
                if actions and all(kind == "skip" for kind, _ in actions):
                    reason = "; ".join(str(value) for _, value in actions)
                return Response(
                    {
                        "valid": action_error is None,
                        "conditions_match": all(c["matched"] for c in evaluation["conditions"]),
                        "trigger_match": evaluation["trigger"]["matched"],
                        "evaluation": evaluation,
                        "reason": reason,
                        "preview_mode": preview_mode,
                        "event_id": str(event.pk) if getattr(event, "pk", None) else None,
                        "action_count": sum(kind != "skip" for kind, _ in actions),
                        "writes": 0,
                    }
                )
            if operation == "status":
                if type(request.data.get("enabled")) is not bool:
                    raise ValidationError({"enabled": "Expected true or false."})
                enabled = request.data["enabled"]
                if enabled:
                    validate_definition(rule.project, rule.definition)
                    Project.objects.select_for_update().get(pk=rule.project_id)
                    if (
                        not rule.enabled
                        and ProjectAutomationRule.objects.filter(project=rule.project, enabled=True).count()
                        >= MAX_ENABLED
                    ):
                        raise ValidationError(f"A project may have at most {MAX_ENABLED} enabled rules.")
                if enabled != rule.enabled:
                    rule.enabled_at = timezone.now() if enabled else None
                    rule.schedule_cursor = {}
                rule.enabled = enabled
                rule.execution_actor = request.user
                rule.revision += 1
                rule.save()
                return Response(rule_data(rule))
            raise ValidationError("Unknown operation.")


class AutomationTemplatesAPIView(AutomationAPIView):
    def get(self, request, slug, project_id):
        self.project(slug, project_id)
        return Response(TEMPLATES)


class AutomationResourcesAPIView(AutomationAPIView):
    def get(self, request, slug, project_id):
        project = self.project(slug, project_id)
        members = ProjectMember.objects.filter(
            project=project, is_active=True, role__gte=15, member__is_active=True
        ).select_related("member")
        return Response(
            {
                "members": [
                    {"id": str(item.member_id), "name": item.member.display_name or item.member.email}
                    for item in members
                ],
                "types": [
                    {
                        "id": str(item.issue_type_id),
                        "name": item.issue_type.name,
                        "start_state_id": str(start.id)
                        if (start := get_workflow_start_state(project.id, item.issue_type_id))
                        else None,
                    }
                    for item in ProjectIssueType.objects.filter(
                        project=project, issue_type__is_active=True
                    ).select_related("issue_type")
                ],
                "states": list(State.objects.filter(project=project).values("id", "name", "group")),
                "timezone": project.timezone,
                "catalog": {
                    "triggers": TRIGGERS,
                    "actions": ACTIONS,
                    "operators": OPERATORS,
                    "relations": RELATIONS,
                    "update_fields": UPDATE_FIELDS,
                },
                "limits": {"enabled_rules": MAX_ENABLED, "conditions": MAX_CONDITIONS, "actions": MAX_ACTIONS},
                "labels": list(Label.objects.filter(project=project).values("id", "name")),
                "work_items": [
                    {"id": str(item.id), "name": f"{project.identifier}-{item.sequence_id} {item.name}"}
                    for item in Issue.objects.filter(project=project).order_by("-created_at")[:200]
                ],
            }
        )


class AutomationHistoryAPIView(AutomationAPIView):
    def get(self, request, slug, project_id):
        project = self.project(slug, project_id)
        try:
            page = max(0, int(request.query_params.get("page", "0")))
        except ValueError:
            raise ValidationError("Invalid history page.")
        query = ProjectAutomationExecution.objects.filter(project=project)
        status = request.query_params.get("status")
        if status:
            if status not in {"success", "failed", "skipped"}:
                raise ValidationError("Invalid history status.")
            query = query.filter(status=status)
        rows = list(query[page * 50 : page * 50 + 51])
        return Response(
            {
                "results": [
                    {
                        "id": str(row.id),
                        "rule_id": str(row.rule_key),
                        "status": row.status,
                        "detail": row.detail,
                        "snapshot": row.snapshot,
                        "created_at": row.created_at,
                    }
                    for row in rows[:50]
                ],
                "has_more": len(rows) > 50,
            }
        )
