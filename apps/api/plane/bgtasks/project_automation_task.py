from celery import shared_task
from django.db import OperationalError

from plane.db.models import ProjectAutomationEvent
from plane.services.automation_runtime import module_enabled, process_event
from plane.services.automation_config import RETRIES, BATCH_SIZE


@shared_task(autoretry_for=(OperationalError,), retry_backoff=True, retry_kwargs={"max_retries": RETRIES})
def run_project_automation(event_id):
    process_event(event_id)


@shared_task
def dispatch_project_automations():
    if not module_enabled():
        return
    for event_id in (
        ProjectAutomationEvent.objects.filter(processed_at__isnull=True)
        .order_by("created_at")
        .values_list("id", flat=True)[:BATCH_SIZE]
    ):
        run_project_automation.delay(str(event_id))


@shared_task
def schedule_project_automations():
    from plane.services.automation_schedule import dispatch_schedules, retain_history

    if module_enabled():
        dispatch_schedules()
        retain_history()
