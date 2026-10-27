# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.app.views.workflow import (
    IssueWorkflowPreviewAPIView,
    IssueWorkflowTransitionsAPIView,
    WorkflowDetailAPIView,
    WorkflowDraftAPIView,
    WorkflowListCreateAPIView,
    WorkflowMappingsAPIView,
    WorkflowIssueTypesAPIView,
    WorkflowIssueTypeDetailAPIView,
    WorkflowIssueTypeHierarchyAPIView,
    WorkflowPublishAPIView,
    WorkflowRollbackAPIView,
    WorkflowValidateAPIView,
    WorkflowVersionsAPIView,
    WorkItemTypeWorkflowStatesAPIView,
)

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/workflow/",
        IssueWorkflowPreviewAPIView.as_view(),
        name="work-item-workflow-preview",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/workflows/",
        WorkflowListCreateAPIView.as_view(),
        name="project-workflows",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/workflows/mappings/",
        WorkflowMappingsAPIView.as_view(),
        name="project-workflow-mappings",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/workflow-issue-types/",
        WorkflowIssueTypesAPIView.as_view(),
        name="project-workflow-issue-types",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/workflow-issue-types/<uuid:issue_type_id>/",
        WorkflowIssueTypeDetailAPIView.as_view(),
        name="project-workflow-issue-type-detail",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-item-hierarchy/",
        WorkflowIssueTypeHierarchyAPIView.as_view(),
        name="project-work-item-hierarchy",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/workflows/<uuid:workflow_id>/",
        WorkflowDetailAPIView.as_view(),
        name="project-workflow-detail",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/workflows/<uuid:workflow_id>/draft/",
        WorkflowDraftAPIView.as_view(),
        name="project-workflow-draft",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/workflows/<uuid:workflow_id>/validate/",
        WorkflowValidateAPIView.as_view(),
        name="project-workflow-validate",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/workflows/<uuid:workflow_id>/publish/",
        WorkflowPublishAPIView.as_view(),
        name="project-workflow-publish",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/workflows/<uuid:workflow_id>/versions/",
        WorkflowVersionsAPIView.as_view(),
        name="project-workflow-versions",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/workflows/<uuid:workflow_id>/versions/<uuid:version_id>/rollback/",
        WorkflowRollbackAPIView.as_view(),
        name="project-workflow-rollback",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/workflow-transitions/",
        IssueWorkflowTransitionsAPIView.as_view(),
        name="work-item-workflow-transitions",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-item-types/<uuid:issue_type_id>/workflow-states/",
        WorkItemTypeWorkflowStatesAPIView.as_view(),
        name="work-item-type-workflow-states",
    ),
]
