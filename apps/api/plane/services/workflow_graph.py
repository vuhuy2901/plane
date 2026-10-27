"""Persist directed graph identity independently from canvas coordinates."""

import math
import uuid

from rest_framework import serializers
from rest_framework.exceptions import APIException, ValidationError

from plane.db.models import State, StateGroup, WorkflowStateLayout, WorkflowTransition, WorkflowVersionState


class DraftConflict(APIException):
    status_code = 409
    default_detail = "This draft changed in another session. Reload it before saving."
    default_code = "WORKFLOW_DRAFT_CHANGED"


class LayoutInput(serializers.Serializer):
    position_x = serializers.FloatField(default=0)
    position_y = serializers.FloatField(default=0)

    def validate(self, attrs):
        if not all(math.isfinite(value) for value in attrs.values()):
            raise ValidationError("Canvas positions must be finite numbers.")
        return attrs


class NodeInput(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    key = serializers.UUIDField()
    state_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(allow_blank=True, default="")
    color = serializers.CharField(max_length=255, default="#60646C")
    group = serializers.ChoiceField(choices=StateGroup.choices, default="unstarted")
    is_start = serializers.BooleanField(default=False)
    is_end = serializers.BooleanField(default=False)
    layout = LayoutInput(default=dict)


class EdgeInput(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    source_key = serializers.UUIDField()
    target_key = serializers.UUIDField()
    name = serializers.CharField(max_length=255, default="Transition")
    source_handle = serializers.CharField(required=False, allow_null=True)
    target_handle = serializers.CharField(required=False, allow_null=True)
    conditions = serializers.ListField(child=serializers.DictField(), default=list)
    permissions = serializers.DictField(default=dict)
    validators = serializers.ListField(child=serializers.DictField(), default=list)
    post_actions = serializers.ListField(child=serializers.DictField(), default=list)


class GraphInput(serializers.Serializer):
    draft_id = serializers.UUIDField(required=False)
    expected_revision = serializers.IntegerField(min_value=0, required=False)
    states = NodeInput(many=True)
    transitions = EdgeInput(many=True)


def assert_draft_revision(draft, payload):
    # Old API clients remain accepted. The editor always supplies both tokens.
    if "draft_id" in payload and str(payload["draft_id"]) != str(draft.pk):
        raise DraftConflict()
    if "expected_revision" in payload and payload["expected_revision"] != draft.revision:
        raise DraftConflict()


def save_workflow_graph(draft, payload, actor):
    """Caller must hold the draft row lock inside a transaction."""
    serializer = GraphInput(data=payload)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    assert_draft_revision(draft, data)
    keys = [item["key"] for item in data["states"]]
    if len(set(keys)) != len(keys):
        raise ValidationError({"states": "State keys must be unique."})
    if sum(item["is_start"] for item in data["states"]) > 1:
        raise ValidationError({"states": "Choose only one start state."})
    linked = [item["state_id"] for item in data["states"] if item["state_id"]]
    if len(set(linked)) != len(linked):
        raise ValidationError({"states": "Each Plane state can appear only once in a workflow."})
    if State.objects.filter(project=draft.project, pk__in=linked).count() != len(linked):
        raise ValidationError({"states": "A linked Plane state does not belong to this project."})
    pairs, edge_ids = set(), set()
    for item in data["transitions"]:
        pair = (item["source_key"], item["target_key"])
        if pair[0] not in keys or pair[1] not in keys:
            raise ValidationError({"transitions": "A transition references a missing state."})
        if pair in pairs:
            raise ValidationError({"transitions": "A transition in this direction already exists."})
        pairs.add(pair)
        if item.get("id") in edge_ids:
            raise ValidationError({"transitions": "Transition IDs must be unique."})
        if item.get("id"):
            edge_ids.add(item["id"])
    WorkflowVersionState.objects.filter(workflow_version=draft, is_start=True).update(is_start=False)
    nodes = {}
    for item in data["states"]:
        values = {
            name: item[name] for name in ("name", "description", "color", "group", "is_start", "is_end", "state_id")
        }
        node = WorkflowVersionState.objects.filter(workflow_version=draft, key=item["key"]).first()
        if node is None:
            node = (
                WorkflowVersionState.all_objects.filter(workflow_version=draft, key=item["key"])
                .order_by("-created_at")
                .first()
            )
        if node is None:
            node = WorkflowVersionState(
                project=draft.project, workflow_version=draft, key=item["key"], created_by=actor
            )
        if item.get("id") and item["id"] != node.id:
            raise ValidationError({"states": "The state ID does not match this draft's state key."})
        for name, value in values.items():
            setattr(node, name, value)
        node.deleted_at, node.updated_by = None, actor
        node.save(disable_auto_set_user=True)
        layout = item["layout"]
        WorkflowStateLayout.all_objects.update_or_create(
            workflow_state=node,
            defaults={
                "project": draft.project,
                "workspace": draft.workspace,
                "deleted_at": None,
                "position_x": layout.get("position_x", 0),
                "position_y": layout.get("position_y", 0),
            },
        )
        nodes[item["key"]] = node
    retained_edges = []
    for item in data["transitions"]:
        edge = None
        if item.get("id"):
            edge = WorkflowTransition.all_objects.filter(pk=item["id"]).first()
            if edge and edge.workflow_version_id != draft.pk:
                raise ValidationError({"transitions": "A transition ID belongs to another workflow version."})
        else:
            edge = WorkflowTransition.objects.filter(
                workflow_version=draft, source=nodes[item["source_key"]], target=nodes[item["target_key"]]
            ).first()
        if edge is None:
            edge = WorkflowTransition(
                id=item.get("id") or uuid.uuid4(), project=draft.project, workflow_version=draft, created_by=actor
            )
        edge.source, edge.target = nodes[item["source_key"]], nodes[item["target_key"]]
        for name in ("name", "conditions", "permissions", "validators", "post_actions"):
            setattr(edge, name, item[name])
        edge.permissions = dict(edge.permissions)
        for name in ("source_handle", "target_handle"):
            if name in item and (item[name] is not None or name in edge.permissions):
                edge.permissions[name] = item[name]
        edge.deleted_at, edge.updated_by = None, actor
        edge.save(disable_auto_set_user=True)
        retained_edges.append(edge.pk)
    WorkflowTransition.objects.filter(workflow_version=draft).exclude(pk__in=retained_edges).delete()
    removed_nodes = WorkflowVersionState.objects.filter(workflow_version=draft).exclude(key__in=keys)
    WorkflowStateLayout.objects.filter(workflow_state__in=removed_nodes).delete()
    removed_nodes.delete()
    draft.revision += 1
    draft.save(update_fields=["revision", "updated_at"])
    return draft
