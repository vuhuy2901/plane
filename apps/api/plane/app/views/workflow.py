# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import re

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from plane.app.permissions import ProjectAdminPermission, ProjectEntityPermission
from plane.app.serializers.workflow import (
    WorkflowSerializer,
    WorkflowTransitionSerializer,
    WorkflowVersionSerializer,
    WorkflowVersionStateSerializer,
)
from plane.db.models import (
    Issue,
    IssueType,
    DraftIssue,
    Project,
    ProjectIssueType,
    Workflow,
    WorkflowIssueTypeMapping,
    WorkflowStateLayout,
    WorkflowTransition,
    WorkflowTransitionAudit,
    WorkflowVersion,
    WorkflowVersionState,
)
from plane.services.workflow import (
    WorkflowRuleError,
    get_available_transitions,
    get_effective_workflow_version,
    next_workflow_version,
    publish_workflow,
    validate_workflow_version,
)
from plane.api.middleware.api_authentication import APIKeyAuthentication
from plane.services.workflow_mapping import preview_workflow_mappings, save_workflow_mappings
from plane.services.workflow_graph import assert_draft_revision, save_workflow_graph
from plane.authentication.session import BaseSessionAuthentication

from .base import BaseAPIView


class WorkflowBaseAPIView(BaseAPIView):
    # The same implementation is mounted under both /api (web session) and
    # /api/v1 (API token/MCP), so every client sees identical workflow rules.
    authentication_classes = [BaseSessionAuthentication, APIKeyAuthentication]


def _workflow_queryset(slug, project_id):
    return Workflow.objects.filter(workspace__slug=slug, project_id=project_id).prefetch_related(
        "versions", "issue_type_mappings"
    )


def _copy_version(source, workflow):
    target = WorkflowVersion.objects.create(
        project=workflow.project,
        workflow=workflow,
        version=next_workflow_version(workflow),
        status=WorkflowVersion.Status.DRAFT,
    )
    node_map = {}
    for source_node in source.states.select_related("layout"):
        node = WorkflowVersionState.objects.create(
            project=workflow.project,
            workflow_version=target,
            key=source_node.key,
            state=source_node.state,
            name=source_node.name,
            description=source_node.description,
            color=source_node.color,
            group=source_node.group,
            is_start=source_node.is_start,
            is_end=source_node.is_end,
        )
        layout = getattr(source_node, "layout", None)
        WorkflowStateLayout.objects.create(
            project=workflow.project,
            workflow_state=node,
            position_x=layout.position_x if layout else 0,
            position_y=layout.position_y if layout else 0,
        )
        node_map[source_node.id] = node
    for edge in source.transitions.all():
        WorkflowTransition.objects.create(
            project=workflow.project,
            workflow_version=target,
            source=node_map[edge.source_id],
            target=node_map[edge.target_id],
            name=edge.name,
            conditions=edge.conditions,
            permissions=edge.permissions,
            validators=edge.validators,
            post_actions=edge.post_actions,
        )
    return target


class WorkflowListCreateAPIView(WorkflowBaseAPIView):
    permission_classes = [ProjectAdminPermission]

    def get(self, request, slug, project_id):
        workflows = _workflow_queryset(slug, project_id)
        return Response(WorkflowSerializer(workflows, many=True).data)

    def post(self, request, slug, project_id):
        name = str(request.data.get("name", "")).strip()
        if not name:
            raise ValidationError({"name": "A workflow name is required."})
        project = Project.objects.get(pk=project_id, workspace__slug=slug)
        with transaction.atomic():
            workflow = Workflow.objects.create(
                project=project,
                name=name,
                description=request.data.get("description", ""),
            )
            WorkflowVersion.objects.create(project=project, workflow=workflow, version=1)
        return Response(WorkflowSerializer(workflow).data, status=status.HTTP_201_CREATED)


