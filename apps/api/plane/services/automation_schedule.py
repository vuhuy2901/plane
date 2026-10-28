"""Bounded daily/weekly scheduling on the existing Celery beat infrastructure."""

from datetime import datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.db import transaction, models
from django.utils import timezone

from plane.db.models import Issue, ProjectAutomationRule, ProjectAutomationEvent
from plane.services.automation_config import BATCH_SIZE, RETENTION_DAYS
from plane.services.automation_runtime import module_enabled, schedule_event_delivery, snapshot, matches_conditions


def occurrence(options, now):
    zone = ZoneInfo(options["timezone"])
    local = now.astimezone(zone)
    day = local.date()
    if options["frequency"] == "weekly":
        day -= timedelta(days=(day.weekday() - options["weekday"]) % 7)
    due = datetime.combine(day, time.fromisoformat(options["time"]), zone)
    if due > local:
        due -= timedelta(days=7 if options["frequency"] == "weekly" else 1)
    # One occurrence per local calendar date, including daylight saving folds.
    return due


def dispatch_schedules(now=None):
    if not module_enabled():
        return
    now = now or timezone.now()
    # Rotate by updated_at, preventing starvation when there are many projects.
    ids = list(
        ProjectAutomationRule.objects.filter(enabled=True, definition__trigger="scheduled")
        .order_by("updated_at", "id")
        .values_list("id", flat=True)[:BATCH_SIZE]
    )
    for rule_id in ids:
        with transaction.atomic():
            rule = (
                ProjectAutomationRule.objects.select_for_update(skip_locked=True)
                .select_related("project")
                .filter(pk=rule_id, enabled=True)
                .first()
            )
            if not rule:
                continue
            options = rule.definition["trigger_options"]
            due = occurrence(options, now)
            cursor = rule.schedule_cursor
            # Finish a started batch even if the next daily occurrence has arrived.
            if cursor and not cursor.get("complete"):
                due = datetime.fromisoformat(cursor["occurrence"])
            if not rule.enabled_at or due < rule.enabled_at:
                ProjectAutomationRule.objects.filter(pk=rule.pk).update(updated_at=now)
                continue
            key = due.isoformat()
            if cursor.get("occurrence") != key:
                cursor = {"occurrence": key, "last_id": None, "complete": False}
            if not cursor.get("complete"):
                query = Issue.objects.filter(
                    project=rule.project, created_at__lte=due, archived_at__isnull=True, is_draft=False
                ).order_by("id")
                if cursor.get("last_id"):
                    query = query.filter(id__gt=cursor["last_id"])
                items = list(query.select_related("state", "project")[:BATCH_SIZE])
                for issue in items:
                    event_snapshot = snapshot(issue)
                    event = SimpleNamespace(snapshot=event_snapshot, created_at=due, issue_id=issue.id)
                    if matches_conditions({"conditions": options.get("filters", [])}, event, rule.project):
                        event, created = ProjectAutomationEvent.objects.get_or_create(
                            deduplication_key=f"schedule:{rule.id}:{rule.revision}:{key}:{issue.id}",
                            defaults={
                                "project": rule.project,
                                "issue": issue,
                                "snapshot": event_snapshot,
                                "triggers": ["scheduled"],
                                "candidates": [{"id": str(rule.id), "revision": rule.revision}],
                                "context": {"scheduled_for": key, "timezone": options["timezone"]},
                            },
                        )
                        if created:
                            schedule_event_delivery(event)
                    cursor["last_id"] = str(issue.id)
                cursor["complete"] = len(items) < BATCH_SIZE
            ProjectAutomationRule.objects.filter(pk=rule.pk).update(schedule_cursor=cursor, updated_at=now)


def retain_history():
    """Delete only expired, completed automation events; history cascades with them."""
    ids = list(
        ProjectAutomationEvent.objects.filter(
            processed_at__lt=timezone.now() - timedelta(days=RETENTION_DAYS)
        ).values_list("id", flat=True)[:BATCH_SIZE]
    )
    # The project base manager soft-deletes by default; retention needs a bounded hard delete.
    models.QuerySet(model=ProjectAutomationEvent, using=ProjectAutomationEvent.objects.db).filter(pk__in=ids).delete()
