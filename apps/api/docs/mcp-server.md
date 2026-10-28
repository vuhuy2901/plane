# Plane MCP server

Plane exposes a Model Context Protocol server over Streamable HTTP at
`https://<your-plane-host>/mcp/`. It uses the same API v1 permissions,
validation, rate limits, activity logging, and webhook behavior as other Plane
API clients.

## Authentication

Create a Plane Personal Access Token and send it as a bearer token:

```http
Authorization: Bearer <plane-personal-access-token>
```

`X-Api-Key` is also accepted for compatibility with existing Plane API
clients. If both headers are present, they must contain the same token. Do not
commit a token to the repository or a shared MCP configuration.

## Client configuration

Use an HTTP MCP client and point it at the public Plane URL. The exact config
file varies by client; the connection values are:

```json
{
  "url": "https://plane.example.com/mcp/",
  "headers": {
    "Authorization": "Bearer ${PLANE_API_TOKEN}"
  }
}
```

The server exposes 60 tools. Mutations only succeed when the PAT owner has
the corresponding Plane role. All tools use internal API requests with the
same token, rather than direct database writes.
Collection APIs that return a bare array are represented as
`{"results": [...]}` so MCP structured outputs remain objects.

## Agent workflows

The server instructions tell agents to resolve human identifiers, inspect
configuration, perform the requested work, and verify the result.
Tool availability does not give permission to delete unrelated records.

| Area             | Capabilities                                                                                                    |
| ---------------- | --------------------------------------------------------------------------------------------------------------- |
| Discovery        | Workspaces, projects, workspace/project members                                                                 |
| Work items       | Paginated list, exact key lookup (e.g. QLDP-215), search, read, create, update, delete, hierarchy import        |
| Batch operations | Update or delete 1–50 explicit item UUIDs, preview by default, individual success/error results                 |
| Discussion       | List/create/update/delete comments and external links; read activity and attachments                            |
| Dependencies     | Read relations, create validated dependency relations                                                           |
| Planning         | List/read/create/update/delete cycles and modules; list/add/remove their work items                             |
| Configuration    | List/create/update/delete states and labels; read work item types, hierarchy, workflows and transition previews |
| Estimates        | Read configured estimate system and point UUIDs; assign through work item updates                               |
| Analytics        | Permission-scoped counts, bugs, overdue work, members, projects, cycles, automation and Story Points            |

### Examples

- “Find QLDP-215 and delete that task.” Resolve with
  `plane_get_work_item_by_identifier`, inspect the result, then call
  `plane_delete_work_item` with its project UUID, item UUID and
  `expected_name`. The tool refuses deletion if the name no longer matches.
- “Move these three tasks to the current cycle.” List cycles, resolve item
  IDs, then use `plane_add_cycle_work_items`. An item can move out of its
  previous cycle.
- “Assign these tasks and set high priority.” Resolve the member UUID,
  preview `plane_bulk_update_work_items` with
  `changes={"assignees": ["<member-uuid>"], "priority": "high"}`, then
  apply with `dry_run=false`. Lists such as assignees/labels replace the
  current set; read the item before preserving and extending an existing set.
- “Report progress and points for October.” Call
  `plane_get_analytics_report` with `date_from="2026-10-01"` and
  `date_to="2026-10-31"`, optionally adding project/member/state/cycle/module/type
  UUID lists. State the returned date scope and excluded estimate systems.

Batch calls are sequential, not atomic. A failed item does not undo earlier
successes. Review `results` and retry only failed IDs; never assume that a
timeout means a create did not happen. Preview reads verify visibility, but
do not guarantee write permission or workflow validity at execution time.

Analytics uses the same report implementation as the web UI, exposed for
PAT clients at `/api/v1/workspaces/<slug>/analytics-report/` with API-key
throttling. Default period is the last 30 days by creation date. A paired
custom date range can span up to 366 days. Estimate totals count leaf items,
exclude cancelled/non-Points projects, and divide points equally across
current assignees. Completion trends use completion date; they do not
reconstruct historical estimates or state transitions.

This edition's work-item list does not support arbitrary structured/PQL
filters. Search results have an explicit cap; use pagination for full lists,
and the analytics tool for aggregate counts.

## Loading updated tools

Restart/rebuild the API after deploying this code. Refresh/reconnect the MCP
client so it fetches `tools/list` again; some clients need a new conversation.
Existing personal connection URLs and PATs continue to use the same server.
The standard and personal-URL routes share one transport/session manager so
both are initialized by the ASGI lifespan.
The MCP connection portal discovers its tool catalogue from the server.
No database migration is required for these additions.

## Deployment settings

DNS rebinding protection is enabled. Plane derives allowed MCP hosts from
`WEB_URL`, `APP_BASE_URL`, and `API_BASE_URL`, and derives browser origins from
`CORS_ALLOWED_ORIGINS`. Override the derived values when needed:

```dotenv
MCP_ALLOWED_HOSTS="plane.example.com,plane.example.com:*"
MCP_ALLOWED_ORIGINS="https://agent.example.com"
```

`MCP_ALLOWED_ORIGINS` is only needed for browser-based clients that send an
`Origin` header. Non-browser MCP clients normally omit it.
