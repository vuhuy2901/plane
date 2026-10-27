"""Preview and apply explicit state migration when a work type changes workflow."""

from django.db import connection, transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from plane.db.models import Issue, IssueActivity, Project, ProjectIssueType, Workflow, WorkflowIssueTypeMapping
from plane.utils.uuid import convert_uuid_to_integer


class MappingInput(serializers.Serializer):
    issue_type_id = serializers.UUIDField()
    workflow_id = serializers.UUIDField()


class MigrationInput(serializers.Serializer):
    issue_type_id = serializers.UUIDField()
    workflow_version_id = serializers.UUIDField()
    source_state_id = serializers.UUIDField(allow_null=True)
    target_state_id = serializers.UUIDField()
    work_item_count = serializers.IntegerField(min_value=1)


class MappingRequest(serializers.Serializer):
    mappings = MappingInput(many=True)
    state_migrations = MigrationInput(many=True, required=False, default=list)


def _prepare(project, payload, lock=False):
    serializer = MappingRequest(data=payload)
    serializer.is_valid(raise_exception=True)
    mappings = serializer.validated_data["mappings"]
    types = {
        item.issue_type_id: item
        for item in ProjectIssueType.objects.filter(project=project).select_related("issue_type")
    }
    workflows = Workflow.objects.filter(project=project, pk__in=[item["workflow_id"] for item in mappings])
    if lock:
        workflows = workflows.select_for_update()
    workflows = {item.pk: item for item in workflows}
    conflicts, targets, versions, seen = [], {}, {}, set()
    for item in mappings:
        type_id, workflow_id = item["issue_type_id"], item["workflow_id"]
        if type_id in seen:
            raise ValidationError({"mappings": "Each work item type can map to only one workflow."})
        seen.add(type_id)
        if type_id not in types or workflow_id not in workflows:
            raise ValidationError({"mappings": "A work item type or workflow does not belong to this project."})
        workflow = workflows[workflow_id]
        if workflow.active_version_id is None:
            raise ValidationError({"mappings": "Publish a workflow before mapping a work item type to it."})
        nodes = list(workflow.active_version.states.select_related("state"))
        if not nodes or any(
            node.state is None or node.state.project_id != project.pk or node.state.deleted_at for node in nodes
        ):
            raise ValidationError({"mappings": "The published workflow contains missing or invalid project states."})
        target_states = {node.state_id: node.state for node in nodes}
        targets[type_id], versions[type_id] = target_states, workflow.active_version_id
        issues = Issue.all_objects.filter(project=project, type_id=type_id, deleted_at__isnull=True)
        if lock:
            list(issues.select_for_update().values_list("id", flat=True))
        outside = (
            issues.exclude(state_id__in=target_states)
            .values("state_id", "state__name", "state__group")
            .annotate(n=Count("id"))
        )
        for row in outside:
            normalized = (row["state__name"] or "").casefold().replace(" ", "").replace("-", "")
            suggestions = [
                state
                for state in target_states.values()
                if state.name.casefold().replace(" ", "").replace("-", "") == normalized
                and state.group == row["state__group"]
            ]
            conflicts.append(
                {
                    "issue_type_id": str(type_id),
                    "issue_type_name": types[type_id].issue_type.name,
                    "workflow_id": str(workflow_id),
                    "workflow_name": workflow.name,
                    "workflow_version_id": str(workflow.active_version_id),
                    "source_state_id": str(row["state_id"]) if row["state_id"] else None,
                    "source_state_name": row["state__name"] or "No state",
                    "source_state_group": row["state__group"],
                    "work_item_count": row["n"],
                    "target_states": [
                        {"id": str(state.pk), "name": state.name, "group": state.group}
                        for state in target_states.values()
                    ],
                    "suggested_target_id": str(suggestions[0].pk) if len(suggestions) == 1 else None,
                }
            )
    return serializer.validated_data, conflicts, targets, versions


def preview_workflow_mappings(project, payload):
    _, conflicts, _, _ = _prepare(project, payload)
    return {"conflicts": conflicts, "work_item_count": sum(item["work_item_count"] for item in conflicts)}


@transaction.atomic
def save_workflow_mappings(project, payload, actor):
    # Issue creation takes this same project advisory lock. Concurrent edits take
    # issue row locks; all migrations and mapping changes commit together.
    Project.objects.select_for_update().get(pk=project.pk)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [convert_uuid_to_integer(project.pk)])
    data, conflicts, targets, versions = _prepare(project, payload, lock=True)
    choices = {}
    for choice in data["state_migrations"]:
        key = (str(choice["issue_type_id"]), str(choice["source_state_id"]) if choice["source_state_id"] else None)
        if key in choices:
            raise ValidationError({"state_migrations": "Duplicate state migration choice."})
        choices[key] = choice
    expected = {(item["issue_type_id"], item["source_state_id"]) for item in conflicts}
    if set(choices) != expected:
        raise ValidationError(
            {
                "mappings": {
                    "code": "STATE_MIGRATION_REQUIRED",
                    "message": "Choose a destination for each existing state before applying the workflow.",
                    "conflicts": conflicts,
                }
            }
        )
    for conflict in conflicts:
        choice = choices[(conflict["issue_type_id"], conflict["source_state_id"])]
        type_id = choice["issue_type_id"]
        if (
            choice["workflow_version_id"] != versions[type_id]
            or choice["work_item_count"] != conflict["work_item_count"]
        ):
            raise ValidationError(
                {
                    "mappings": {
                        "code": "MAPPING_PREVIEW_CHANGED",
                        "message": "The workflow or work items changed. Review the updated state migration.",
                        "conflicts": conflicts,
                    }
                }
            )
        if choice["target_state_id"] not in targets[type_id]:
            raise ValidationError(
                {"state_migrations": "The destination must be a state in the selected published workflow."}
            )
    for conflict in conflicts:
        choice = choices[(conflict["issue_type_id"], conflict["source_state_id"])]
        target = targets[choice["issue_type_id"]][choice["target_state_id"]]
        issues = Issue.all_objects.filter(
            project=project,
            type_id=choice["issue_type_id"],
            state_id=choice["source_state_id"],
            deleted_at__isnull=True,
        ).select_related("state")
        for issue in issues:
            old_state = issue.state
            completed_at = issue.completed_at
            issue.state = target
            issue.updated_by = actor
            issue.save(disable_auto_set_user=True, update_fields=["state", "completed_at", "updated_at", "updated_by"])
            if old_state and old_state.group == target.group == "completed":
                Issue.all_objects.filter(pk=issue.pk).update(completed_at=completed_at)
            IssueActivity.objects.create(
                project=project,
                issue=issue,
                actor=actor,
                verb="updated",
                field="state",
                old_value=old_state.name if old_state else None,
                new_value=target.name,
                old_identifier=old_state.pk if old_state else None,
                new_identifier=target.pk,
                comment=f"Workflow mapping migration: {conflict['workflow_name']}",
                epoch=timezone.now().timestamp(),
            )
    WorkflowIssueTypeMapping.objects.filter(project=project).delete()
    for item in data["mappings"]:
        WorkflowIssueTypeMapping.objects.create(project=project, **item)
