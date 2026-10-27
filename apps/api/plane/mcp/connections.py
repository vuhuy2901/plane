# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.utils import timezone

from plane.db.models import MCPConnection


CONNECTION_COOKIE_NAME = "plane_mcp_connection"


class ConnectionCredentialError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedConnection:
    connection: MCPConnection
    api_key: str


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_connection_token() -> str:
    return secrets.token_urlsafe(32)


def _fernet() -> Fernet:
    material = f"{settings.SECRET_KEY}:plane-mcp-connect:v1".encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
    return Fernet(key)


def encrypt_api_key(api_key: str) -> str:
    return _fernet().encrypt(api_key.encode("utf-8")).decode("ascii")


def decrypt_api_key(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        raise ConnectionCredentialError("The saved Plane credential cannot be decrypted.") from exc


def normalize_server_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Enter a valid Plane server URL using http:// or https://.")
    if parsed.query or parsed.fragment:
        raise ValueError("Plane server URL cannot contain a query string or fragment.")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def connection_ttl() -> timedelta:
    return timedelta(hours=max(1, int(getattr(settings, "MCP_CONNECTION_TTL_HOURS", 168))))


def create_connection(*, api_key: str, plane_server_url: str, workspace, user) -> tuple[MCPConnection, str]:
    raw_token = generate_connection_token()
    connection = MCPConnection.objects.create(
        token_hash=token_digest(raw_token),
        encrypted_api_key=encrypt_api_key(api_key),
        plane_server_url=normalize_server_url(plane_server_url),
        workspace=workspace,
        user=user,
        expires_at=timezone.now() + connection_ttl(),
    )
    return connection, raw_token


def resolve_connection(raw_token: str, *, require_available: bool = True) -> ResolvedConnection | None:
    if not raw_token or len(raw_token) > 200:
        return None
    connection = (
        MCPConnection.objects.select_related("workspace", "user").filter(token_hash=token_digest(raw_token)).first()
    )
    if connection is None or (require_available and not connection.is_available):
        return None
    return ResolvedConnection(connection=connection, api_key=decrypt_api_key(connection.encrypted_api_key))
