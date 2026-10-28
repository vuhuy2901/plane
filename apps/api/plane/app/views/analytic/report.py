# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

from datetime import date, timedelta
from uuid import UUID

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.db.models import (
    Cycle,
    CycleIssue,
    Issue,
    IssueActivity,
    IssueAssignee,
    IssueType,
    Module,
    ModuleIssue,
    Project,
    ProjectAutomationExecution,
    ProjectAutomationRule,
    ProjectMember,
    State,
)
from plane.utils.date_utils import get_analytics_filters


REPORT_MAX_DAYS = 366
OPEN_STATE_GROUPS = ("backlog", "unstarted", "started")
NON_OVERDUE_STATE_GROUPS = ("completed", "cancelled")


def _parse_uuid_list(request, key):
    raw_value = request.GET.get(key)
    if not raw_value:
        return None
    values = [value.strip() for value in raw_value.split(",") if value.strip()]
    if not values or len(values) > 100:
        raise ValueError(key)
    return [str(UUID(value)) for value in values]


def _parse_date_range(request, analytics_date_range):
    raw_start = request.GET.get("date_from")
    raw_end = request.GET.get("date_to")
    if bool(raw_start) != bool(raw_end):
        raise ValueError("date_from and date_to must be provided together")

    if raw_start and raw_end:
        start = date.fromisoformat(raw_start)
        end = date.fromisoformat(raw_end)
    elif analytics_date_range:
        start = analytics_date_range["current"]["gte"].date()
        end = analytics_date_range["current"]["lte"].date()
    else:
        end = timezone.localdate()
        start = end - timedelta(days=29)

    if start > end:
        raise ValueError("date_from must not be after date_to")
    if (end - start).days >= REPORT_MAX_DAYS:
        raise ValueError(f"Date range cannot exceed {REPORT_MAX_DAYS} days")
    return start, end


