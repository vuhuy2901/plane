# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import asyncio
from unittest.mock import AsyncMock, Mock

import httpx

from plane.mcp import server


def test_server_registers_plane_tools_with_structured_schemas():
    tools = asyncio.run(server.mcp_server.list_tools())
    tools_by_name = {tool.name: tool for tool in tools}

    assert set(tools_by_name) >= {
        "plane_create_project",
        "plane_create_label",
        "plane_create_work_item",
        "plane_get_project",
        "plane_get_work_item",
        "plane_import_work_items",
        "plane_list_labels",
        "plane_list_project_members",
        "plane_list_projects",
        "plane_list_states",
        "plane_list_work_items",
        "plane_list_workspaces",
        "plane_update_project",
        "plane_update_work_item",
    }
    assert tools_by_name["plane_list_workspaces"].annotations.read_only_hint is True
    assert tools_by_name["plane_create_work_item"].annotations.read_only_hint is False
    assert "ctx" not in tools_by_name["plane_create_work_item"].input_schema["properties"]
    assert len(tools_by_name) >= 60
    assert tools_by_name["plane_delete_work_item"].annotations.destructive_hint is True
    assert tools_by_name["plane_get_analytics_report"].annotations.read_only_hint is True
    assert tools_by_name["plane_bulk_delete_work_items"].input_schema["properties"]["dry_run"]["default"] is True


def test_create_work_item_maps_arguments_to_api_payload(monkeypatch):
    request_api = AsyncMock(return_value={"id": "work-item-id"})
    monkeypatch.setattr(server, "_request_api", request_api)
    context = object()

    result = asyncio.run(
        server.plane_create_work_item(
            "engineering",
            "project-id",
            "Fix MCP transport",
            context,
            priority="high",
            state_id="state-id",
            assignee_ids=["user-id"],
            parent_id="parent-id",
            start_date="2026-10-22",
            target_date="2026-10-31",
        )
    )

    assert result == {"id": "work-item-id"}
    request_api.assert_awaited_once_with(
        context,
        "POST",
        "/api/v1/workspaces/engineering/projects/project-id/work-items/",
        payload={
            "name": "Fix MCP transport",
            "priority": "high",
            "state": "state-id",
            "assignees": ["user-id"],
            "parent": "parent-id",
            "start_date": "2026-10-22",
            "target_date": "2026-10-31",
        },
    )


def test_import_work_items_resolves_parent_reference(monkeypatch):
    request_api = AsyncMock(
        side_effect=[
            {"id": "parent-id", "sequence_id": 1},
            {"id": "child-id", "sequence_id": 2},
        ]
    )
    monkeypatch.setattr(server, "_request_api", request_api)
    context = object()

    result = asyncio.run(
        server.plane_import_work_items(
            "engineering",
            "project-id",
            [
                {"ref": "EPIC-1", "name": "Checkout epic", "priority": "high"},
                {"ref": "TASK-1", "parent_ref": "EPIC-1", "name": "Payment form"},
            ],
            context,
        )
    )

    assert result["created_count"] == 2
    assert result["failed_count"] == 0
    assert request_api.await_args_list[1].kwargs["payload"]["parent"] == "parent-id"


def test_streamable_http_initialize_succeeds_with_api_key():
    async def initialize():
        app = server.create_mcp_http_app()
        manager = server.mcp_server.session_manager
        personal_app = server.create_personal_mcp_http_app(app)
        assert personal_app.app is app
        assert server.mcp_server.session_manager is manager
        app.authentication.validate_api_token = Mock(return_value=(object(), "token"))
        transport = httpx.ASGITransport(app=app)

        async with server.mcp_server.session_manager.run():
            async with httpx.AsyncClient(transport=transport, base_url="http://plane.internal") as client:
                return await client.post(
                    "/mcp/",
                    headers={
                        "Authorization": "Bearer token",
                        "Accept": "application/json, text/event-stream",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1"},
                        },
                    },
                )

    response = asyncio.run(initialize())

    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "Plane"
