# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from collections.abc import Awaitable, Callable
from typing import Any

from asgiref.sync import sync_to_async
from rest_framework.exceptions import AuthenticationFailed

from plane.api.middleware.api_authentication import APIKeyAuthentication


ASGIApp = Callable[
    [dict[str, Any], Callable[[], Awaitable[dict[str, Any]]], Callable[[dict[str, Any]], Awaitable[None]]],
    Awaitable[None],
]


def get_api_token(headers: dict[str, str]) -> str | None:
    """Read a Plane PAT from the standard bearer header or X-Api-Key."""
    api_key = headers.get("x-api-key")
    authorization = headers.get("authorization", "")
    bearer_token = None

    if authorization:
        scheme, separator, credentials = authorization.partition(" ")
        if separator and scheme.lower() == "bearer" and credentials.strip():
            bearer_token = credentials.strip()

    if api_key and bearer_token and api_key != bearer_token:
        return None
    return bearer_token or api_key


class MCPAPIKeyAuthenticationMiddleware:
    """Authenticate every MCP HTTP request with an existing Plane PAT."""

    def __init__(self, app: ASGIApp):
        self.app = app
        self.authentication = APIKeyAuthentication()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
        token = get_api_token(headers)
        if token is None:
            await self._reject(send, "Authentication credentials were not provided.")
            return

        try:
            await sync_to_async(self.authentication.validate_api_token, thread_sensitive=True)(token)
        except AuthenticationFailed:
            await self._reject(send, "Given API token is not valid.")
            return

        # Remove any caller-supplied X-Api-Key and append the token that was just
        # validated. Tools can safely forward this normalized header to API v1.
        scope = dict(scope)
        scope["headers"] = [(key, value) for key, value in scope.get("headers", []) if key.lower() != b"x-api-key"] + [
            (b"x-api-key", token.encode("latin-1"))
        ]
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send, detail: str) -> None:
        body = ('{"error":"' + detail + '"}').encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"www-authenticate", b'Bearer realm="plane-mcp"'),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
