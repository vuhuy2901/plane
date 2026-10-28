# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Stdio bridge to Plane MCP server for Antigravity IDE and external MCP clients."""

import os
import sys
import json
import httpx2
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver import MCPServer

MCP_URL = os.environ.get("PLANE_MCP_URL", "http://localhost:8000/mcp/")
API_TOKEN = os.environ.get("PLANE_API_TOKEN")

server = MCPServer("plane")


async def _call_plane_api_mcp(tool_name: str, args: dict) -> str:
    if not API_TOKEN:
        raise RuntimeError("PLANE_API_TOKEN is required; set it in the MCP client's environment.")
    timeout = httpx2.Timeout(30, read=300)
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        timeout=timeout,
    ) as http_client:
        transport = streamable_http_client(MCP_URL, http_client=http_client)
        async with Client(transport) as client:
            res = await client.call_tool(tool_name, args)
            if hasattr(res, "content") and res.content:
                for c in res.content:
                    text = getattr(c, "text", "")
                    if text:
                        return text
            return json.dumps(res, ensure_ascii=False)


@server.tool(name="plane_list_workspaces", description="List Plane workspaces accessible to the authenticated user.")
async def plane_list_workspaces() -> str:
    return await _call_plane_api_mcp("plane_list_workspaces", {})


@server.tool(name="plane_list_projects", description="List projects in a Plane workspace.")
async def plane_list_projects(workspace_slug: str = "qldapm") -> str:
    return await _call_plane_api_mcp("plane_list_projects", {"workspace_slug": workspace_slug})


@server.tool(name="plane_get_project", description="Get one Plane project by workspace slug and project UUID.")
async def plane_get_project(workspace_slug: str, project_id: str) -> str:
    return await _call_plane_api_mcp("plane_get_project", {"workspace_slug": workspace_slug, "project_id": project_id})


@server.tool(name="plane_create_project", description="Create a Plane project. Identifier should be a short unique key such as ENG, ECOM.")
async def plane_create_project(workspace_slug: str, name: str, identifier: str, description: str = "") -> str:
    args = {"workspace_slug": workspace_slug, "name": name, "identifier": identifier}
    if description:
        args["description"] = description
    return await _call_plane_api_mcp("plane_create_project", args)


@server.tool(name="plane_update_project", description="Partially update a Plane project using API v1 project fields in changes.")
async def plane_update_project(workspace_slug: str, project_id: str, changes: dict) -> str:
    return await _call_plane_api_mcp("plane_update_project", {"workspace_slug": workspace_slug, "project_id": project_id, "changes": changes})


@server.tool(name="plane_list_states", description="List workflow states in a Plane project so work items can be assigned by state name.")
async def plane_list_states(workspace_slug: str, project_id: str) -> str:
    return await _call_plane_api_mcp("plane_list_states", {"workspace_slug": workspace_slug, "project_id": project_id})


@server.tool(name="plane_list_labels", description="List labels in a Plane project so work items can be tagged by label name.")
async def plane_list_labels(workspace_slug: str, project_id: str) -> str:
    return await _call_plane_api_mcp("plane_list_labels", {"workspace_slug": workspace_slug, "project_id": project_id})


@server.tool(name="plane_create_label", description="Create a Plane project label. Color should be a hex value such as #22C55E.")
async def plane_create_label(workspace_slug: str, project_id: str, name: str, color: str = "#22C55E") -> str:
    return await _call_plane_api_mcp("plane_create_label", {"workspace_slug": workspace_slug, "project_id": project_id, "name": name, "color": color})


@server.tool(name="plane_list_project_members", description="List project members so work items can be assigned by a person's name or email.")
async def plane_list_project_members(workspace_slug: str, project_id: str) -> str:
    return await _call_plane_api_mcp("plane_list_project_members", {"workspace_slug": workspace_slug, "project_id": project_id})


@server.tool(name="plane_list_work_items", description="List work items/tasks in a Plane project with optional cursor pagination.")
async def plane_list_work_items(workspace_slug: str, project_id: str, cursor: str = "", state: str = "", priority: str = "") -> str:
    args = {"workspace_slug": workspace_slug, "project_id": project_id}
    if cursor:
        args["cursor"] = cursor
    if state:
        args["state"] = state
    if priority:
        args["priority"] = priority
    return await _call_plane_api_mcp("plane_list_work_items", args)


@server.tool(name="plane_get_work_item", description="Get one Plane work item by workspace slug, project UUID, and work item UUID.")
async def plane_get_work_item(workspace_slug: str, project_id: str, work_item_id: str) -> str:
    return await _call_plane_api_mcp("plane_get_work_item", {"workspace_slug": workspace_slug, "project_id": project_id, "work_item_id": work_item_id})


@server.tool(name="plane_create_work_item", description="Create a Plane work item with optional state, assignees, labels, hierarchy, and ISO dates.")
async def plane_create_work_item(workspace_slug: str, project_id: str, name: str, priority: str = "medium", description_html: str = "", state_name: str = "") -> str:
    args = {"workspace_slug": workspace_slug, "project_id": project_id, "name": name, "priority": priority}
    if description_html:
        args["description_html"] = description_html
    if state_name:
        args["state_name"] = state_name
    return await _call_plane_api_mcp("plane_create_work_item", args)


@server.tool(name="plane_import_work_items", description="Import up to 100 work items in one call; use ref and parent_ref to preserve CSV hierarchy.")
async def plane_import_work_items(workspace_slug: str, project_id: str, items: list) -> str:
    return await _call_plane_api_mcp("plane_import_work_items", {"workspace_slug": workspace_slug, "project_id": project_id, "items": items})


@server.tool(name="plane_update_work_item", description="Partially update a Plane work item using API v1 work-item fields in changes.")
async def plane_update_work_item(workspace_slug: str, project_id: str, work_item_id: str, changes: dict) -> str:
    return await _call_plane_api_mcp("plane_update_work_item", {"workspace_slug": workspace_slug, "project_id": project_id, "work_item_id": work_item_id, "changes": changes})


if __name__ == "__main__":
    server.run("stdio")
