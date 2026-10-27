# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from plane.db.models import MCPConnectionEvent


EVENT_LABELS = {
    "initialize": "MCP Initialize",
    "tools_discovery": "MCP Tools Discovery",
    "tool_call": "MCP Tool Call",
    "plane_request": "Plane REST API Request",
    "plane_response": "Plane REST API Response",
    "tool_result": "MCP Tool Result",
}


def record_event(connection_id, event_type: str, summary: str, *, request_id: str = "", succeeded: bool = True):
    """Persist a bounded, credential-free activity entry."""
    if not connection_id or event_type not in EVENT_LABELS:
        return None
    return MCPConnectionEvent.objects.create(
        connection_id=connection_id,
        event_type=event_type,
        summary=summary[:500],
        request_id=str(request_id)[:64],
        succeeded=succeeded,
    )
