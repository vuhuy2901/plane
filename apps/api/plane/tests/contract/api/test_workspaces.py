# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from plane.db.models import Workspace


def test_list_workspaces_returns_only_active_memberships(api_key_client, workspace, create_user):
    Workspace.objects.create(name="Private", slug="private", owner=create_user)

    response = api_key_client.get("/api/v1/workspaces/")

    assert response.status_code == 200
    assert [item["slug"] for item in response.data["results"]] == [workspace.slug]


def test_list_workspaces_requires_api_key(api_client):
    response = api_client.get("/api/v1/workspaces/")

    assert response.status_code in (401, 403)