class WorkspaceReportEndpoint(BaseAPIView):
    """Permission-scoped analytics used by the workspace reporting tabs."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug):
        try:
            project_ids = _parse_uuid_list(request, "project_ids")
            type_ids = _parse_uuid_list(request, "type_ids")
            state_ids = _parse_uuid_list(request, "state_ids")
            assignee_ids = _parse_uuid_list(request, "assignee_ids")
            cycle_ids = _parse_uuid_list(request, "cycle_ids")
            module_ids = _parse_uuid_list(request, "module_ids")
            bug_type_ids = _parse_uuid_list(request, "bug_type_ids")
        except (ValueError, AttributeError):
            return Response(
                {"message": "One or more identifier filters are invalid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        date_filter = request.GET.get("date_filter")
        if date_filter and date_filter not in {
            "yesterday",
            "last_7_days",
            "last_30_days",
            "last_3_months",
        }:
            return Response({"message": "Invalid date_filter"}, status=status.HTTP_400_BAD_REQUEST)

        count_mode = request.GET.get("count_mode", "all")
        if count_mode not in {"all", "top_level"}:
            return Response({"message": "Invalid count_mode"}, status=status.HTTP_400_BAD_REQUEST)

        filters = get_analytics_filters(
            slug=slug,
            user=request.user,
            type="analytics",
            date_filter=date_filter,
            project_ids=project_ids,
        )
        try:
            range_start, range_end = _parse_date_range(request, filters["analytics_date_range"])
        except (TypeError, ValueError):
            return Response({"message": "Invalid date range"}, status=status.HTTP_400_BAD_REQUEST)

        projects = Project.objects.filter(**filters["project_filters"]).distinct()
        issues = Issue.issue_objects.filter(**filters["base_filters"])
        if type_ids:
            issues = issues.filter(type_id__in=type_ids)
        if state_ids:
            issues = issues.filter(state_id__in=state_ids)
        if assignee_ids:
            issues = issues.filter(
                issue_assignee__assignee_id__in=assignee_ids,
                issue_assignee__deleted_at__isnull=True,
            )
        if cycle_ids:
            issues = issues.filter(
                issue_cycle__cycle_id__in=cycle_ids,
                issue_cycle__deleted_at__isnull=True,
            )
        if module_ids:
            issues = issues.filter(
                issue_module__module_id__in=module_ids,
                issue_module__deleted_at__isnull=True,
            )

        priorities = [value.strip() for value in request.GET.get("priorities", "").split(",") if value.strip()]
        valid_priorities = {choice[0] for choice in Issue.PRIORITY_CHOICES}
        if priorities and (len(priorities) > len(valid_priorities) or not set(priorities).issubset(valid_priorities)):
            return Response({"message": "Invalid priorities"}, status=status.HTTP_400_BAD_REQUEST)
        if priorities:
            issues = issues.filter(priority__in=priorities)
        if count_mode == "top_level":
            issues = issues.filter(parent__isnull=True)

        # Date filters scope KPI populations by creation date. Event charts use
        # the same population so cards and charts keep one filter meaning.
        issues = (
            issues.filter(
                created_at__date__gte=range_start,
                created_at__date__lte=range_end,
            )
            .order_by()
            .distinct()
        )
        issue_ids = issues.values("id")
        accessible_project_ids = projects.values("id")
        reference_date = min(range_end, timezone.localdate())

        if bug_type_ids is None:
            bug_type_ids = list(
                IssueType.objects.filter(
                    workspace__slug=slug,
                    name__iexact="bug",
                    is_active=True,
                ).values_list("id", flat=True)
            )
        bug_issues = issues.filter(type_id__in=bug_type_ids)
        overdue_filter = Q(target_date__lt=reference_date) & ~Q(state__group__in=NON_OVERDUE_STATE_GROUPS)

        totals = issues.aggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(state__group="completed")),
            cancelled=Count("id", filter=Q(state__group="cancelled")),
            in_progress=Count("id", filter=Q(state__group="started")),
            unstarted=Count("id", filter=Q(state__group__in=("backlog", "unstarted"))),
            overdue=Count("id", filter=overdue_filter),
            subtasks=Count("id", filter=Q(parent__isnull=False)),
        )
        actionable_total = max(totals["total"] - totals["cancelled"], 0)
        totals["completion_rate"] = round((totals["completed"] / actionable_total) * 100, 2) if actionable_total else 0
        totals["completion_denominator"] = actionable_total

        average_duration = issues.filter(completed_at__isnull=False).aggregate(
            value=Avg(
                ExpressionWrapper(
                    F("completed_at") - F("created_at"),
                    output_field=DurationField(),
                )
            )
        )["value"]
        totals["average_completion_seconds"] = round(average_duration.total_seconds()) if average_duration else None

        bug_totals = bug_issues.aggregate(
            total=Count("id"),
            open=Count("id", filter=Q(state__group__in=OPEN_STATE_GROUPS)),
            completed=Count("id", filter=Q(state__group="completed")),
            overdue=Count("id", filter=overdue_filter),
        )
        totals.update(
            total_bugs=bug_totals["total"],
            open_bugs=bug_totals["open"],
            completed_bugs=bug_totals["completed"],
        )

        active_members = (
            ProjectMember.objects.filter(
                project_id__in=accessible_project_ids,
                is_active=True,
                deleted_at__isnull=True,
            )
            .values("member_id")
            .distinct()
            .count()
        )
        now = timezone.now()
        active_cycles = Cycle.objects.filter(
            project_id__in=accessible_project_ids,
            deleted_at__isnull=True,
            archived_at__isnull=True,
            start_date__lte=now,
            end_date__gte=now,
        ).count()
        totals.update(active_members=active_members, active_cycles=active_cycles)

        states = list(
            issues.values("state_id", "state__name", "state__project__name", "state__group", "state__color")
            .annotate(count=Count("id"))
            .order_by("state__group", "state__name")
        )
        priority_distribution = list(issues.values("priority").annotate(count=Count("id")).order_by("priority"))
        type_distribution = list(
            issues.values("type_id", "type__name", "type__color").annotate(count=Count("id")).order_by("type__name")
        )

        completed_state_ids = State.objects.filter(workspace__slug=slug, group="completed").values("id")
        open_state_ids = State.objects.filter(workspace__slug=slug).exclude(group="completed").values("id")
        reopen_activities = IssueActivity.objects.filter(
            issue_id__in=issue_ids,
            field__in=("state", "state_id"),
            old_identifier__in=completed_state_ids,
            new_identifier__in=open_state_ids,
        )
        reopen = reopen_activities.aggregate(
            transitions=Count("id"),
            work_items=Count("issue_id", distinct=True),
        )

        member_rows = list(
            IssueAssignee.objects.filter(issue_id__in=issue_ids, deleted_at__isnull=True)
            .values(
                "assignee_id",
                "assignee__display_name",
                "assignee__first_name",
                "assignee__last_name",
            )
            .annotate(
                assigned=Count("issue_id", distinct=True),
                completed=Count(
                    "issue_id",
                    filter=Q(issue__state__group="completed"),
                    distinct=True,
                ),
                in_progress=Count(
                    "issue_id",
                    filter=Q(issue__state__group="started"),
                    distinct=True,
                ),
                overdue=Count(
                    "issue_id",
                    filter=Q(issue__target_date__lt=reference_date)
                    & ~Q(issue__state__group__in=NON_OVERDUE_STATE_GROUPS),
                    distinct=True,
                ),
                bugs_assigned=Count(
                    "issue_id",
                    filter=Q(issue__type_id__in=bug_type_ids),
                    distinct=True,
                ),
                bugs_resolved=Count(
                    "issue_id",
                    filter=Q(
                        issue__type_id__in=bug_type_ids,
                        issue__state__group="completed",
                    ),
                    distinct=True,
                ),
            )
            .order_by("-assigned", "assignee__display_name")[:100]
        )

        project_counts = {
            row["project_id"]: row
            for row in issues.values("project_id").annotate(
                total=Count("id"),
                completed=Count("id", filter=Q(state__group="completed")),
                cancelled=Count("id", filter=Q(state__group="cancelled")),
                overdue=Count("id", filter=overdue_filter),
                open_bugs=Count(
                    "id",
                    filter=Q(
                        type_id__in=bug_type_ids,
                        state__group__in=OPEN_STATE_GROUPS,
                    ),
                ),
            )
        }
        project_report = []
        for project in projects.order_by("name")[:100]:
            row = project_counts.get(project.id, {})
            total = row.get("total", 0)
            denominator = max(total - row.get("cancelled", 0), 0)
            project_report.append(
                {
                    "id": project.id,
                    "name": project.name,
                    "identifier": project.identifier,
                    "total": total,
                    "completed": row.get("completed", 0),
                    "overdue": row.get("overdue", 0),
                    "open_bugs": row.get("open_bugs", 0),
                    "progress": (round((row.get("completed", 0) / denominator) * 100, 2) if denominator else 0),
                }
            )

        cycles = Cycle.objects.filter(
            project_id__in=accessible_project_ids,
            deleted_at__isnull=True,
            archived_at__isnull=True,
        )
        modules = Module.objects.filter(
            project_id__in=accessible_project_ids,
            deleted_at__isnull=True,
            archived_at__isnull=True,
        )

        def progress(items, through_model, relation_name):
            fields = ["id", "name", "project_id", "project__name"]
            if through_model is CycleIssue:
                fields.extend(["start_date", "end_date"])
            else:
                fields.extend(["start_date", "target_date"])
            selected = list(items.order_by("-created_at")[:100].values(*fields))
            selected_ids = [item["id"] for item in selected]
            if not selected_ids:
                return []
            relation_filter = {f"{relation_name}__in": selected_ids}
            counts = {
                row[relation_name]: row
                for row in through_model.objects.filter(
                    **relation_filter,
                    issue_id__in=issue_ids,
                    deleted_at__isnull=True,
                )
                .values(relation_name)
                .annotate(
                    total=Count("issue_id", distinct=True),
                    completed=Count(
                        "issue_id",
                        filter=Q(issue__state__group="completed"),
                        distinct=True,
                    ),
                    overdue=Count(
                        "issue_id",
                        filter=Q(issue__target_date__lt=reference_date)
                        & ~Q(issue__state__group__in=NON_OVERDUE_STATE_GROUPS),
                        distinct=True,
                    ),
                    open_bugs=Count(
                        "issue_id",
                        filter=Q(
                            issue__type_id__in=bug_type_ids,
                            issue__state__group__in=OPEN_STATE_GROUPS,
                        ),
                        distinct=True,
                    ),
                    active_members=Count("issue__issue_assignee__assignee_id", distinct=True),
                )
            }
            result = []
            for item in selected:
                row = counts.get(item["id"], {})
                total = row.get("total", 0)
                result.append(
                    {
                        **item,
                        "total": total,
                        "completed": row.get("completed", 0),
                        "overdue": row.get("overdue", 0),
                        "open_bugs": row.get("open_bugs", 0),
                        "active_members": row.get("active_members", 0),
                        "progress": (round((row.get("completed", 0) / total) * 100, 2) if total else 0),
                    }
                )
            return result

        created = {
            row["day"]: row["count"]
            for row in issues.annotate(day=TruncDate("created_at")).values("day").annotate(count=Count("id"))
        }
        resolved = {
            row["day"]: row["count"]
            for row in issues.filter(
                completed_at__date__gte=range_start,
                completed_at__date__lte=range_end,
            )
            .annotate(day=TruncDate("completed_at"))
            .values("day")
            .annotate(count=Count("id"))
        }
        trend = [
            {
                "date": (range_start + timedelta(days=offset)).isoformat(),
                "created": created.get(range_start + timedelta(days=offset), 0),
                "resolved": resolved.get(range_start + timedelta(days=offset), 0),
            }
            for offset in range((range_end - range_start).days + 1)
        ]

        automation_rules = ProjectAutomationRule.objects.filter(project_id__in=accessible_project_ids)
        automation_executions = ProjectAutomationExecution.objects.filter(
            project_id__in=accessible_project_ids,
            created_at__date__gte=range_start,
            created_at__date__lte=range_end,
        )
        execution_statuses = {
            row["status"]: row["count"] for row in automation_executions.values("status").annotate(count=Count("id"))
        }
        automation = {
            "rules": automation_rules.count(),
            "enabled_rules": automation_rules.filter(enabled=True).count(),
            "disabled_rules": automation_rules.filter(enabled=False).count(),
            "executions": automation_executions.count(),
            "successful": execution_statuses.get("success", 0),
            "failed": execution_statuses.get("failed", 0),
            "skipped": execution_statuses.get("skipped", 0),
            "average_execution_seconds": None,
            "average_execution_time_status": "insufficient_data",
        }

        return Response(
            {
                "meta": {
                    "generated_at": timezone.now(),
                    "date_from": range_start,
                    "date_to": range_end,
                    "date_basis": "work_item_created_at",
                    "count_mode": count_mode,
                    "reference_date": reference_date,
                    "member_allocation": "full_count_per_assignee",
                    "limits": {
                        "max_days": REPORT_MAX_DAYS,
                        "max_rows_per_dimension": 100,
                    },
                    "limitations": [
                        (
                            "Resolved trend uses the current completed_at value "
                            "and cannot retain a completion later followed by reopen."
                        ),
                        (
                            "Member completion is credited to every assignee "
                            "present now; historical assignee-at-completion is not stored."
                        ),
                        (
                            "Automation execution duration is unavailable because "
                            "executions do not store start and finish timestamps."
                        ),
                    ],
                },
                "totals": totals,
                "states": states,
                "priorities": priority_distribution,
                "types": type_distribution,
                "bugs": {
                    **bug_totals,
                    "by_state": list(
                        bug_issues.values(
                            "state_id",
                            "state__name",
                            "state__group",
                            "state__color",
                        )
                        .annotate(count=Count("id"))
                        .order_by("state__name")
                    ),
                    "by_priority": list(bug_issues.values("priority").annotate(count=Count("id")).order_by("priority")),
                },
                "parenting": {
                    "subtasks": totals["subtasks"],
                    "completed_subtasks": issues.filter(parent__isnull=False, state__group="completed").count(),
                    "parents_with_open_children": issues.filter(
                        parent__isnull=True,
                        parent_issue__in=issues.exclude(state__group__in=NON_OVERDUE_STATE_GROUPS).values("id"),
                    )
                    .distinct()
                    .count(),
                },
                "reopen": reopen,
                "members": member_rows,
                "projects": project_report,
                "cycles": progress(cycles, CycleIssue, "cycle_id"),
                "modules": progress(modules, ModuleIssue, "module_id"),
                "trend": trend,
                "automation": automation,
                "worklogs_available": False,
            }
        )