class WorkflowDetailAPIView(WorkflowBaseAPIView):
    permission_classes = [ProjectAdminPermission]

    def get(self, request, slug, project_id, workflow_id):
        workflow = _workflow_queryset(slug, project_id).get(pk=workflow_id)
        return Response(WorkflowSerializer(workflow).data)

    def patch(self, request, slug, project_id, workflow_id):
        workflow = _workflow_queryset(slug, project_id).get(pk=workflow_id)
        if "name" in request.data:
            raw_name = request.data["name"]
            name = raw_name.strip() if isinstance(raw_name, str) else ""
            if not name:
                raise ValidationError({"name": "A workflow name is required."})
            if len(name) > 255:
                raise ValidationError({"name": "A workflow name must be 255 characters or fewer."})
            if Workflow.objects.filter(project_id=project_id, name__iexact=name).exclude(pk=workflow_id).exists():
                raise ValidationError({"name": "This project already has a workflow with that name."})
            workflow.name = name
        if "description" in request.data:
            workflow.description = request.data["description"]
        workflow.save()
        return Response(WorkflowSerializer(workflow).data)

    def delete(self, request, slug, project_id, workflow_id):
        with transaction.atomic():
            workflow = _workflow_queryset(slug, project_id).select_for_update().get(pk=workflow_id)
            if workflow.issue_type_mappings.exists():
                raise ValidationError({"workflow": "Remove all work item type mappings before deleting this workflow."})
            if WorkflowTransitionAudit.all_objects.filter(workflow=workflow).exists():
                raise ValidationError({"workflow": "This workflow has transition history and cannot be deleted."})
            # A published workflow points at one of its own versions with
            # PROTECT; clear that link before soft-deleting the workflow.
            if workflow.active_version_id:
                workflow.active_version = None
                workflow.save(update_fields=["active_version"])
            workflow.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkflowDraftAPIView(WorkflowBaseAPIView):
    permission_classes = [ProjectAdminPermission]

    def _draft(self, slug, project_id, workflow_id, create=False):
        workflow = _workflow_queryset(slug, project_id).select_for_update().get(pk=workflow_id)
        draft = workflow.versions.filter(status=WorkflowVersion.Status.DRAFT).first()
        if draft is None and create:
            if workflow.active_version_id is None:
                draft = WorkflowVersion.objects.create(
                    project=workflow.project,
                    workflow=workflow,
                    version=next_workflow_version(workflow),
                )
            else:
                draft = _copy_version(workflow.active_version, workflow)
        return workflow, draft

    def get(self, request, slug, project_id, workflow_id):
        with transaction.atomic():
            _, draft = self._draft(slug, project_id, workflow_id, create=True)
            return Response(WorkflowVersionSerializer(draft).data)

    def put(self, request, slug, project_id, workflow_id):
        with transaction.atomic():
            _, draft = self._draft(slug, project_id, workflow_id, create=True)
            draft = WorkflowVersion.objects.select_for_update().get(pk=draft.pk)
            save_workflow_graph(draft, request.data, request.user)
            return Response(WorkflowVersionSerializer(draft).data)


class WorkflowValidateAPIView(WorkflowBaseAPIView):
    permission_classes = [ProjectAdminPermission]

    def post(self, request, slug, project_id, workflow_id):
        workflow = _workflow_queryset(slug, project_id).get(pk=workflow_id)
        draft = workflow.versions.filter(status=WorkflowVersion.Status.DRAFT).first()
        if draft is None:
            raise ValidationError({"workflow": "This workflow has no draft."})
        return Response(validate_workflow_version(draft))


class WorkflowPublishAPIView(WorkflowBaseAPIView):
    permission_classes = [ProjectAdminPermission]

    def post(self, request, slug, project_id, workflow_id):
        with transaction.atomic():
            workflow = _workflow_queryset(slug, project_id).select_for_update().get(pk=workflow_id)
            draft = workflow.versions.select_for_update().filter(status=WorkflowVersion.Status.DRAFT).first()
            if draft is None:
                raise ValidationError({"workflow": "This workflow has no draft."})
            assert_draft_revision(draft, request.data)
            try:
                published, validation = publish_workflow(draft, request.user)
            except WorkflowRuleError as exc:
                raise ValidationError(exc.as_dict()) from exc
            return Response({"version": WorkflowVersionSerializer(published).data, "validation": validation})


