"""Regression tests for MCP routing, delete safeguards and partial batch execution."""

import asyncio
import inspect
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
from django.urls import resolve
from mcp.server.mcpserver.exceptions import ToolError

from plane.mcp import server


def test_api_array_response_has_valid_mcp_object_shape(monkeypatch):
    async def application(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b'[{"id":"member"}]'})

    monkeypatch.setattr(server, "_plane_api_application", application)
    result = asyncio.run(
        server._request_api(SimpleNamespace(headers={"x-api-key": "token"}), "GET", "/api/v1/workspaces/")
    )
    assert result == {"results": [{"id": "member"}]}


def test_api_failure_is_not_reported_as_success(monkeypatch):
    async def application(scope, receive, send):
        await send({"type": "http.response.start", "status": 403, "headers": []})
        await send({"type": "http.response.body", "body": b'{"error":"forbidden"}'})

    monkeypatch.setattr(server, "_plane_api_application", application)
    with pytest.raises(ToolError, match="403"):
        asyncio.run(server._request_api(SimpleNamespace(headers={"x-api-key": "token"}), "DELETE", "/api/v1/denied/"))


NEW_TOOLS = [
    "plane_list_cycles",
    "plane_get_cycle",
    "plane_create_cycle",
    "plane_update_cycle",
    "plane_delete_cycle",
    "plane_list_cycle_work_items",
    "plane_add_cycle_work_items",
    "plane_remove_cycle_work_item",
    "plane_list_modules",
    "plane_get_module",
    "plane_create_module",
    "plane_update_module",
    "plane_delete_module",
    "plane_list_module_work_items",
    "plane_add_module_work_items",
    "plane_remove_module_work_item",
    "plane_create_state",
    "plane_update_state",
    "plane_delete_state",
    "plane_update_label",
    "plane_delete_label",
    "plane_list_work_item_comments",
    "plane_create_work_item_comment",
    "plane_update_work_item_comment",
    "plane_delete_work_item_comment",
    "plane_list_work_item_links",
    "plane_create_work_item_link",
    "plane_update_work_item_link",
    "plane_delete_work_item_link",
    "plane_list_work_item_activities",
    "plane_list_work_item_relations",
    "plane_list_work_item_attachments",
    "plane_get_work_item_workflow",
    "plane_list_workflows",
    "plane_list_work_item_types",
    "plane_get_work_item_hierarchy",
    "plane_list_workspace_members",
    "plane_get_work_item_by_identifier",
    "plane_search_work_items",
    "plane_delete_work_item",
    "plane_bulk_update_work_items",
    "plane_bulk_delete_work_items",
    "plane_create_work_item_relation",
    "plane_get_analytics_report",
    "plane_get_project_estimate",
    "plane_list_estimate_points",
]


@pytest.mark.parametrize("name", NEW_TOOLS)
def test_expanded_tools_use_existing_api_routes(monkeypatch, name):
    request_api = AsyncMock(return_value={"id": "item", "name": "Test"})
    monkeypatch.setattr(server, "_request_api", request_api)
    tool = getattr(server, name)
    args = {}
    for key, parameter in inspect.signature(tool).parameters.items():
        if parameter.default is not inspect.Parameter.empty:
            continue
        if key == "ctx":
            args[key] = object()
        elif key == "workspace_slug":
            args[key] = "engineering"
        elif key == "identifier":
            args[key] = "QLDP-215"
        elif key.endswith("_ids"):
            args[key] = ["12345678-1234-1234-1234-123456789abc"]
        elif key.endswith("_id"):
            args[key] = "12345678-1234-1234-1234-123456789abc"
        elif key == "changes":
            args[key] = {"priority": "high"}
        elif key == "group":
            args[key] = "started"
        else:
            args[key] = "Test"
    asyncio.run(tool(**args))
    assert request_api.await_count > 0
    for call in request_api.await_args_list:
        _, method, path = call.args
        match = resolve(path)
        assert method.lower() in match.func.view_class.http_method_names, (name, method, path)


def test_delete_name_mismatch_never_sends_delete(monkeypatch):
    request_api = AsyncMock(return_value={"name": "Different item"})
    monkeypatch.setattr(server, "_request_api", request_api)
    with pytest.raises(ToolError, match="expected_name"):
        asyncio.run(server.plane_delete_work_item("eng", "project", "item", object(), expected_name="Wanted"))
    assert [call.args[1] for call in request_api.await_args_list] == ["GET"]


def test_bulk_delete_defaults_to_preview(monkeypatch):
    request_api = AsyncMock(return_value={"name": "Keep me"})
    monkeypatch.setattr(server, "_request_api", request_api)
    result = asyncio.run(server.plane_bulk_delete_work_items("eng", "project", ["item"], object()))
    assert result["dry_run"] is True
    assert result["results"][0]["applied"] is False
    assert [call.args[1] for call in request_api.await_args_list] == ["GET"]


def test_bulk_update_reports_partial_failures_and_continues(monkeypatch):
    request_api = AsyncMock(
        side_effect=[{"name": "First"}, ToolError("forbidden"), {"name": "Second"}, {"id": "second"}]
    )
    monkeypatch.setattr(server, "_request_api", request_api)
    result = asyncio.run(
        server.plane_bulk_update_work_items(
            "eng", "project", ["first", "second"], {"priority": "high"}, object(), dry_run=False
        )
    )
    assert result["succeeded"] == 1
    assert result["failed"] == 1
    assert result["results"][0]["applied"] is False
    assert result["results"][1]["applied"] is True


@pytest.mark.parametrize("ids", [[], ["same", "same"], [str(i) for i in range(51)]])
def test_bulk_rejects_invalid_batches_without_requests(monkeypatch, ids):
    request_api = AsyncMock()
    monkeypatch.setattr(server, "_request_api", request_api)
    with pytest.raises(ToolError):
        asyncio.run(server.plane_bulk_delete_work_items("eng", "project", ids, object(), dry_run=False))
    request_api.assert_not_awaited()


def test_exact_identifier_and_analytics_filter_mapping(monkeypatch):
    request_api = AsyncMock(return_value={})
    monkeypatch.setattr(server, "_request_api", request_api)
    asyncio.run(server.plane_get_work_item_by_identifier("eng", "QLDP-215", object()))
    assert request_api.await_args.args[2] == "/api/v1/workspaces/eng/work-items/QLDP-215/"
    asyncio.run(
        server.plane_get_analytics_report(
            "eng",
            object(),
            project_ids=["p1", "p2"],
            assignee_ids=["member"],
            date_from="2026-10-01",
            date_to="2026-10-29",
        )
    )
    assert request_api.await_args.kwargs["params"]["project_ids"] == "p1,p2"
    assert request_api.await_args.kwargs["params"]["assignee_ids"] == "member"
