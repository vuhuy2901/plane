from django.conf import settings
from django.db import models

from .project import ProjectBaseModel


class ProjectAutomationRule(ProjectBaseModel):
    definition = models.JSONField(default=dict)
    enabled = models.BooleanField(default=False)
    enabled_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=0)
    schedule_cursor = models.JSONField(default=dict)
    execution_actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="automation_rules"
    )

    class Meta:
        db_table = "project_automation_rules"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["project", "enabled"], name="automation_project_enabled_idx")]


class ProjectAutomationEvent(ProjectBaseModel):
    issue = models.ForeignKey("db.Issue", null=True, on_delete=models.SET_NULL)
    snapshot = models.JSONField(default=dict)
    before_snapshot = models.JSONField(null=True)
    context = models.JSONField(default=dict)
    progress = models.JSONField(default=dict)
    deduplication_key = models.CharField(max_length=255, null=True, unique=True)
    candidates = models.JSONField(default=list)
    triggers = models.JSONField(default=list)
    processed_at = models.DateTimeField(null=True)
    delivery_attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        db_table = "project_automation_events"
        indexes = [models.Index(fields=["processed_at", "created_at"], name="automation_pending_event_idx")]


class ProjectAutomationExecution(ProjectBaseModel):
    event = models.ForeignKey(ProjectAutomationEvent, on_delete=models.CASCADE)
    rule = models.ForeignKey(ProjectAutomationRule, null=True, on_delete=models.SET_NULL)
    rule_key = models.UUIDField()
    snapshot = models.JSONField(default=dict)
    status = models.CharField(
        max_length=10, choices=[("success", "Success"), ("failed", "Failed"), ("skipped", "Skipped")]
    )
    detail = models.TextField(blank=True)

    class Meta:
        db_table = "project_automation_executions"
        constraints = [models.UniqueConstraint(fields=["event", "rule_key"], name="automation_event_rule_once")]
        ordering = ("-created_at",)
