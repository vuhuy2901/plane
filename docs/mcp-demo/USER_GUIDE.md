# Plane MCP Connect user guide

## Create a Plane Personal API Key

1. Sign in to Plane with the disposable account prepared for the demonstration.
2. Open profile settings.
3. Select API Tokens.
4. Create a token with a clear label such as `MCP classroom demo` and an appropriate expiry.
5. Copy the key once. Do not paste it into chat, source code, screenshots, or shared notes.

## Create the connection

1. Open `https://<your-plane-host>/mcp-connect/`.
2. Confirm the prefilled Plane Server URL.
3. Enter the workspace slug from the Plane workspace URL.
4. Paste the Personal API Key.
5. Select **Test connection**.
6. After validation succeeds, select **Generate MCP connection**.
7. Copy the Personal MCP URL from the dashboard.

The saved API key is not displayed again. Treat the Personal MCP URL as a password because anyone holding it can use the connected Plane permissions until the connection expires or is revoked.

## Connect ChatGPT

Custom MCP access depends on the ChatGPT plan and workspace policy. Current setup and plan details are maintained in the [official OpenAI developer mode guide](https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt).

1. Use ChatGPT on the web and enable Developer mode under Settings > Apps > Advanced settings, if available.
2. Open Settings > Apps and select Create.
3. Enter the Personal MCP URL.
4. Choose **No authentication**. The demo URL itself is the bearer credential.
5. Select **Scan Tools**, review the discovered Plane actions, and create the app.
6. Start a new conversation and select the Plane app from the tools menu.
7. Begin with a read-only prompt such as `List my Plane projects`.
8. Confirm write actions only when their workspace, project, and content are correct.

If the create option is absent, the current plan, role, or workspace policy does not provide custom MCP access. Use MCP Inspector for the classroom demonstration instead.

## Explore and test tools

Open the **Tools** section. Tools and their JSON schemas are loaded directly from the MCP registry. Read tools execute immediately. Write tools show a confirmation prompt and should target a dedicated disposable project.

The **Live demo** section provides the presentation workflow: list projects, list work items, create a test work item, retrieve it, create a child, and update state. Project, work item, and state IDs must come from real earlier results.

## Disconnect

Select **Disconnect** on the dashboard. The server revokes the record immediately and removes the browser cookie. A regenerated connection also revokes the previous URL.

## Limitations

- This is a demo bearer-URL design, not OAuth.
- One connection is bound to one Plane instance and workspace.
- The hosting instance's Django `SECRET_KEY` protects encrypted credentials.
- ChatGPT must reach a public HTTPS endpoint. It cannot connect directly to localhost.
- Custom MCP availability and UI vary by ChatGPT plan and workspace policy.
- Use disposable users, tokens, and projects. Delete demonstration data afterward.
