# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import asyncio
from unittest.mock import Mock

from rest_framework.exceptions import AuthenticationFailed

from plane.mcp.authentication import MCPAPIKeyAuthenticationMiddleware, get_api_token


def test_get_api_token_accepts_bearer_and_api_key():
    assert get_api_token({"authorization": "Bearer token-1"}) == "token-1"
    assert get_api_token({"x-api-key": "token-2"}) == "token-2"
    assert get_api_token({"authorization": "bearer token-3", "x-api-key": "token-3"}) == "token-3"


def test_get_api_token_rejects_conflicting_credentials():
    assert get_api_token({"authorization": "Bearer first", "x-api-key": "second"}) is None


def test_middleware_validates_and_normalizes_token():
    captured_scope = None

    async def app(scope, receive, send):
        nonlocal captured_scope
        captured_scope = scope

    middleware = MCPAPIKeyAuthenticationMiddleware(app)
    middleware.authentication.validate_api_token = Mock(return_value=(object(), "secret"))
    scope = {
        "type": "http",
        "headers": [(b"authorization", b"Bearer secret"), (b"x-api-key", b"secret")],
    }

    asyncio.run(middleware(scope, _receive, _send))

    assert captured_scope is not None
    assert captured_scope["headers"].count((b"x-api-key", b"secret")) == 1
    middleware.authentication.validate_api_token.assert_called_once_with("secret")


def test_middleware_returns_401_for_invalid_token():
    messages = []

    async def app(scope, receive, send):  # pragma: no cover - must not be called
        raise AssertionError("downstream app should not run")

    async def send(message):
        messages.append(message)

    middleware = MCPAPIKeyAuthenticationMiddleware(app)
    middleware.authentication.validate_api_token = Mock(side_effect=AuthenticationFailed("invalid"))
    scope = {"type": "http", "headers": [(b"authorization", b"Bearer invalid")]}

    asyncio.run(middleware(scope, _receive, send))

    assert messages[0]["status"] == 401
    assert (b"www-authenticate", b'Bearer realm="plane-mcp"') in messages[0]["headers"]


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


async def _send(message):
    return None
