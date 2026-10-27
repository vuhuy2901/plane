# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from rest_framework import serializers

from plane.db.models import (
    Workflow,
    WorkflowIssueTypeMapping,
    WorkflowStateLayout,
    WorkflowTransition,
    WorkflowTransitionAudit,
    WorkflowVersion,
    WorkflowVersionState,
)

from .base import BaseSerializer


class WorkflowStateLayoutSerializer(BaseSerializer):
    class Meta:
        model = WorkflowStateLayout
        fields = ["position_x", "position_y"]


class WorkflowVersionStateSerializer(BaseSerializer):
    layout = WorkflowStateLayoutSerializer(read_only=True)

    class Meta:
        model = WorkflowVersionState
        fields = [
            "id",
            "key",
            "state_id",
            "name",
            "description",
            "color",
            "group",
            "is_start",
            "is_end",
            "layout",
        ]


class WorkflowTransitionSerializer(BaseSerializer):
    source_key = serializers.UUIDField(source="source.key", read_only=True)
    target_key = serializers.UUIDField(source="target.key", read_only=True)
    target_state_id = serializers.UUIDField(source="target.state_id", read_only=True, allow_null=True)
    source_handle = serializers.CharField(source="permissions.source_handle", read_only=True, allow_null=True)
    target_handle = serializers.CharField(source="permissions.target_handle", read_only=True, allow_null=True)
    direction = serializers.SerializerMethodField()
    target_state = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowTransition
        fields = [
            "id",
            "source_key",
            "target_key",
            "target_state_id",
            "target_state",
            "direction",
            "source_handle",
            "target_handle",
            "name",
            "conditions",
            "permissions",
            "validators",
            "post_actions",
        ]

    def get_direction(self, obj):
        return getattr(obj, "direction", "forward")

    def get_target_state(self, obj):
        target = getattr(obj, "target", None)
        if target is None:
            return None
        state = getattr(target, "state", None)
        if state is not None:
            return {
                "id": str(state.id),
                "name": state.name,
                "color": state.color,
                "group": state.group,
                "order": getattr(state, "order", 0),
            }
        return {
            "id": str(target.state_id) if getattr(target, "state_id", None) else None,
            "name": getattr(target, "name", ""),
            "color": getattr(target, "color", "#3E63DD"),
            "group": getattr(target, "group", "unstarted"),
            "order": 0,
        }


class WorkflowVersionSerializer(BaseSerializer):
    states = WorkflowVersionStateSerializer(many=True, read_only=True)
    transitions = WorkflowTransitionSerializer(many=True, read_only=True)

    class Meta:
        model = WorkflowVersion
        fields = [
            "id",
            "version",
            "revision",
            "status",
            "published_at",
            "published_by_id",
            "states",
            "transitions",
        ]


class WorkflowSerializer(BaseSerializer):
    active_version_id = serializers.UUIDField(read_only=True, allow_null=True)
    draft_version_id = serializers.SerializerMethodField()
    mapped_issue_type_ids = serializers.SerializerMethodField()

    def get_draft_version_id(self, obj):
        draft = obj.versions.filter(status=WorkflowVersion.Status.DRAFT).first()
        return str(draft.id) if draft else None

    def get_mapped_issue_type_ids(self, obj):
        return [str(value) for value in obj.issue_type_mappings.values_list("issue_type_id", flat=True)]

    class Meta:
        model = Workflow
        fields = [
            "id",
            "name",
            "description",
            "active_version_id",
            "draft_version_id",
            "mapped_issue_type_ids",
            "created_at",
            "updated_at",
        ]


class WorkflowIssueTypeMappingSerializer(BaseSerializer):
    class Meta:
        model = WorkflowIssueTypeMapping
        fields = ["id", "issue_type_id", "workflow_id"]


class WorkflowTransitionAuditSerializer(BaseSerializer):
    class Meta:
        model = WorkflowTransitionAudit
        fields = [
            "id",
            "issue_id",
            "workflow_id",
            "workflow_version_id",
            "transition_id",
            "source_state_id",
            "target_state_id",
            "actor_id",
            "metadata",
            "created_at",
        ]
