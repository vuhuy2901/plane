# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import secrets
from dataclasses import dataclass

from asgiref.sync import async_to_sync
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from plane.api.middleware.api_authentication import APIKeyAuthentication
from plane.db.models import APIToken, MCPConnection, Project, Workspace, WorkspaceMember
from plane.mcp.activity import EVENT_LABELS, record_event
from plane.mcp.connections import (
    CONNECTION_COOKIE_NAME,
    create_connection,
    normalize_server_url,
    resolve_connection,
)
from plane.mcp.server import mcp_server


def _user_name(user) -> str:
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full_name or user.email


def _public_base_url(request) -> str:
    configured = getattr(settings, "WEB_URL", "") or getattr(settings, "APP_BASE_URL", "")
    return normalize_server_url(configured or request.build_absolute_uri("/"))


def _validate_local_server(request, value: str) -> str:
    normalized = normalize_server_url(value)
    candidates = {_public_base_url(request), normalize_server_url(request.build_absolute_uri("/"))}
    for setting_name in ("WEB_URL", "APP_BASE_URL", "API_BASE_URL"):
        candidate = getattr(settings, setting_name, "")
        if candidate:
            try:
                candidates.add(normalize_server_url(candidate))
            except ValueError:
                continue
    if normalized not in candidates:
        raise ValueError("This demo portal can connect only to the Plane instance hosting it.")
    return normalized


