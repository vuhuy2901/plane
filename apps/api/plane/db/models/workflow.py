# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from .project import ProjectBaseModel


class Workflow(ProjectBaseModel):
    """A user-defined workflow whose entire lifecycle is scoped to one project."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    active_version = models.ForeignKey(
        "db.WorkflowVersion",
        related_name="active_for_workflows",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "workflows"
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"],
                condition=Q(deleted_at__isnull=True),
                name="workflow_unique_name_project_when_active",
            )
        ]


class WorkflowVersion(ProjectBaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    workflow = models.ForeignKey(Workflow, related_name="versions", on_delete=models.CASCADE)
    version = models.PositiveIntegerField()
    revision = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="published_workflow_versions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "workflow_versions"
        ordering = ("-version",)
        constraints = [
            models.UniqueConstraint(
                fields=["workflow", "version"],
                condition=Q(deleted_at__isnull=True),
                name="workflow_version_unique_number_when_active",
            ),
            models.UniqueConstraint(
                fields=["workflow"],
                condition=Q(status="draft", deleted_at__isnull=True),
                name="workflow_version_one_draft",
            ),
        ]


class WorkflowVersionState(ProjectBaseModel):
    """A versioned workflow node; ``key`` stays stable when a version is cloned."""

    workflow_version = models.ForeignKey(WorkflowVersion, related_name="states", on_delete=models.CASCADE)
    key = models.UUIDField(default=uuid.uuid4, db_index=True)
    state = models.ForeignKey(
        "db.State",
        related_name="workflow_version_states",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=255)
    group = models.CharField(max_length=20)
    is_start = models.BooleanField(default=False)
    is_end = models.BooleanField(default=False)

    class Meta:
        db_table = "workflow_version_states"
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["workflow_version", "key"],
                condition=Q(deleted_at__isnull=True),
                name="workflow_state_unique_key_per_version",
            ),
            models.UniqueConstraint(
                fields=["workflow_version"],
                condition=Q(is_start=True, deleted_at__isnull=True),
                name="workflow_version_one_start_state",
            ),
        ]


class WorkflowStateLayout(ProjectBaseModel):
    """Canvas-only data kept separate from transition semantics."""

    workflow_state = models.OneToOneField(
        WorkflowVersionState,
        related_name="layout",
        on_delete=models.CASCADE,
    )
    position_x = models.FloatField(default=0)
    position_y = models.FloatField(default=0)

    class Meta:
        db_table = "workflow_state_layouts"


class WorkflowTransition(ProjectBaseModel):
    workflow_version = models.ForeignKey(WorkflowVersion, related_name="transitions", on_delete=models.CASCADE)
    source = models.ForeignKey(
        WorkflowVersionState,
        related_name="outgoing_transitions",
        on_delete=models.CASCADE,
    )
    target = models.ForeignKey(
        WorkflowVersionState,
        related_name="incoming_transitions",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    conditions = models.JSONField(default=list, blank=True)
    permissions = models.JSONField(default=dict, blank=True)
    validators = models.JSONField(default=list, blank=True)
    post_actions = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "workflow_transitions"
        ordering = ("created_at",)


class WorkflowIssueTypeMapping(ProjectBaseModel):
    issue_type = models.ForeignKey(
        "db.IssueType",
        related_name="workflow_mappings",
        on_delete=models.CASCADE,
    )
    workflow = models.ForeignKey(Workflow, related_name="issue_type_mappings", on_delete=models.CASCADE)

    class Meta:
        db_table = "workflow_issue_type_mappings"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "issue_type"],
                condition=Q(deleted_at__isnull=True),
                name="workflow_mapping_unique_project_issue_type",
            )
        ]


class WorkflowTransitionAudit(ProjectBaseModel):
    issue = models.ForeignKey("db.Issue", related_name="workflow_transition_audits", on_delete=models.CASCADE)
    workflow = models.ForeignKey(Workflow, related_name="transition_audits", on_delete=models.PROTECT)
    workflow_version = models.ForeignKey(WorkflowVersion, related_name="transition_audits", on_delete=models.PROTECT)
    transition = models.ForeignKey(
        WorkflowTransition,
        related_name="audits",
        on_delete=models.PROTECT,
    )
    source_state = models.ForeignKey(
        "db.State",
        related_name="workflow_transition_audits_from",
        on_delete=models.PROTECT,
    )
    target_state = models.ForeignKey(
        "db.State",
        related_name="workflow_transition_audits_to",
        on_delete=models.PROTECT,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="workflow_transition_audits",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "workflow_transition_audits"
        ordering = ("-created_at",)