class WorkflowVersionsAPIView(WorkflowBaseAPIView):
    permission_classes = [ProjectAdminPermission]

    def get(self, request, slug, project_id, workflow_id):
        workflow = _workflow_queryset(slug, project_id).get(pk=workflow_id)
        versions = workflow.versions.filter(status=WorkflowVersion.Status.PUBLISHED)
        return Response(WorkflowVersionSerializer(versions, many=True).data)


class WorkflowRollbackAPIView(WorkflowBaseAPIView):
    permission_classes = [ProjectAdminPermission]

    def post(self, request, slug, project_id, workflow_id, version_id):
        with transaction.atomic():
            workflow = _workflow_queryset(slug, project_id).select_for_update().get(pk=workflow_id)
            current_draft = workflow.versions.filter(status=WorkflowVersion.Status.DRAFT).first()
            if current_draft is not None:
                if request.data.get("replace_draft") is not True:
                    raise ValidationError(
                        {"workflow": "Confirm replace_draft to discard the current draft before starting a rollback."}
                    )
                current_draft.delete()
            source = workflow.versions.get(pk=version_id, status=WorkflowVersion.Status.PUBLISHED)
            draft = _copy_version(source, workflow)
        return Response(WorkflowVersionSerializer(draft).data, status=status.HTTP_201_CREATED)


class WorkflowMappingsAPIView(WorkflowBaseAPIView):
    permission_classes = [ProjectAdminPermission]

    def get(self, request, slug, project_id):
        mappings = WorkflowIssueTypeMapping.objects.filter(project_id=project_id, workspace__slug=slug)
        return Response(
            [{"issue_type_id": str(item.issue_type_id), "workflow_id": str(item.workflow_id)} for item in mappings]
        )

    def post(self, request, slug, project_id):
        project = Project.objects.get(pk=project_id, workspace__slug=slug)
        return Response(preview_workflow_mappings(project, request.data))

    def put(self, request, slug, project_id):
        project = Project.objects.get(pk=project_id, workspace__slug=slug)
        save_workflow_mappings(project, request.data, request.user)
        return self.get(request, slug, project_id)


class WorkflowIssueTypesAPIView(WorkflowBaseAPIView):
    """Minimal self-hosted project type management used by workflow mapping."""

    permission_classes = [ProjectAdminPermission]

    def get_permissions(self):
        # Work item creators need to read the project's available types; only admins
        # may create, rename, or remove those types.
        self.permission_classes = (
            [ProjectEntityPermission] if self.request.method == "GET" else [ProjectAdminPermission]
        )
        return super().get_permissions()

    def get(self, request, slug, project_id):
        items = ProjectIssueType.objects.filter(project_id=project_id, workspace__slug=slug).select_related(
            "issue_type"
        )
        return Response(
            [
                {
                    "id": str(item.issue_type_id),
                    "name": item.issue_type.name,
                    "color": item.issue_type.color,
                    "description": item.issue_type.description,
                    "is_default": item.is_default,
                    "is_active": item.issue_type.is_active,
                    "level": item.level,
                }
                for item in items
            ]
        )

    def post(self, request, slug, project_id):
        name = str(request.data.get("name", "")).strip()
        color = _work_type_color(request.data.get("color", "#3E63DD"))
        if not name:
            raise ValidationError({"name": "A work item type name is required."})
        project = Project.objects.get(pk=project_id, workspace__slug=slug)
        if ProjectIssueType.objects.filter(project=project, issue_type__name__iexact=name).exists():
            raise ValidationError({"name": "This project already has a work item type with that name."})
        with transaction.atomic():
            issue_type = IssueType.objects.create(
                workspace=project.workspace,
                name=name,
                description=request.data.get("description", ""),
                color=color,
                is_default=False,
                is_active=True,
            )
            project_type = ProjectIssueType.objects.create(
                project=project,
                issue_type=issue_type,
                is_default=bool(request.data.get("is_default", False)),
            )
            if project_type.is_default:
                ProjectIssueType.objects.filter(project=project).exclude(pk=project_type.pk).update(is_default=False)
        return Response(
            {
                "id": str(issue_type.id),
                "name": issue_type.name,
                "description": issue_type.description,
                "color": issue_type.color,
                "is_default": project_type.is_default,
                "is_active": issue_type.is_active,
                "level": project_type.level,
            },
            status=status.HTTP_201_CREATED,
        )


