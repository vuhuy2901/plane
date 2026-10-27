# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from collections.abc import Awaitable, Callable
import json
import re
import secrets
from typing import Any

from asgiref.sync import sync_to_async
from rest_framework.exceptions import AuthenticationFailed

from plane.api.middleware.api_authentication import APIKeyAuthentication
from plane.db.models import MCPConnection

from .activity import record_event
from .connections import resolve_connection


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


class MCPConnectionAuthenticationMiddleware:
    """Resolve an opaque portal URL and inject its independently stored PAT."""

    _path_pattern = re.compile(r"^/mcp/c/([^/]+)/?$")

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        match = self._path_pattern.fullmatch(scope.get("path", ""))
        if match is None:
            await self._not_found(send)
            return

        resolved = await sync_to_async(resolve_connection, thread_sensitive=True)(match.group(1))
        if resolved is None:
            await self._not_found(send)
            return

        body = await self._read_body(receive)
        event_type, summary, rpc_request_id = self._describe_request(body)
        activity_request_id = secrets.token_hex(8)
        if event_type:
            await sync_to_async(record_event, thread_sensitive=True)(
                resolved.connection.id,
                event_type,
                summary,
                request_id=str(rpc_request_id or activity_request_id),
            )

        request_sent = False

        async def replay_receive():
            nonlocal request_sent
            if request_sent:
                return {"type": "http.disconnect"}
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        status_code = 500

        async def tracked_send(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        rewritten_scope = dict(scope)
        rewritten_scope["path"] = "/mcp/"
        rewritten_scope["raw_path"] = b"/mcp/"
        headers = [
            (key, value)
            for key, value in scope.get("headers", [])
            if key.lower() not in {b"authorization", b"x-api-key", b"x-plane-mcp-connection-id"}
        ]
        headers.extend(
            [
                (b"x-api-key", resolved.api_key.encode("latin-1")),
                (b"x-plane-mcp-connection-id", str(resolved.connection.id).encode("ascii")),
                (b"x-plane-mcp-request-id", activity_request_id.encode("ascii")),
            ]
        )
        rewritten_scope["headers"] = headers

        await self.app(rewritten_scope, replay_receive, tracked_send)

        if status_code < 400:
            from django.utils import timezone

            await sync_to_async(MCPConnection.objects.filter(id=resolved.connection.id).update, thread_sensitive=True)(
                last_mcp_request_at=timezone.now()
            )
        if event_type == "tool_call":
            await sync_to_async(record_event, thread_sensitive=True)(
                resolved.connection.id,
                "tool_result",
                "MCP returned the tool result to the client.",
                request_id=str(rpc_request_id or activity_request_id),
                succeeded=status_code < 400,
            )

    @staticmethod
    async def _read_body(receive) -> bytes:
        chunks = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        return b"".join(chunks)

    @staticmethod
    def _describe_request(body: bytes) -> tuple[str | None, str, Any]:
        try:
            payload = json.loads(body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, "", ""
        method = payload.get("method") if isinstance(payload, dict) else None
        request_id = payload.get("id", "") if isinstance(payload, dict) else ""
        if method == "initialize":
            return "initialize", "The MCP client initialized a Plane session.", request_id
        if method == "tools/list":
            return "tools_discovery", "The MCP client requested the registered Plane tools.", request_id
        if method == "tools/call":
            params = payload.get("params") or {}
            tool_name = params.get("name", "unknown tool") if isinstance(params, dict) else "unknown tool"
            return "tool_call", f"The MCP client called {tool_name}.", request_id
        return None, "", request_id

    @staticmethod
    async def _not_found(send):
        body = b'{"error":"MCP connection was not found, expired, or revoked."}'
        await send(
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})
