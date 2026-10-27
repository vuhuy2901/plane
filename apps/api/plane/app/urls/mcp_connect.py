# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.app.views.mcp_connect import (
    MCPConnectionActivityEndpoint,
    MCPConnectionEndpoint,
    MCPConnectionRegenerateEndpoint,
    MCPConnectionRevokeEndpoint,
    MCPConnectionStatusEndpoint,
    MCPConnectionTestEndpoint,
    MCPProjectsEndpoint,
    MCPToolsEndpoint,
    MCPToolTestEndpoint,
)


urlpatterns = [
    path("mcp-connect/test/", MCPConnectionTestEndpoint.as_view(), name="mcp-connection-test"),
    path("mcp-connect/connections/", MCPConnectionEndpoint.as_view(), name="mcp-connection-create"),
    path("mcp-connect/status/", MCPConnectionStatusEndpoint.as_view(), name="mcp-connection-status"),
    path("mcp-connect/revoke/", MCPConnectionRevokeEndpoint.as_view(), name="mcp-connection-revoke"),
    path("mcp-connect/regenerate/", MCPConnectionRegenerateEndpoint.as_view(), name="mcp-connection-regenerate"),
    path("mcp-connect/tools/", MCPToolsEndpoint.as_view(), name="mcp-tools"),
    path("mcp-connect/projects/", MCPProjectsEndpoint.as_view(), name="mcp-projects"),
    path("mcp-connect/tools/test/", MCPToolTestEndpoint.as_view(), name="mcp-tool-test"),
    path("mcp-connect/activity/", MCPConnectionActivityEndpoint.as_view(), name="mcp-connection-activity"),
]
