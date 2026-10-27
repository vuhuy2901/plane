# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from starlette.testclient import TestClient

from scripts.mcp_console import app


def test_console_home_renders_tool_interface():
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "Plane MCP Console" in response.text
    assert "Chạy tool" in response.text


def test_console_rejects_non_object_arguments():
    response = TestClient(app).post(
        "/api/call",
        json={"name": "plane_list_workspaces", "arguments": []},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "Arguments must be a JSON object"}
