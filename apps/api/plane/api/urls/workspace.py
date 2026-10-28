# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.api.views import WorkspaceListAPIEndpoint
from plane.api.views.analytic import WorkspaceAnalyticsAPIEndpoint


urlpatterns = [
    path(
        "workspaces/<str:slug>/analytics-report/",
        WorkspaceAnalyticsAPIEndpoint.as_view(http_method_names=["get"]),
        name="workspace-analytics-report",
    ),
    path(
        "workspaces/",
        WorkspaceListAPIEndpoint.as_view(http_method_names=["get"]),
        name="workspace-list",
    ),
]
