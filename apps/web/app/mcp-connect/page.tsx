/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@makeplane/propel/components/button";
import { InputField } from "@makeplane/propel/components/input-field";
import { TextAreaField } from "@makeplane/propel/components/text-area-field";
import {
  Chatgpt,
  CopyOutline,
  HideOutline,
  KeyOutline,
  MemoryOutline,
  NetworkOutline,
  PlayOutline,
  RefreshOutline,
  ServerOutline,
  ShowOutline,
  ToolOutline,
} from "@makeplane/propel/icons";
import { PlaneLogo } from "@plane/blocks/icons";
import { API_BASE_URL } from "@plane/constants";
import type { Route } from "./+types/page";

export const meta: Route.MetaFunction = () => [
  { title: "Plane MCP Connect" },
  { name: "description", content: "Create and test a personal Plane MCP connection." },
];

type ConnectionStatus = {
  connected: boolean;
  status: "connected" | "disconnected" | "expired" | "revoked";
  user?: { name: string; email: string };
  workspace?: { name: string; slug: string };
  plane_server_url: string;
  mcp_server_status?: string;
  public_base_url?: string;
  effective_public_base_url?: string;
  mcp_url?: string;
  expires_at?: string;
  last_mcp_request_at?: string | null;
};

type MCPTool = {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  classification: "read" | "write";
  available: boolean;
};

type ActivityEvent = {
  id: string;
  type: string;
  label: string;
  summary: string;
  request_id: string;
  succeeded: boolean;
  created_at: string;
};

type ProjectOption = { id: string; name: string; identifier: string };

type PortalTab = "connect" | "dashboard" | "tools" | "guide" | "demo";

const api = async <T,>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  const payload = (await response.json().catch(() => ({}))) as T & { error?: string };
  if (!response.ok) throw new Error(payload.error || `Request failed with HTTP ${response.status}.`);
  return payload;
};

const formatDate = (value?: string | null) => {
  if (!value) return "Not yet";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
};

const JsonPanel = ({ value }: { value: unknown }) => (
  <pre className="max-h-96 overflow-auto rounded-md border border-subtle bg-layer-1 p-4 font-code text-12 leading-5 break-words whitespace-pre-wrap text-primary">
    {JSON.stringify(value, null, 2)}
  </pre>
);

const copyToClipboard = async (text: string): Promise<boolean> => {
  if (!text) return false;
  if (typeof navigator !== "undefined" && navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall through to fallback
    }
  }

  try {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.top = "-9999px";
    textArea.style.left = "-9999px";
    textArea.style.opacity = "0";
    textArea.setAttribute("readonly", "");
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    const successful = document.execCommand("copy");
    textArea.remove();
    return successful;
  } catch {
    return false;
  }
};

const McpUrlBox = ({
  id,
  url,
  onCopy,
  configuredPublicBaseUrl,
  effectivePublicBaseUrl,
  publicUrlDraft,
  setPublicUrlDraft,
  isEditing,
  onEdit,
  onSave,
  onCancel,
  saving,
}: {
  id: string;
  url: string;
  onCopy: () => void;
  configuredPublicBaseUrl: string;
  effectivePublicBaseUrl: string;
  publicUrlDraft: string;
  setPublicUrlDraft: (value: string) => void;
  isEditing: boolean;
  onEdit: () => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
}) => (
  <div className="mt-6 rounded-md border border-subtle bg-layer-1 p-4">
    <div className="flex items-center justify-between gap-2">
      <label className="text-12 font-medium text-secondary" htmlFor={id}>
        Personal MCP URL
      </label>
      <span className="text-11 font-medium text-tertiary">{url ? "Đã sẵn sàng kết nối" : "Chưa có URL"}</span>
    </div>
    <div className="mt-2 flex flex-col gap-2 sm:flex-row">
      <input
        id={id}
        readOnly
        value={url}
        placeholder="Chưa có URL MCP (Hãy tạo ở tab Connect trước)..."
        onClick={(e) => e.currentTarget.select()}
        className="min-w-0 flex-1 rounded-md border border-subtle bg-layer-2 px-3 py-2 font-code text-12 text-primary outline-none select-all focus:border-accent-strong"
      />
      <Button
        variant="primary"
        size="md"
        stretch="auto"
        label="Copy MCP URL"
        icon={<CopyOutline className="size-4" />}
        onClick={onCopy}
      />
    </div>
    <div className="mt-3 border-t border-subtle pt-3">
      <div className="flex items-center justify-between gap-3">
        <label className="text-11 font-medium text-secondary" htmlFor={`${id}-tunnel`}>
          Public Tunnel URL (Optional)
        </label>
        {url && !isEditing && (
          <button type="button" className="text-12 font-medium text-accent-primary hover:underline" onClick={onEdit}>
            Edit Public URL
          </button>
        )}
      </div>
      {isEditing ? (
        <>
          <input
            id={`${id}-tunnel`}
            value={publicUrlDraft}
            onChange={(event) => setPublicUrlDraft(event.target.value)}
            placeholder="https://geopolitical-anthropomorphously-rosena.ngrok-free.dev"
            className="mt-1 w-full rounded-md border border-subtle bg-layer-2 px-3 py-1.5 font-code text-12 text-primary outline-none placeholder:text-tertiary focus:border-accent-strong"
          />
          <div className="mt-2 flex gap-2">
            <Button variant="primary" size="sm" stretch="auto" label="Save" loading={saving} onClick={onSave} />
            <Button variant="secondary" size="sm" stretch="auto" label="Cancel" onClick={onCancel} />
          </div>
        </>
      ) : (
        <div className="mt-1 font-code text-12 break-all text-primary">
          {configuredPublicBaseUrl || `${effectivePublicBaseUrl} (server default)`}
        </div>
      )}
      <p className="mt-1 text-11 text-tertiary">
        Supports HTTPS tunnels and custom domains. Localhost is development-only.
      </p>
    </div>
  </div>
);

