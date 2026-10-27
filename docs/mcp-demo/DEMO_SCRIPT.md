# Teacher demonstration script

## Preparation

- Start Plane and apply database migrations.
- Create a disposable Plane user, workspace, Personal API Key, project, and at least one workflow state.
- If ChatGPT will be shown, obtain approval to start the HTTPS tunnel before the session.
- Open `/mcp-connect/` and keep Plane open in a second browser tab.

## Presentation

1. On **Connect**, explain that no `.env` file or terminal is needed by the end user.
2. Enter the workspace slug and disposable key. Select **Test connection** and show the identified user and workspace.
3. Select **Generate MCP connection**. On **Dashboard**, point out expiration, server status, tool count, and the bearer URL warning.
4. Open **Tools**. Select `plane_list_projects`, show its schema, execute it, and compare the real project names with Plane.
5. Open **Live demo**. Explain the flow from ChatGPT host to MCP client, Plane MCP server, MCP tool, REST API, and PostgreSQL.
6. Enter the dedicated project UUID and select **List existing tasks**.
7. Select **Create test task** and approve the confirmation. Copy the returned work item UUID into **Created parent task ID** if it is not filled automatically.
8. Select **Verify task exists**. Refresh the Plane project and show the same item.
9. Select **Create child subtask** and confirm it appears under the parent in Plane.
10. Enter a valid state UUID and select **Update task status**. Show the state change in Plane.
11. Point to the sanitized activity entries: MCP tool call, Plane REST API request, Plane REST API response, and MCP tool result.
12. Optionally connect MCP Inspector or ChatGPT using the copied HTTPS URL.
13. Return to **Dashboard** and select **Disconnect**. Show that the old endpoint no longer initializes.

## MCP Inspector

With the HTTPS endpoint copied from the dashboard:

```powershell
npx @modelcontextprotocol/inspector
```

In Inspector, select Streamable HTTP, paste the personal URL, leave authentication empty, connect, list tools, and call `plane_list_projects`. Use the exact opaque endpoint. Do not add an API key header.

For an automated protocol check, use an MCP client that sends `initialize`, `notifications/initialized`, `tools/list`, and `tools/call` to the generated URL. A successful HTTP probe alone is not sufficient because MCP requires a protocol handshake.

## Safety closeout

- Revoke the portal connection.
- Revoke the disposable Plane Personal API Key.
- Delete or archive demo work items and the demo project.
- Stop the tunnel if one was approved and started.
