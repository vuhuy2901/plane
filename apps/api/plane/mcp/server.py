# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json
from typing import Any
from urllib.parse import quote

import httpx
from django.conf import settings
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from .authentication import ASGIApp, MCPAPIKeyAuthenticationMiddleware, get_api_token


_plane_api_application: ASGIApp | None = None


def set_plane_api_application(application: ASGIApp) -> None:
    """Set the Django ASGI app used for permission-preserving internal API calls."""
    global _plane_api_application
    _plane_api_application = application


def _read_annotations() -> ToolAnnotations:
    return ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


def _write_annotations() -> ToolAnnotations:
    return ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)


mcp_server = MCPServer(
    name="Plane",
    title="Plane MCP Server",
    version="1.0.0",
    instructions=(
        "Use these tools to inspect and manage Plane workspaces, projects, and work items. "
        "All operations run with the permissions of the supplied Plane Personal Access Token. "
        "Prefer read tools before mutations and never invent workspace slugs or entity IDs."
    ),
)


def _token_from_context(ctx: Context) -> str:
    token = get_api_token(dict(ctx.headers or {}))
    if token is None:
        raise ToolError("A valid Plane Personal Access Token is required.")
    return token


async def _request_api(
    ctx: Context,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    if _plane_api_application is None:
        raise ToolError("The Plane API application is not available.")

    token = _token_from_context(ctx)
    transport = httpx.ASGITransport(app=_plane_api_application)
    async with httpx.AsyncClient(transport=transport, base_url="http://plane.internal") as client:
        response = await client.request(
            method,
            path,
            params={key: value for key, value in (params or {}).items() if value is not None},
            json=payload,
            headers={"X-Api-Key": token},
        )

    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:
            detail = {"error": response.text or "Plane API request failed"}
        raise ToolError(
            json.dumps(
                {"status": response.status_code, "detail": detail},
                default=str,
                separators=(",", ":"),
            )
        )

    if response.status_code == 204 or not response.content:
        return {"ok": True}
    return response.json()


def _segment(value: str) -> str:
    return quote(value, safe="")


@mcp_server.tool(annotations=_read_annotations())
async def plane_list_workspaces(ctx: Context, cursor: str | None = None, per_page: int = 50) -> dict[str, Any]:
    """List Plane workspaces accessible to the authenticated user."""
    return await _request_api(ctx, "GET", "/api/v1/workspaces/", params={"cursor": cursor, "per_page": per_page})


@mcp_server.tool(annotations=_read_annotations())
async def plane_list_projects(
    workspace_slug: str,
    ctx: Context,
    cursor: str | None = None,
    per_page: int = 50,
    include_archived: bool = False,
) -> dict[str, Any]:
    """List projects that the user can access in a Plane workspace."""
    return await _request_api(
        ctx,
        "GET",
        f"/api/v1/workspaces/{_segment(workspace_slug)}/projects-lite/",
        params={"cursor": cursor, "per_page": per_page, "include_archived": str(include_archived).lower()},
    )


@mcp_server.tool(annotations=_read_annotations())
async def plane_get_project(workspace_slug: str, project_id: str, ctx: Context) -> dict[str, Any]:
    """Get one Plane project by workspace slug and project UUID."""
    return await _request_api(
        ctx,
        "GET",
        f"/api/v1/workspaces/{_segment(workspace_slug)}/projects/{_segment(project_id)}/",
    )


@mcp_server.tool(annotations=_write_annotations())
async def plane_create_project(
    workspace_slug: str,
    name: str,
    identifier: str,
    ctx: Context,
    description: str = "",
) -> dict[str, Any]:
    """Create a Plane project. Identifier should be a short unique key such as ENG."""
    return await _request_api(
        ctx,
        "POST",
        f"/api/v1/workspaces/{_segment(workspace_slug)}/projects/",
        payload={"name": name, "identifier": identifier, "description": description},
    )


@mcp_server.tool(annotations=_write_annotations())
async def plane_update_project(
    workspace_slug: str,
    project_id: str,
    changes: dict[str, Any],
    ctx: Context,
) -> dict[str, Any]:
    """Partially update a Plane project using API v1 project fields in changes."""
    return await _request_api(
        ctx,
        "PATCH",
        f"/api/v1/workspaces/{_segment(workspace_slug)}/projects/{_segment(project_id)}/",
        payload=changes,
    )


@mcp_server.tool(annotations=_read_annotations())
async def plane_list_states(workspace_slug: str, project_id: str, ctx: Context) -> dict[str, Any]:
    """List workflow states in a Plane project so work items can be assigned by state name."""
    return await _request_api(
        ctx,
        "GET",
        f"/api/v1/workspaces/{_segment(workspace_slug)}/projects/{_segment(project_id)}/states/",
    )


@mcp_server.tool(annotations=_read_annotations())
async def plane_list_labels(workspace_slug: str, project_id: str, ctx: Context) -> dict[str, Any]:
    """List labels in a Plane project so work items can be tagged by label name."""
    return await _request_api(
        ctx,
        "GET",
        f"/api/v1/workspaces/{_segment(workspace_slug)}/projects/{_segment(project_id)}/labels/",
    )


@mcp_server.tool(annotations=_write_annotations())
async def plane_create_label(
    workspace_slug: str,
    project_id: str,
    name: str,
    color: str,
    ctx: Context,
    description: str = "",
) -> dict[str, Any]:
    """Create a Plane project label. Color should be a hex value such as #22C55E."""
    return await _request_api(
        ctx,
        "POST",
        f"/api/v1/workspaces/{_segment(workspace_slug)}/projects/{_segment(project_id)}/labels/",
        payload={"name": name, "color": color, "description": description},
    )


@mcp_server.tool(annotations=_read_annotations())
async def plane_list_project_members(workspace_slug: str, project_id: str, ctx: Context) -> dict[str, Any]:
    """List project members so work items can be assigned by a person's name or email."""
    return await _request_api(
        ctx,
        "GET",
        f"/api/v1/workspaces/{_segment(workspace_slug)}/projects/{_segment(project_id)}/project-members-lite/",
    )


@mcp_server.tool(annotations=_read_annotations())
async def plane_list_work_items(
    workspace_slug: str,
    project_id: str,
    ctx: Context,
    cursor: str | None = None,
    per_page: int = 50,
    order_by: str = "-created_at",
) -> dict[str, Any]:
    """List work items in a Plane project with cursor pagination."""
    return await _request_api(
        ctx,
        "GET",
        f"/api/v1/workspaces/{_segment(workspace_slug)}/projects/{_segment(project_id)}/work-items/",
        params={"cursor": cursor, "per_page": per_page, "order_by": order_by},
    )


@mcp_server.tool(annotations=_read_annotations())
async def plane_get_work_item(
    workspace_slug: str,
    project_id: str,
    work_item_id: str,
    ctx: Context,
) -> dict[str, Any]:
    """Get one Plane work item by workspace slug, project UUID, and work item UUID."""
    return await _request_api(
        ctx,
        "GET",
        (
            f"/api/v1/workspaces/{_segment(workspace_slug)}/projects/{_segment(project_id)}"
            f"/work-items/{_segment(work_item_id)}/"
        ),
    )


@mcp_server.tool(annotations=_write_annotations())
async def plane_create_work_item(
    workspace_slug: str,
    project_id: str,
    name: str,
    ctx: Context,
    description_html: str | None = None,
    priority: str = "none",
    state_id: str | None = None,
    assignee_ids: list[str] | None = None,
    label_ids: list[str] | None = None,
    parent_id: str | None = None,
    start_date: str | None = None,
    target_date: str | None = None,
) -> dict[str, Any]:
    """Create a Plane work item with optional state, assignees, labels, hierarchy, and ISO dates."""
    payload: dict[str, Any] = {"name": name, "priority": priority}
    optional_values = {
        "description_html": description_html,
        "state": state_id,
        "assignees": assignee_ids,
        "labels": label_ids,
        "parent": parent_id,
        "start_date": start_date,
        "target_date": target_date,
    }
    payload.update({key: value for key, value in optional_values.items() if value is not None})
    return await _request_api(
        ctx,
        "POST",
        f"/api/v1/workspaces/{_segment(workspace_slug)}/projects/{_segment(project_id)}/work-items/",
        payload=payload,
    )


@mcp_server.tool(annotations=_write_annotations())
async def plane_import_work_items(
    workspace_slug: str,
    project_id: str,
    items: list[dict[str, Any]],
    ctx: Context,
) -> dict[str, Any]:
    """Import up to 100 work items in one call; use ref and parent_ref to preserve CSV hierarchy."""
    if not items or len(items) > 100:
        raise ToolError("items must contain between 1 and 100 work items")

    allowed_fields = {
        "description_html",
        "priority",
        "state",
        "assignees",
        "labels",
        "parent",
        "start_date",
        "target_date",
    }
    references: dict[str, str] = {}
    results: list[dict[str, Any]] = []

    for index, item in enumerate(items):
        name = item.get("name")
        reference = str(item.get("ref", index + 1))
        if not isinstance(name, str) or not name.strip():
            results.append({"ref": reference, "ok": False, "error": "name is required"})
            continue

        payload = {key: value for key, value in item.items() if key in allowed_fields and value is not None}
        payload["name"] = name.strip()
        payload.setdefault("priority", "none")

        parent_reference = item.get("parent_ref")
        if parent_reference is not None:
            parent_id = references.get(str(parent_reference))
            if parent_id is None:
                results.append(
                    {
                        "ref": reference,
                        "ok": False,
                        "error": f"parent_ref {parent_reference} must refer to an earlier successful row",
                    }
                )
                continue
            payload["parent"] = parent_id

        try:
            created = await _request_api(
                ctx,
                "POST",
                f"/api/v1/workspaces/{_segment(workspace_slug)}/projects/{_segment(project_id)}/work-items/",
                payload=payload,
            )
            created_id = created.get("id") if isinstance(created, dict) else None
            if created_id:
                references[reference] = str(created_id)
            results.append(
                {
                    "ref": reference,
                    "ok": True,
                    "id": created_id,
                    "sequence_id": created.get("sequence_id") if isinstance(created, dict) else None,
                }
            )
        except ToolError as exc:
            results.append({"ref": reference, "ok": False, "error": str(exc)})

    created_count = sum(1 for result in results if result["ok"])
    return {
        "created_count": created_count,
        "failed_count": len(results) - created_count,
        "results": results,
    }


@mcp_server.tool(annotations=_write_annotations())
async def plane_update_work_item(
    workspace_slug: str,
    project_id: str,
    work_item_id: str,
    changes: dict[str, Any],
    ctx: Context,
) -> dict[str, Any]:
    """Partially update a Plane work item using API v1 work-item fields in changes."""
    return await _request_api(
        ctx,
        "PATCH",
        (
            f"/api/v1/workspaces/{_segment(workspace_slug)}/projects/{_segment(project_id)}"
            f"/work-items/{_segment(work_item_id)}/"
        ),
        payload=changes,
    )


def _configured_values(name: str) -> list[str]:
    value = getattr(settings, name, "")
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def create_mcp_http_app() -> ASGIApp:
    """Build the authenticated, stateless MCP Streamable HTTP application."""
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_configured_values("MCP_ALLOWED_HOSTS"),
        allowed_origins=_configured_values("MCP_ALLOWED_ORIGINS"),
    )
    app = mcp_server.streamable_http_app(
        streamable_http_path="/mcp/",
        json_response=True,
        stateless_http=True,
        transport_security=transport_security,
    )
    return MCPAPIKeyAuthenticationMiddleware(app)