export default function MCPConnectPage() {
  const [tab, setTab] = useState<PortalTab>("connect");
  const [connection, setConnection] = useState<ConnectionStatus | null>(null);
  const [publicBaseUrl, setPublicBaseUrl] = useState("https://geopolitical-anthropomorphously-rosena.ngrok-free.dev");
  const [publicUrlDraft, setPublicUrlDraft] = useState("https://geopolitical-anthropomorphously-rosena.ngrok-free.dev");
  const [isEditingPublicUrl, setIsEditingPublicUrl] = useState(false);
  const [planeServerUrl, setPlaneServerUrl] = useState("");
  const [workspaceSlug, setWorkspaceSlug] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [busy, setBusy] = useState<string | null>("status");
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [selectedToolName, setSelectedToolName] = useState("");
  const [argumentsText, setArgumentsText] = useState("{}");
  const [toolResult, setToolResult] = useState<unknown>(null);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [demoProjectId, setDemoProjectId] = useState("");
  const [demoStateId, setDemoStateId] = useState("");
  const [demoParentId, setDemoParentId] = useState("");
  const [demoResult, setDemoResult] = useState<unknown>(null);
  const selectedTool = useMemo(() => tools.find((tool) => tool.name === selectedToolName), [tools, selectedToolName]);

  const effectiveMcpUrl = connection?.mcp_url || "";

  const loadStatus = useCallback(async () => {
    try {
      const status = await api<ConnectionStatus>("/api/mcp-connect/status/");
      setConnection(status);
      const defaultUrl =
        status.public_base_url ||
        status.effective_public_base_url ||
        "https://geopolitical-anthropomorphously-rosena.ngrok-free.dev";
      setPublicBaseUrl(defaultUrl);
      setPublicUrlDraft(defaultUrl);
      setPlaneServerUrl(status.plane_server_url || window.location.origin);
      if (status.workspace) setWorkspaceSlug(status.workspace.slug);
      if (status.mcp_url) setTab((current) => (current === "connect" ? "dashboard" : current));
    } catch (error) {
      setPlaneServerUrl(window.location.origin);
      setNotice({ kind: "error", text: error instanceof Error ? error.message : "Plane server is unavailable." });
    } finally {
      setBusy(null);
    }
  }, []);

  const loadTools = useCallback(async () => {
    if (!connection?.connected) return;
    try {
      const payload = await api<{ tools: MCPTool[] }>("/api/mcp-connect/tools/");
      setTools(payload.tools);
      setSelectedToolName(
        (current) =>
          current ||
          payload.tools.find((tool) => tool.name === "plane_list_projects")?.name ||
          payload.tools[0]?.name ||
          ""
      );
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof Error ? error.message : "Tool discovery failed." });
    }
  }, [connection?.connected]);

  const loadActivity = useCallback(async () => {
    if (!connection?.connected) return;
    const payload = await api<{ events: ActivityEvent[] }>("/api/mcp-connect/activity/");
    setEvents(payload.events);
  }, [connection?.connected]);

  const loadProjects = useCallback(async () => {
    if (!connection?.connected) return;
    try {
      const payload = await api<{ projects: ProjectOption[] }>("/api/mcp-connect/projects/");
      setProjects(payload.projects);
      setDemoProjectId((current) => current || payload.projects[0]?.id || "");
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof Error ? error.message : "Project discovery failed." });
    }
  }, [connection?.connected]);

  useEffect(() => void loadStatus(), [loadStatus]);
  useEffect(() => void loadTools(), [loadTools]);
  useEffect(() => {
    if (!connection?.connected) return;
    void loadActivity();
    const interval = window.setInterval(() => void loadActivity(), 4000);
    return () => window.clearInterval(interval);
  }, [connection?.connected, loadActivity]);
  useEffect(() => void loadProjects(), [loadProjects]);

  useEffect(() => {
    if (!selectedTool) return;
    const properties = (selectedTool.input_schema.properties || {}) as Record<string, unknown>;
    const suggested: Record<string, unknown> = {};
    if ("workspace_slug" in properties && workspaceSlug) suggested.workspace_slug = workspaceSlug;
    if ("project_id" in properties) suggested.project_id = demoProjectId || "";
    if ("name" in properties) suggested.name = "MCP demo task";
    setArgumentsText(JSON.stringify(suggested, null, 2));
  }, [selectedTool, workspaceSlug, demoProjectId]);

  const submitCredentials = async (create: boolean) => {
    setBusy(create ? "create" : "test");
    setNotice(null);
    try {
      const payload = await api<ConnectionStatus & { ok?: boolean }>(
        create ? "/api/mcp-connect/connections/" : "/api/mcp-connect/test/",
        {
          method: "POST",
          body: JSON.stringify({
            plane_server_url: planeServerUrl,
            public_base_url: publicBaseUrl,
            workspace_slug: workspaceSlug,
            api_key: apiKey,
          }),
        }
      );
      if (create) {
        setConnection(payload);
        setPublicBaseUrl(payload.public_base_url || "");
        setPublicUrlDraft(payload.public_base_url || "");
        setApiKey("");
        setShowApiKey(false);
        setTab("dashboard");
        setNotice({ kind: "success", text: "Your personal MCP connection is ready." });
      } else {
        setNotice({ kind: "success", text: "Connection validated. You can generate the personal MCP URL." });
      }
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof Error ? error.message : "Connection validation failed." });
    } finally {
      setBusy(null);
    }
  };

  const savePublicUrl = async () => {
    setBusy("public-url");
    setNotice(null);
    try {
      const payload = await api<ConnectionStatus>("/api/mcp-connect/connections/", {
        method: "PATCH",
        body: JSON.stringify({ public_base_url: publicUrlDraft }),
      });
      setConnection(payload);
      setPublicBaseUrl(payload.public_base_url || "");
      setPublicUrlDraft(payload.public_base_url || "");
      setIsEditingPublicUrl(false);
      setNotice({
        kind: "success",
        text: "Public URL updated. If your MCP client uses the previous URL, update its server configuration.",
      });
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof Error ? error.message : "Public URL update failed." });
    } finally {
      setBusy(null);
    }
  };

  const copyMcpUrl = async (overrideUrl?: string) => {
    const urlToCopy = overrideUrl || effectiveMcpUrl;
    if (!urlToCopy) {
      setNotice({
        kind: "error",
        text: "Chưa có Personal MCP URL. Vui lòng vào tab 'Connect' để tạo kết nối trước!",
      });
      setTab("connect");
      return;
    }

    const success = await copyToClipboard(urlToCopy);
    if (success) {
      setNotice({
        kind: "success",
        text: `Đã copy MCP URL: ${urlToCopy}`,
      });
    } else {
      const input = (document.getElementById("mcp-url") ||
        document.getElementById("mcp-url-guide")) as HTMLInputElement | null;
      if (input) {
        input.focus();
        input.select();
      }
      setNotice({
        kind: "error",
        text: "Không thể tự động copy. Vui lòng nhấp vào ô URL và nhấn Ctrl+C.",
      });
    }
  };

  const regenerate = async () => {
    setBusy("regenerate");
    try {
      const payload = await api<ConnectionStatus>("/api/mcp-connect/regenerate/", { method: "POST", body: "{}" });
      setConnection(payload);
      setPublicBaseUrl(payload.public_base_url || "");
      setPublicUrlDraft(payload.public_base_url || "");
      setNotice({ kind: "success", text: "The old URL was revoked and a new URL was generated." });
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof Error ? error.message : "Regeneration failed." });
    } finally {
      setBusy(null);
    }
  };

  const disconnect = async () => {
    setBusy("disconnect");
    try {
      await api("/api/mcp-connect/revoke/", { method: "POST", body: "{}" });
      setConnection({ connected: false, status: "disconnected", plane_server_url: planeServerUrl });
      setIsEditingPublicUrl(false);
      setTools([]);
      setProjects([]);
      setEvents([]);
      setTab("connect");
      setNotice({ kind: "success", text: "The personal MCP URL has been revoked." });
    } finally {
      setBusy(null);
    }
  };

  const executeTool = async (toolName = selectedToolName, argsText = argumentsText, confirmed = false) => {
    setBusy(`tool:${toolName}`);
    setToolResult(null);
    try {
      const args = JSON.parse(argsText) as Record<string, unknown>;
      const payload = await api<{ result: unknown }>("/api/mcp-connect/tools/test/", {
        method: "POST",
        body: JSON.stringify({ tool_name: toolName, arguments: args, confirm_write: confirmed }),
      });
      setToolResult(payload.result);
      await Promise.all([loadActivity(), loadStatus()]);
      return payload.result;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Tool execution failed.";
      setToolResult({ error: message });
      return null;
    } finally {
      setBusy(null);
    }
  };

  const runDemo = async (action: "projects" | "tasks" | "create" | "verify" | "child" | "status") => {
    const configurations = {
      projects: ["plane_list_projects", { workspace_slug: workspaceSlug }, false],
      tasks: ["plane_list_work_items", { workspace_slug: workspaceSlug, project_id: demoProjectId }, false],
      create: [
        "plane_create_work_item",
        { workspace_slug: workspaceSlug, project_id: demoProjectId, name: `MCP demo task ${new Date().toISOString()}` },
        true,
      ],
      verify: [
        "plane_get_work_item",
        { workspace_slug: workspaceSlug, project_id: demoProjectId, work_item_id: demoParentId },
        false,
      ],
      child: [
        "plane_create_work_item",
        {
          workspace_slug: workspaceSlug,
          project_id: demoProjectId,
          name: "MCP demo child task",
          parent_id: demoParentId,
        },
        true,
      ],
      status: [
        "plane_update_work_item",
        {
          workspace_slug: workspaceSlug,
          project_id: demoProjectId,
          work_item_id: demoParentId,
          changes: { state: demoStateId },
        },
        true,
      ],
    } as const;
    const [toolName, args, isWrite] = configurations[action];
    if (isWrite && !window.confirm("Execute this real write operation in the dedicated demo project?")) return;
    try {
      const result = await executeTool(toolName, JSON.stringify(args), isWrite);
      setDemoResult(result);
      if (action === "create" && result && typeof result === "object") {
        const resultObject = result as Record<string, unknown>;
        const content = resultObject.structuredContent as Record<string, unknown> | undefined;
        const id = content?.id;
        if (typeof id === "string") setDemoParentId(id);
      }
    } catch {
      setDemoResult(toolResult);
    }
  };

  const tabs: { id: PortalTab; label: string; disabled?: boolean }[] = [
    { id: "connect", label: "Connect" },
    { id: "dashboard", label: "Dashboard", disabled: !connection?.mcp_url },
    { id: "tools", label: "Tools", disabled: !connection?.connected },
    { id: "guide", label: "AI / ChatGPT" },
    { id: "demo", label: "Live demo", disabled: !connection?.connected },
  ];

  return (
    <div className="h-full overflow-y-auto bg-surface-1 text-primary">
      <header className="sticky top-0 z-[1] border-b border-subtle bg-surface-1/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-3">
            <PlaneLogo className="h-7 w-auto text-primary" />
            <div className="h-5 w-px bg-layer-1" />
            <span className="text-14 font-semibold">MCP Connect</span>
          </div>
          <div className="flex items-center gap-2 text-12 text-secondary">
            <span className={`size-2 rounded-full ${connection?.connected ? "bg-success-primary" : "bg-layer-3"}`} />
            {connection?.connected ? "Connection active" : "Not connected"}
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-8 sm:px-6 lg:grid-cols-[220px_minmax(0,1fr)] lg:py-12">
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="mb-6">
            <h1 className="text-24 font-semibold tracking-tight">Connect Plane to ChatGPT</h1>
            <p className="mt-2 text-13 leading-5 text-secondary">
              Create a revocable MCP URL without editing environment files.
            </p>
          </div>
          <nav className="flex gap-1 overflow-x-auto pb-2 lg:flex-col" aria-label="Portal sections">
            {tabs.map((item) => (
              <button
                key={item.id}
                type="button"
                disabled={item.disabled}
                onClick={() => setTab(item.id)}
                className={`min-w-max rounded-md px-3 py-2 text-left text-13 font-medium transition-colors active:translate-y-px disabled:cursor-not-allowed disabled:text-disabled ${
                  tab === item.id
                    ? "bg-layer-1 text-primary"
                    : "text-secondary hover:bg-layer-transparent-hover hover:text-primary"
                }`}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <div className="mt-6 hidden border-t border-subtle pt-5 text-12 leading-5 text-tertiary lg:block">
            Credentials stay encrypted on the server. The browser stores only an HttpOnly connection cookie.
          </div>
        </aside>

        <main className="min-w-0">
          {notice && (
            <div
              role="status"
              className={`mb-5 rounded-md border px-4 py-3 text-13 ${
                notice.kind === "error"
                  ? "border-danger-strong bg-danger-subtle text-danger-primary"
                  : "border-success-strong bg-success-subtle text-success-primary"
              }`}
            >
              {notice.text}
            </div>
          )}

          {busy === "status" ? (
            <div className="space-y-4" aria-label="Loading connection status">
              <div className="h-8 w-64 animate-pulse rounded-md bg-layer-1" />
              <div className="h-72 animate-pulse rounded-md bg-layer-1" />
            </div>
          ) : tab === "connect" ? (
            <section className="max-w-2xl">
              <h2 className="text-20 font-semibold">Plane connection</h2>
              <p className="mt-1 text-13 text-secondary">
                Use a disposable demo account and a Personal API Key with access to one workspace.
              </p>
              <form
                className="mt-7 space-y-5"
                onSubmit={(event) => {
                  event.preventDefault();
                  void submitCredentials(true);
                }}
              >
                <InputField
                  size="xl"
                  orientation="vertical"
                  label="Plane Server URL"
                  description="This demo accepts the Plane instance hosting this portal."
                  required
                  value={planeServerUrl}
                  onChange={(event) => setPlaneServerUrl(event.target.value)}
                  placeholder="https://plane.example.com"
                />
                <InputField
                  size="xl"
                  orientation="vertical"
                  label="Public Tunnel URL (Optional)"
                  description="Use an HTTPS ngrok, Cloudflare Tunnel, or custom domain. A server default is used when blank."
                  value={publicBaseUrl}
                  onChange={(event) => setPublicBaseUrl(event.target.value)}
                  placeholder="https://geopolitical-anthropomorphously-rosena.ngrok-free.dev"
                />
                <InputField
                  size="xl"
                  orientation="vertical"
                  label="Workspace Slug"
                  description="Find this value in the workspace URL."
                  required
                  value={workspaceSlug}
                  onChange={(event) => setWorkspaceSlug(event.target.value)}
                  placeholder="engineering"
                />
                <InputField
                  size="xl"
                  orientation="vertical"
                  label="Personal API Key"
                  description="The full key is never shown again after the connection is saved."
                  required
                  type={showApiKey ? "text" : "password"}
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder="plane_api_..."
                  startIcon={<KeyOutline className="size-4 text-secondary" />}
                  endIcon={
                    <button
                      type="button"
                      onClick={() => setShowApiKey((value) => !value)}
                      aria-label={showApiKey ? "Hide API Key" : "Show API Key"}
                    >
                      {showApiKey ? <HideOutline className="size-4" /> : <ShowOutline className="size-4" />}
                    </button>
                  }
                />
                <div className="flex flex-wrap gap-2 pt-2">
                  <Button
                    type="button"
                    variant="secondary"
                    size="md"
                    stretch="auto"
                    label="Test connection"
                    loading={busy === "test"}
                    onClick={() => void submitCredentials(false)}
                  />
                  <Button
                    type="submit"
                    variant="primary"
                    size="md"
                    stretch="auto"
                    label="Generate MCP connection"
                    loading={busy === "create"}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="md"
                    stretch="auto"
                    label="Reset form"
                    onClick={() => {
                      setWorkspaceSlug("");
                      setApiKey("");
                      setNotice(null);
                    }}
                  />
                </div>
              </form>
            </section>
          ) : tab === "dashboard" && connection?.mcp_url ? (
            <section>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h2 className="text-20 font-semibold">Connection dashboard</h2>
                  <p className="mt-1 text-13 text-secondary">
                    This URL is a bearer credential. Share it only with the MCP client you trust.
                  </p>
                </div>
                <span
                  className={`rounded-md border px-2.5 py-1 text-12 font-medium ${
                    connection.connected
                      ? "border-success-strong bg-success-subtle text-success-primary"
                      : "border-warning-strong bg-warning-subtle text-warning-primary"
                  }`}
                >
                  {connection.status === "connected"
                    ? "Connected"
                    : connection.status === "expired"
                      ? "Expired"
                      : connection.status === "revoked"
                        ? "Revoked"
                        : "Disconnected"}
                </span>
              </div>
              <dl className="mt-7 grid gap-x-8 gap-y-5 border-y border-subtle py-6 sm:grid-cols-2">
                {[
                  ["Connected user", `${connection.user?.name} (${connection.user?.email})`],
                  ["Workspace", `${connection.workspace?.name} (${connection.workspace?.slug})`],
                  ["MCP server", connection.mcp_server_status],
                  ["Available tools", tools.length ? String(tools.length) : "Discovering"],
                  ["Connection expires", formatDate(connection.expires_at)],
                  ["Last successful MCP request", formatDate(connection.last_mcp_request_at)],
                ].map(([label, value]) => (
                  <div key={label}>
                    <dt className="text-12 font-medium text-tertiary">{label}</dt>
                    <dd className="mt-1 text-13 text-primary">{value}</dd>
                  </div>
                ))}
              </dl>
              <McpUrlBox
                id="mcp-url"
                url={effectiveMcpUrl}
                onCopy={() => void copyMcpUrl()}
                configuredPublicBaseUrl={connection.public_base_url || ""}
                effectivePublicBaseUrl={connection.effective_public_base_url || ""}
                publicUrlDraft={publicUrlDraft}
                setPublicUrlDraft={setPublicUrlDraft}
                isEditing={isEditingPublicUrl}
                onEdit={() => {
                  setPublicUrlDraft(connection.public_base_url || "");
                  setIsEditingPublicUrl(true);
                }}
                onSave={() => void savePublicUrl()}
                onCancel={() => {
                  setPublicUrlDraft(connection.public_base_url || "");
                  setIsEditingPublicUrl(false);
                }}
                saving={busy === "public-url"}
              />
              <div className="mt-6 flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  size="md"
                  stretch="auto"
                  label="Test MCP"
                  icon={<PlayOutline className="size-4" />}
                  onClick={() => {
                    setTab("tools");
                    setSelectedToolName("plane_list_projects");
                  }}
                />
                <Button
                  variant="secondary"
                  size="md"
                  stretch="auto"
                  label="Regenerate connection"
                  icon={<RefreshOutline className="size-4" />}
                  loading={busy === "regenerate"}
                  onClick={() => void regenerate()}
                />
                <Button
                  variant="danger-outline"
                  size="md"
                  stretch="auto"
                  label="Disconnect"
                  loading={busy === "disconnect"}
                  onClick={() => void disconnect()}
                />
              </div>
            </section>
          ) : tab === "tools" ? (
            <section>
              <h2 className="text-20 font-semibold">MCP tools explorer</h2>
              <p className="mt-1 text-13 text-secondary">
                The list below comes from the live MCP registry. Responses are executed against Plane.
              </p>
              <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(260px,0.75fr)_minmax(0,1.25fr)]">
                <div className="max-h-[620px] space-y-2 overflow-y-auto pr-1">
                  {tools.length === 0 ? (
                    <div className="rounded-md border border-dashed border-subtle p-8 text-center text-13 text-secondary">
                      No registered tools were returned.
                    </div>
                  ) : (
                    tools.map((tool) => (
                      <button
                        key={tool.name}
                        type="button"
                        onClick={() => setSelectedToolName(tool.name)}
                        className={`w-full rounded-md border p-3 text-left transition-colors ${selectedToolName === tool.name ? "border-accent-strong bg-accent-primary/10" : "border-subtle hover:bg-layer-transparent-hover"}`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <code className="text-12 font-semibold text-primary">{tool.name}</code>
                          <span
                            className={`rounded-sm px-1.5 py-0.5 text-11 font-medium ${tool.classification === "read" ? "bg-layer-1 text-secondary" : "bg-warning-subtle text-warning-primary"}`}
                          >
                            {tool.classification}
                          </span>
                        </div>
                        <p className="mt-2 line-clamp-2 text-12 leading-5 text-secondary">{tool.description}</p>
                      </button>
                    ))
                  )}
                </div>
                {selectedTool ? (
                  <div className="min-w-0 space-y-5">
                    <div>
                      <div className="flex items-center gap-2">
                        <ToolOutline className="size-5 text-accent-primary" />
                        <h3 className="font-code text-14 font-semibold">{selectedTool.name}</h3>
                      </div>
                      <p className="mt-2 text-13 leading-5 text-secondary">{selectedTool.description}</p>
                    </div>
                    <details className="rounded-md border border-subtle bg-layer-1 p-3">
                      <summary className="cursor-pointer text-12 font-medium">Input schema</summary>
                      <div className="mt-3">
                        <JsonPanel value={selectedTool.input_schema} />
                      </div>
                    </details>
                    <TextAreaField
                      size="xl"
                      label="Arguments (JSON)"
                      description={
                        selectedTool.classification === "write"
                          ? "Use a dedicated demo project. Write tools require explicit confirmation."
                          : "Workspace slug is locked to the connected workspace."
                      }
                      value={argumentsText}
                      onChange={(event) => setArgumentsText(event.target.value)}
                      rows={9}
                    />
                    <Button
                      variant="primary"
                      size="md"
                      stretch="auto"
                      label={selectedTool.classification === "write" ? "Confirm and execute" : "Execute"}
                      loading={busy === `tool:${selectedTool.name}`}
                      onClick={() => {
                        const confirmed =
                          selectedTool.classification === "write"
                            ? window.confirm("Execute this real write operation in Plane?")
                            : false;
                        if (selectedTool.classification === "read" || confirmed)
                          void executeTool(selectedTool.name, argumentsText, confirmed);
                      }}
                    />
                    {toolResult !== null && <JsonPanel value={toolResult} />}
                  </div>
                ) : null}
              </div>
            </section>
          ) : tab === "guide" ? (
            <section className="max-w-3xl">
              <h2 className="text-20 font-semibold">AI / ChatGPT</h2>
              <p className="mt-1 text-13 text-secondary">
                Connect Plane to ChatGPT, then let it read projects and perform confirmed actions through MCP.
              </p>
              {!connection?.connected && (
                <div className="mt-5 rounded-md border border-accent-strong bg-accent-primary/10 p-4 text-13 leading-5 text-primary">
                  Start in the{" "}
                  <button
                    type="button"
                    className="font-semibold text-accent-primary hover:underline"
                    onClick={() => setTab("connect")}
                  >
                    Connect
                  </button>{" "}
                  tab to generate your personal MCP URL.
                </div>
              )}
              <div className="mt-5 rounded-md border border-warning-strong bg-warning-subtle p-4 text-13 leading-5 text-warning-primary">
                Custom MCP access depends on your ChatGPT plan and workspace permissions. Full read and write MCP
                support is currently available for Business and Enterprise/Edu workspaces on ChatGPT web. Pro access may
                be limited to read and fetch tools.
              </div>
              <ol className="mt-7 grid gap-3">
                {[
                  "Generate a connection in the Connect tab, then copy the Personal MCP URL from the dashboard.",
                  "In ChatGPT web, enable Developer mode in Settings > Apps > Advanced settings, if your plan provides it.",
                  "Open Settings > Apps and choose Create.",
                  "Enter the MCP URL and choose No authentication for this demo bearer URL.",
                  "Select Scan Tools, review the discovered Plane actions, then create the app.",
                  "Open a new ChatGPT conversation and select the Plane app from the tools menu.",
                  "Ask it to list projects first. Confirm every write action before allowing it.",
                  "Open ChatGPT Work and use @Plane AI Manager if that app name is configured in your workspace.",
                ].map((step, index) => (
                  <li
                    key={step}
                    className="grid grid-cols-[28px_1fr] gap-3 rounded-md border border-subtle p-4 text-13 leading-5"
                  >
                    <span className="grid size-7 place-items-center rounded-md bg-layer-1 font-code text-12 font-semibold">
                      {index + 1}
                    </span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
              <McpUrlBox
                id="mcp-url-guide"
                url={effectiveMcpUrl}
                onCopy={() => void copyMcpUrl()}
                configuredPublicBaseUrl={connection?.public_base_url || ""}
                effectivePublicBaseUrl={connection?.effective_public_base_url || ""}
                publicUrlDraft={publicUrlDraft}
                setPublicUrlDraft={setPublicUrlDraft}
                isEditing={isEditingPublicUrl}
                onEdit={() => {
                  setPublicUrlDraft(connection?.public_base_url || "");
                  setIsEditingPublicUrl(true);
                }}
                onSave={() => void savePublicUrl()}
                onCancel={() => {
                  setPublicUrlDraft(connection?.public_base_url || "");
                  setIsEditingPublicUrl(false);
                }}
                saving={busy === "public-url"}
              />
              <div className="mt-6 flex flex-wrap gap-2">
                <Button
                  variant="primary"
                  size="md"
                  stretch="auto"
                  label="Copy MCP URL"
                  icon={<CopyOutline className="size-4" />}
                  onClick={() => void copyMcpUrl()}
                />
                <Button
                  variant="secondary"
                  size="md"
                  stretch="auto"
                  nativeButton={false}
                  render={
                    <a
                      href="https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt"
                      target="_blank"
                      rel="noreferrer"
                    >
                      Official setup guide
                    </a>
                  }
                  label="Official setup guide"
                />
              </div>
            </section>
          ) : tab === "demo" ? (
            <section>
              <h2 className="text-20 font-semibold">Live MCP demonstration</h2>
              <p className="mt-1 max-w-2xl text-13 leading-5 text-secondary">
                Every action below calls the registered MCP tool and persists changes through Plane REST API. Use only a
                disposable project.
              </p>
              <div className="mt-7 overflow-x-auto pb-2">
                <div className="grid min-w-[760px] grid-cols-[repeat(6,minmax(110px,1fr))] items-center gap-2">
                  {[
                    [Chatgpt, "MCP Host", "ChatGPT"],
                    [NetworkOutline, "MCP Client", "Connector"],
                    [ServerOutline, "MCP Server", "Plane MCP"],
                    [ToolOutline, "MCP Tools", `${tools.length} actions`],
                    [RefreshOutline, "Plane REST API", "API v1"],
                    [MemoryOutline, "Plane Database", "Persisted"],
                  ].map(([Icon, label, value]) => {
                    const NodeIcon = Icon as typeof ServerOutline;
                    return (
                      <div
                        key={String(label)}
                        className="relative rounded-md border border-subtle bg-layer-1 p-3 text-center before:absolute before:top-1/2 before:-right-2 before:h-px before:w-2 before:bg-layer-3 last:before:hidden"
                      >
                        <NodeIcon className="mx-auto size-5 text-accent-primary" />
                        <div className="mt-2 text-11 font-medium text-tertiary">{String(label)}</div>
                        <div className="mt-0.5 text-12 font-semibold">{String(value)}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="mt-7 grid gap-6 xl:grid-cols-2">
                <div>
                  <h3 className="text-14 font-semibold">Teacher workflow</h3>
                  <div className="mt-4 grid gap-4 sm:grid-cols-2">
                    <label className="flex flex-col gap-1.5 text-12 font-medium text-secondary">
                      Demo project
                      <select
                        value={demoProjectId}
                        onChange={(event) => setDemoProjectId(event.target.value)}
                        className="h-10 rounded-md border border-subtle bg-layer-1 px-3 text-13 text-primary outline-none focus:border-accent-strong"
                        disabled={!projects.length}
                      >
                        {!projects.length && <option value="">No projects available</option>}
                        {projects.map((project) => (
                          <option key={project.id} value={project.id}>
                            {project.identifier} · {project.name}
                          </option>
                        ))}
                      </select>
                      <span className="font-normal text-tertiary">Select a project from the connected workspace.</span>
                    </label>
                    <InputField
                      size="lg"
                      orientation="vertical"
                      label="State ID for final update"
                      value={demoStateId}
                      onChange={(event) => setDemoStateId(event.target.value)}
                      placeholder="State UUID"
                    />
                    <InputField
                      size="lg"
                      orientation="vertical"
                      label="Created parent task ID"
                      value={demoParentId}
                      onChange={(event) => setDemoParentId(event.target.value)}
                      placeholder="Filled after creation"
                    />
                  </div>
                  <div className="mt-5 grid gap-2 sm:grid-cols-2">
                    {[
                      ["projects", "List projects"],
                      ["tasks", "List existing tasks"],
                      ["create", "Create test task"],
                      ["verify", "Verify task exists"],
                      ["child", "Create child subtask"],
                      ["status", "Update task status"],
                    ].map(([action, label]) => (
                      <Button
                        key={action}
                        variant={action === "create" ? "primary" : "secondary"}
                        size="md"
                        stretch="full"
                        label={label}
                        loading={
                          busy ===
                          `tool:${action === "projects" ? "plane_list_projects" : action === "tasks" ? "plane_list_work_items" : action === "verify" ? "plane_get_work_item" : action === "status" ? "plane_update_work_item" : "plane_create_work_item"}`
                        }
                        onClick={() => void runDemo(action as Parameters<typeof runDemo>[0])}
                      />
                    ))}
                  </div>
                  {demoResult !== null && (
                    <div className="mt-5">
                      <JsonPanel value={demoResult} />
                    </div>
                  )}
                </div>
                <div>
                  <div className="flex items-center justify-between">
                    <h3 className="text-14 font-semibold">Sanitized request activity</h3>
                    <button
                      type="button"
                      className="text-12 text-accent-primary hover:underline"
                      onClick={() => void loadActivity()}
                    >
                      Refresh
                    </button>
                  </div>
                  <div className="mt-4 max-h-[560px] space-y-2 overflow-y-auto">
                    {events.length === 0 ? (
                      <div className="rounded-md border border-dashed border-subtle p-8 text-center text-13 text-secondary">
                        Run an MCP test to populate the activity stream.
                      </div>
                    ) : (
                      events.map((event) => (
                        <article key={event.id} className="rounded-md border border-subtle p-3">
                          <div className="flex items-center justify-between gap-3">
                            <span className="text-12 font-semibold">{event.label}</span>
                            <time className="text-11 text-tertiary">{formatDate(event.created_at)}</time>
                          </div>
                          <p className="mt-1 text-12 leading-5 text-secondary">{event.summary}</p>
                          <div className="mt-2 font-code text-10 text-tertiary">
                            Request {event.request_id || "portal"} | {event.succeeded ? "success" : "failed"}
                          </div>
                        </article>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </section>
          ) : null}
        </main>
      </div>
    </div>
  );
}