def _work_type_color(value):
    if not isinstance(value, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
        raise ValidationError({"color": "Choose a valid color in #RRGGBB format."})
    return value.upper()


class WorkflowIssueTypeDetailAPIView(WorkflowBaseAPIView):
    permission_classes = [ProjectAdminPermission]

    def _project_type(self, slug, project_id, issue_type_id):
        return ProjectIssueType.objects.select_related("issue_type").get(
            project_id=project_id,
            workspace__slug=slug,
            issue_type_id=issue_type_id,
        )

    def patch(self, request, slug, project_id, issue_type_id):
        project_type = self._project_type(slug, project_id, issue_type_id)
        if "name" not in request.data:
            raise ValidationError({"name": "A work item type name is required."})
        raw_name = request.data["name"]
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if not name:
            raise ValidationError({"name": "A work item type name is required."})
        if len(name) > 255:
            raise ValidationError({"name": "A work item type name must be 255 characters or fewer."})
        issue_type = project_type.issue_type
        color = _work_type_color(request.data.get("color", issue_type.color))
        # IssueType is workspace-scoped and can be shared by several projects.
        # Legacy imports may already contain case-insensitive duplicates. An
        # unchanged name must not prevent editing that existing type's color.
        if name != issue_type.name:
            duplicate = IssueType.objects.filter(workspace=issue_type.workspace, name__iexact=name)
            if duplicate.exclude(pk=issue_type.pk).exists():
                raise ValidationError({"name": "This workspace already has a work item type with that name."})
        issue_type.name = name
        issue_type.color = color
        issue_type.save(update_fields=["name", "color", "updated_at"])
        return Response(
            {
                "id": str(issue_type.id),
                "name": issue_type.name,
                "color": issue_type.color,
                "description": issue_type.description,
                "is_default": project_type.is_default,
                "is_active": issue_type.is_active,
                "level": project_type.level,
            }
        )

    def delete(self, request, slug, project_id, issue_type_id):
        with transaction.atomic():
            project_type = self._project_type(slug, project_id, issue_type_id)
            issue_type = project_type.issue_type
            if project_type.is_default or issue_type.is_default:
                raise ValidationError({"issue_type": "The default work item type cannot be deleted."})
            has_issues = Issue.all_objects.filter(
                project_id=project_id, type=issue_type, deleted_at__isnull=True
            ).exists()
            has_drafts = DraftIssue.all_objects.filter(
                project_id=project_id, type=issue_type, deleted_at__isnull=True
            ).exists()
            if has_issues or has_drafts:
                raise ValidationError(
                    {"issue_type": "Move or change the type of existing work items before deleting it."}
                )

            WorkflowIssueTypeMapping.objects.filter(project_id=project_id, issue_type=issue_type).delete()
            project_type.delete()
            # Keep the workspace type when another project still uses it.
            if (
                not ProjectIssueType.objects.filter(issue_type=issue_type).exists()
                and not Issue.all_objects.filter(type=issue_type).exists()
                and not DraftIssue.all_objects.filter(type=issue_type).exists()
            ):
                issue_type.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkflowIssueTypeHierarchyAPIView(WorkflowBaseAPIView):
    permission_classes = [ProjectAdminPermission]

    def put(self, request, slug, project_id):
        levels = request.data.get("levels")
        if not isinstance(levels, list):
            raise ValidationError({"levels": "Expected a list of work item type levels."})
        project = Project.objects.get(pk=project_id, workspace__slug=slug)
        normalized = {}
        for item in levels:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise ValidationError({"levels": "Each entry must include a work item type id and level."})
            try:
                level = int(item.get("level"))
            except (TypeError, ValueError):
                raise ValidationError({"levels": "Hierarchy levels must be integers from 0 to 4."})
            if level < 0 or level > 4:
                raise ValidationError({"levels": "Hierarchy levels must be integers from 0 to 4."})
            normalized[item["id"]] = level
        project_types = list(ProjectIssueType.objects.filter(project=project, issue_type_id__in=normalized))
        if len(project_types) != len(normalized):
            raise ValidationError({"levels": "One or more work item types do not belong to this project."})
        with transaction.atomic():
            for project_type in project_types:
                project_type.level = normalized[str(project_type.issue_type_id)]
                project_type.save(update_fields=["level", "updated_at"])
        return Response([{"id": str(item.issue_type_id), "level": item.level} for item in project_types])


class IssueWorkflowPreviewAPIView(WorkflowBaseAPIView):
    """Read-only published graph for the work item's effective workflow, available to project members."""

    permission_classes = [ProjectEntityPermission]

    def get(self, request, slug, project_id, issue_id):
        issue = get_object_or_404(Issue, pk=issue_id, project_id=project_id, workspace__slug=slug)
        version = get_effective_workflow_version(issue)
        payload = {"current_state_id": str(issue.state_id) if issue.state_id else None, "workflow": None}
        if version is not None and version.status == WorkflowVersion.Status.PUBLISHED:
            # Show graph topology, never private rule configuration or post-action credentials.
            transitions = [
                {
                    "id": str(edge.id),
                    "source_key": str(edge.source.key),
                    "target_key": str(edge.target.key),
                    "source_handle": edge.permissions.get("source_handle"),
                    "target_handle": edge.permissions.get("target_handle"),
                    "name": edge.name,
                }
                for edge in version.transitions.select_related("source", "target")
            ]
            payload["workflow"] = {
                "id": str(version.workflow_id),
                "name": version.workflow.name,
                "version": version.version,
                "states": WorkflowVersionStateSerializer(version.states.select_related("layout"), many=True).data,
                "transitions": transitions,
            }
        return Response(payload)


class IssueWorkflowTransitionsAPIView(WorkflowBaseAPIView):
    permission_classes = [ProjectEntityPermission]

    def get(self, request, slug, project_id, issue_id):
        issue = Issue.objects.select_related("type", "state").get(
            pk=issue_id, project_id=project_id, workspace__slug=slug
        )
        transitions = get_available_transitions(issue, request.user)
        if transitions is None:
            return Response({"workflow_enabled": False, "transitions": []})
        current_state = None
        if issue.state:
            current_state = {
                "id": str(issue.state.id),
                "name": issue.state.name,
                "color": issue.state.color,
                "group": issue.state.group,
                "order": getattr(issue.state, "order", 0),
            }
        return Response(
            {
                "workflow_enabled": True,
                "current_state": current_state,
                "transitions": WorkflowTransitionSerializer(transitions, many=True).data,
            }
        )


class WorkItemTypeWorkflowStatesAPIView(WorkflowBaseAPIView):
    permission_classes = [ProjectEntityPermission]

    def get(self, request, slug, project_id, issue_type_id):
        mapping = (
            WorkflowIssueTypeMapping.objects.filter(
                project_id=project_id,
                workspace__slug=slug,
                issue_type_id=issue_type_id,
                workflow__active_version__isnull=False,
            )
            .select_related("workflow__active_version")
            .first()
        )
        if mapping is None:
            return Response({"workflow_enabled": False, "state_ids": [], "start_state_id": None})
        nodes = mapping.workflow.active_version.states.exclude(state_id__isnull=True)
        start = nodes.filter(is_start=True).values_list("state_id", flat=True).first()
        return Response(
            {
                "workflow_enabled": True,
                "state_ids": [str(state_id) for state_id in nodes.values_list("state_id", flat=True)],
                "start_state_id": str(start) if start else None,
            }
        )