def _validate_credentials(request):
    server_url = str(request.data.get("plane_server_url", "")).strip()
    workspace_slug = str(request.data.get("workspace_slug", "")).strip()
    api_key = str(request.data.get("api_key", "")).strip()
    missing = [
        label
        for label, value in (
            ("Plane server URL", server_url),
            ("Workspace slug", workspace_slug),
            ("Personal API key", api_key),
        )
        if not value
    ]
    if missing:
        return None, Response({"error": f"Required: {', '.join(missing)}."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        server_url = _validate_local_server(request, server_url)
    except ValueError as exc:
        return None, Response({"error": str(exc), "code": "invalid_server"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user, _ = APIKeyAuthentication().validate_api_token(api_key)
    except AuthenticationFailed:
        return None, Response(
            {"error": "The Personal API Key is invalid or expired.", "code": "invalid_api_key"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    workspace = Workspace.objects.filter(slug=workspace_slug).first()
    if workspace is None:
        return None, Response(
            {"error": "No Plane workspace was found with that slug.", "code": "invalid_workspace"},
            status=status.HTTP_404_NOT_FOUND,
        )
    is_member = (
        workspace.owner_id == user.id
        or WorkspaceMember.objects.filter(workspace=workspace, member=user, is_active=True).exists()
    )
    token_record = APIToken.objects.filter(token=api_key).only("workspace_id").first()
    if not is_member or (token_record and token_record.workspace_id and token_record.workspace_id != workspace.id):
        return None, Response(
            {"error": "This API Key does not have access to that workspace.", "code": "invalid_workspace"},
            status=status.HTTP_403_FORBIDDEN,
        )

    return {"server_url": server_url, "workspace": workspace, "user": user, "api_key": api_key}, None


def _raw_cookie_token(request) -> str:
    return request.COOKIES.get(CONNECTION_COOKIE_NAME, "")


def _connection_payload(request, connection: MCPConnection, raw_token: str) -> dict:
    return {
        "connected": connection.is_available,
        "status": "connected" if connection.is_available else "disconnected",
        "user": {"name": _user_name(connection.user), "email": connection.user.email},
        "workspace": {"name": connection.workspace.name, "slug": connection.workspace.slug},
        "plane_server_url": connection.plane_server_url,
        "mcp_server_status": "available" if connection.is_available else "unavailable",
        "mcp_url": request.build_absolute_uri(f"/mcp/c/{raw_token}"),
        "expires_at": connection.expires_at.isoformat(),
        "last_mcp_request_at": connection.last_mcp_request_at.isoformat() if connection.last_mcp_request_at else None,
    }


def _set_connection_cookie(response: Response, request, raw_token: str, expires_at) -> None:
    response.set_cookie(
        CONNECTION_COOKIE_NAME,
        raw_token,
        expires=expires_at,
        httponly=True,
        secure=request.is_secure(),
        samesite="Strict",
        path="/",
    )


class PublicMCPAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []


class MCPConnectionTestEndpoint(PublicMCPAPIView):
    def post(self, request):
        validated, error = _validate_credentials(request)
        if error:
            return error
        return Response(
            {
                "ok": True,
                "user": {"name": _user_name(validated["user"]), "email": validated["user"].email},
                "workspace": {"name": validated["workspace"].name, "slug": validated["workspace"].slug},
            }
        )


class MCPConnectionEndpoint(PublicMCPAPIView):
    def post(self, request):
        validated, error = _validate_credentials(request)
        if error:
            return error
        connection, raw_token = create_connection(
            api_key=validated["api_key"],
            plane_server_url=validated["server_url"],
            workspace=validated["workspace"],
            user=validated["user"],
        )
        response = Response(_connection_payload(request, connection, raw_token), status=status.HTTP_201_CREATED)
        _set_connection_cookie(response, request, raw_token, connection.expires_at)
        return response


class MCPConnectionStatusEndpoint(PublicMCPAPIView):
    def get(self, request):
        raw_token = _raw_cookie_token(request)
        resolved = resolve_connection(raw_token)
        if resolved is None:
            return Response(
                {"connected": False, "status": "disconnected", "plane_server_url": _public_base_url(request)}
            )
        return Response(_connection_payload(request, resolved.connection, raw_token))


class MCPConnectionRevokeEndpoint(PublicMCPAPIView):
    def post(self, request):
        raw_token = _raw_cookie_token(request)
        resolved = resolve_connection(raw_token)
        if resolved is not None:
            resolved.connection.revoked_at = timezone.now()
            resolved.connection.save(update_fields=["revoked_at", "updated_at"])
        response = Response({"connected": False, "status": "disconnected"})
        response.delete_cookie(CONNECTION_COOKIE_NAME, path="/", samesite="Strict")
        return response


class MCPConnectionRegenerateEndpoint(PublicMCPAPIView):
    def post(self, request):
        raw_token = _raw_cookie_token(request)
        resolved = resolve_connection(raw_token)
        if resolved is None:
            return Response({"error": "The active connection was not found."}, status=status.HTTP_404_NOT_FOUND)
        old_connection = resolved.connection
        old_connection.revoked_at = timezone.now()
        old_connection.save(update_fields=["revoked_at", "updated_at"])
        connection, new_token = create_connection(
            api_key=resolved.api_key,
            plane_server_url=old_connection.plane_server_url,
            workspace=old_connection.workspace,
            user=old_connection.user,
        )
        response = Response(_connection_payload(request, connection, new_token))
        _set_connection_cookie(response, request, new_token, connection.expires_at)
        return response


def _tool_payload(tool) -> dict:
    annotations = tool.annotations.model_dump(mode="json", by_alias=True) if tool.annotations else {}
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.input_schema,
        "classification": "read" if tool.annotations and tool.annotations.read_only_hint else "write",
        "available": True,
        "annotations": annotations,
    }


class MCPToolsEndpoint(PublicMCPAPIView):
    def get(self, request):
        resolved = resolve_connection(_raw_cookie_token(request))
        if resolved is None:
            return Response({"error": "Connect Plane before discovering tools."}, status=status.HTTP_401_UNAUTHORIZED)
        tools = async_to_sync(mcp_server.list_tools)()
        return Response({"count": len(tools), "tools": [_tool_payload(tool) for tool in tools]})


class MCPProjectsEndpoint(PublicMCPAPIView):
    def get(self, request):
        resolved = resolve_connection(_raw_cookie_token(request))
        if resolved is None:
            return Response({"error": "Connect Plane before listing projects."}, status=status.HTTP_401_UNAUTHORIZED)
        projects = (
            Project.objects.filter(
                workspace=resolved.connection.workspace,
                deleted_at__isnull=True,
                archived_at__isnull=True,
            )
            .filter(
                Q(network=2)
                | Q(
                    project_projectmember__member=resolved.connection.user,
                    project_projectmember__is_active=True,
                )
            )
            .distinct()
            .order_by("name")
            .values("id", "name", "identifier")
        )
        return Response({"projects": list(projects)})


@dataclass(frozen=True)
class _PortalToolContext:
    headers: dict[str, str]


class MCPToolTestEndpoint(PublicMCPAPIView):
    def post(self, request):
        resolved = resolve_connection(_raw_cookie_token(request))
        if resolved is None:
            return Response({"error": "Connect Plane before executing a tool."}, status=status.HTTP_401_UNAUTHORIZED)
        tool_name = str(request.data.get("tool_name", ""))
        arguments = request.data.get("arguments", {})
        if not tool_name or not isinstance(arguments, dict):
            return Response(
                {"error": "tool_name and an arguments object are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tools = {tool.name: tool for tool in async_to_sync(mcp_server.list_tools)()}
        tool = tools.get(tool_name)
        if tool is None:
            return Response({"error": "That MCP tool is not registered."}, status=status.HTTP_404_NOT_FOUND)
        is_write = not bool(tool.annotations and tool.annotations.read_only_hint)
        if is_write and request.data.get("confirm_write") is not True:
            return Response(
                {"error": "Confirm the write operation before executing this tool.", "code": "confirmation_required"},
                status=status.HTTP_409_CONFLICT,
            )

        properties = tool.input_schema.get("properties", {})
        if "workspace_slug" in properties:
            supplied_slug = arguments.get("workspace_slug")
            if supplied_slug and supplied_slug != resolved.connection.workspace.slug:
                return Response(
                    {"error": "Tool tests are limited to the connected workspace."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            arguments["workspace_slug"] = resolved.connection.workspace.slug

        request_id = secrets.token_hex(8)
        record_event(
            resolved.connection.id,
            "tool_call",
            f"The portal called {tool_name}.",
            request_id=request_id,
        )
        context = _PortalToolContext(
            headers={
                "x-api-key": resolved.api_key,
                "x-plane-mcp-connection-id": str(resolved.connection.id),
                "x-plane-mcp-request-id": request_id,
            }
        )
        try:
            result = async_to_sync(mcp_server.call_tool)(tool_name, arguments, context=context)
            payload = result.model_dump(mode="json", by_alias=True) if hasattr(result, "model_dump") else result
            succeeded = not bool(payload.get("isError", False)) if isinstance(payload, dict) else True
        except Exception as exc:
            record_event(
                resolved.connection.id,
                "tool_result",
                f"{tool_name} failed: {str(exc)[:300]}",
                request_id=request_id,
                succeeded=False,
            )
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        record_event(
            resolved.connection.id,
            "tool_result",
            f"{tool_name} returned a real MCP result.",
            request_id=request_id,
            succeeded=succeeded,
        )
        MCPConnection.objects.filter(id=resolved.connection.id).update(last_mcp_request_at=timezone.now())
        return Response({"tool_name": tool_name, "result": payload})


class MCPConnectionActivityEndpoint(PublicMCPAPIView):
    def get(self, request):
        resolved = resolve_connection(_raw_cookie_token(request))
        if resolved is None:
            return Response({"events": []})
        events = resolved.connection.events.all()[:50]
        return Response(
            {
                "events": [
                    {
                        "id": str(event.id),
                        "type": event.event_type,
                        "label": EVENT_LABELS.get(event.event_type, event.event_type),
                        "summary": event.summary,
                        "request_id": event.request_id,
                        "succeeded": event.succeeded,
                        "created_at": event.created_at.isoformat(),
                    }
                    for event in events
                ]
            }
        )
