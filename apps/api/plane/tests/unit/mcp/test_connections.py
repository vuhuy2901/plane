# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from django.test import override_settings
from django.utils import timezone

from plane.db.models import MCPConnection, Project
from plane.mcp import server
from plane.app.views.mcp_connect import _PortalToolContext
from plane.mcp.connections import create_connection, decrypt_api_key, resolve_connection, token_digest


@pytest.mark.django_db
@override_settings(WEB_URL="http://testserver")
def test_connection_api_validates_creates_refreshes_and_revokes(api_client, api_token, workspace):
    payload = {
        "plane_server_url": "http://testserver/",
        "workspace_slug": workspace.slug,
        "api_key": api_token.token,
    }
    test_response = api_client.post("/api/mcp-connect/test/", payload, format="json")
    assert test_response.status_code == 200
    assert test_response.json()["workspace"]["slug"] == workspace.slug

    create_response = api_client.post("/api/mcp-connect/connections/", payload, format="json")
    assert create_response.status_code == 201
    raw_token = create_response.json()["mcp_url"].rsplit("/", 1)[-1]
    connection = MCPConnection.objects.get()
    assert connection.token_hash == token_digest(raw_token)
    assert raw_token not in connection.encrypted_api_key
    assert decrypt_api_key(connection.encrypted_api_key) == api_token.token

    status_response = api_client.get("/api/mcp-connect/status/")
    assert status_response.status_code == 200
    assert status_response.json()["connected"] is True
    assert status_response.json()["mcp_url"].endswith(raw_token)

    revoke_response = api_client.post("/api/mcp-connect/revoke/", {}, format="json")
    assert revoke_response.status_code == 200
    connection.refresh_from_db()
    assert connection.revoked_at is not None
    assert resolve_connection(raw_token) is None


@pytest.mark.django_db
@override_settings(WEB_URL="http://testserver")
def test_connection_api_rejects_invalid_key_and_workspace(api_client, api_token, workspace):
    invalid_key = api_client.post(
        "/api/mcp-connect/test/",
        {"plane_server_url": "http://testserver", "workspace_slug": workspace.slug, "api_key": "invalid"},
        format="json",
    )
    assert invalid_key.status_code == 401
    assert invalid_key.json()["code"] == "invalid_api_key"

    invalid_workspace = api_client.post(
        "/api/mcp-connect/test/",
        {"plane_server_url": "http://testserver", "workspace_slug": "missing", "api_key": api_token.token},
        format="json",
    )
    assert invalid_workspace.status_code == 404
    assert invalid_workspace.json()["code"] == "invalid_workspace"


@pytest.mark.django_db
@override_settings(WEB_URL="http://testserver")
def test_connected_workspace_projects_are_listed_for_demo_picker(api_client, api_token, workspace):
    project = Project.objects.create(name="Demo Project", identifier="DEMO", workspace=workspace)
    payload = {
        "plane_server_url": "http://testserver",
        "workspace_slug": workspace.slug,
        "api_key": api_token.token,
    }
    create_response = api_client.post("/api/mcp-connect/connections/", payload, format="json")
    assert create_response.status_code == 201

    projects_response = api_client.get("/api/mcp-connect/projects/")
    assert projects_response.status_code == 200
    assert projects_response.json()["projects"] == [
        {"id": str(project.id), "name": "Demo Project", "identifier": "DEMO"}
    ]


@pytest.mark.django_db
def test_connections_keep_credentials_isolated_and_expire(api_token, workspace, create_user):
    first, first_token = create_connection(
        api_key=api_token.token,
        plane_server_url="http://testserver",
        workspace=workspace,
        user=create_user,
    )
    second, second_token = create_connection(
        api_key="plane_api_second",
        plane_server_url="http://testserver",
        workspace=workspace,
        user=create_user,
    )
    assert first.token_hash != second.token_hash
    assert resolve_connection(first_token).api_key == api_token.token
    assert resolve_connection(second_token).api_key == "plane_api_second"

    first.expires_at = timezone.now() - timedelta(seconds=1)
    first.save(update_fields=["expires_at", "updated_at"])
    assert resolve_connection(first_token) is None
    assert resolve_connection(second_token).connection.id == second.id


@pytest.mark.django_db(transaction=True)
def test_personal_streamable_http_initializes_with_resolved_connection(api_token, workspace, create_user):
    connection, raw_token = create_connection(
        api_key=api_token.token,
        plane_server_url="http://plane.internal",
        workspace=workspace,
        user=create_user,
    )

    async def initialize():
        app = server.create_personal_mcp_http_app()
        app.app.authentication.validate_api_token = Mock(return_value=(create_user, api_token.token))
        transport = httpx.ASGITransport(app=app)
        async with server.mcp_server.session_manager.run():
            async with httpx.AsyncClient(transport=transport, base_url="http://plane.internal") as client:
                return await client.post(
                    f"/mcp/c/{raw_token}",
                    headers={"Accept": "application/json, text/event-stream"},
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "portal-test", "version": "1"},
                        },
                    },
                )

    response = asyncio.run(initialize())
    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "Plane"
    connection.refresh_from_db()
    assert connection.last_mcp_request_at is not None


def test_portal_context_executes_the_registered_tool(monkeypatch):
    request_api = AsyncMock(return_value={"results": []})
    monkeypatch.setattr(server, "_request_api", request_api)
    context = _PortalToolContext(headers={"x-api-key": "connection-specific-key"})

    result = asyncio.run(
        server.mcp_server.call_tool(
            "plane_list_projects",
            {"workspace_slug": "engineering"},
            context=context,
        )
    )

    assert result.is_error is False
    request_api.assert_awaited_once()
