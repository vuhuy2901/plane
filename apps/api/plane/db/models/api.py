# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
from uuid import uuid4

# Django imports
from django.db import models
from django.conf import settings

from .base import BaseModel


def generate_label_token():
    return uuid4().hex


def generate_token():
    return "plane_api_" + uuid4().hex


class APIToken(BaseModel):
    # Meta information
    label = models.CharField(max_length=255, default=generate_label_token)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    last_used = models.DateTimeField(null=True)

    # Token
    token = models.CharField(max_length=255, unique=True, default=generate_token, db_index=True)

    # User Information
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bot_tokens")
    user_type = models.PositiveSmallIntegerField(choices=((0, "Human"), (1, "Bot")), default=0)
    workspace = models.ForeignKey("db.Workspace", related_name="api_tokens", on_delete=models.CASCADE, null=True)
    expired_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = "API Token"
        verbose_name_plural = "API Tokems"
        db_table = "api_tokens"
        ordering = ("-created_at",)

    def __str__(self):
        return str(self.user.id)


class APIActivityLog(BaseModel):
    token_identifier = models.CharField(max_length=255)

    # Request Info
    path = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    query_params = models.TextField(null=True, blank=True)
    headers = models.TextField(null=True, blank=True)
    body = models.TextField(null=True, blank=True)

    # Response info
    response_code = models.PositiveIntegerField()
    response_body = models.TextField(null=True, blank=True)

    # Meta information
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, null=True, blank=True)

    class Meta:
        verbose_name = "API Activity Log"
        verbose_name_plural = "API Activity Logs"
        db_table = "api_activity_logs"
        ordering = ("-created_at",)

    def __str__(self):
        return str(self.token_identifier)


class MCPConnection(BaseModel):
    """A revocable bearer-URL connection for the Plane MCP demo portal."""

    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    encrypted_api_key = models.TextField()
    plane_server_url = models.URLField(max_length=500)
    workspace = models.ForeignKey("db.Workspace", related_name="mcp_connections", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="mcp_connections", on_delete=models.CASCADE)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_mcp_request_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "mcp_connections"
        ordering = ("-created_at",)

    @property
    def is_available(self):
        from django.utils import timezone

        return self.revoked_at is None and self.expires_at > timezone.now()


class MCPConnectionEvent(BaseModel):
    """A sanitized event emitted while a portal connection processes MCP work."""

    connection = models.ForeignKey(MCPConnection, related_name="events", on_delete=models.CASCADE)
    event_type = models.CharField(max_length=40)
    summary = models.CharField(max_length=500)
    request_id = models.CharField(max_length=64, blank=True)
    succeeded = models.BooleanField(default=True)

    class Meta:
        db_table = "mcp_connection_events"
        ordering = ("-created_at",)
