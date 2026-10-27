import { useCallback, useEffect, useRef, useState } from "react";
import { observer } from "mobx-react";
import {
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  BaseEdge,
  ConnectionLineType,
  ConnectionMode,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  useUpdateNodeInternals,
} from "@xyflow/react";
import type { Connection, EdgeChange, EdgeProps, NodeChange, NodeProps } from "@xyflow/react";
import { Button } from "@makeplane/propel/components/button";
import type { IState, TWorkflowDraftToken, TWorkflowState, TWorkflowTransition } from "@plane/types";
import { useWorkflow } from "@/hooks/store/use-workflow";
import { useProjectState } from "@/hooks/store/use-project-state";
import {
  autoLayout,
  canConnect,
  defaultWorkflow,
  duplicateEdges,
  hydrateGraph,
  reciprocalEdges,
  workflowPath,
  serializeGraph,
  connectWorkflow,
  WORKFLOW_HANDLE_POSITIONS,
} from "./workflow-graph";
import type { WorkflowNode, WorkflowEdge, WorkflowGraph } from "./workflow-graph";
// oxlint-disable-next-line import/no-unassigned-import -- React Flow ships its canvas primitives as global CSS.
import "@xyflow/react/dist/style.css";

type Snapshot = WorkflowGraph;

const STATE_GROUPS = ["backlog", "unstarted", "started", "completed", "cancelled"] as const;

const handleBaseClass = "cursor-crosshair! rounded-full! hover:ring-4 hover:ring-blue-500/25";

function WorkflowStateNode({ id, data, selected, isConnectable }: NodeProps<WorkflowNode>) {
  const state = data.workflowState;
  const updateNodeInternals = useUpdateNodeInternals();
  useEffect(() => {
    updateNodeInternals(id);
  }, [id, updateNodeInternals]);
  return (
    <div
      className={`group shadow-sm relative min-w-48 rounded-lg border-2 bg-surface-1 px-4 py-3 transition-all ${
        selected ? "ring-blue-500/20 ring-2" : "hover:border-secondary border-subtle"
      }`}
      style={selected ? { borderColor: "#3E63DD" } : undefined}
    >
      {WORKFLOW_HANDLE_POSITIONS.map((position) => (
        <Handle
          key={position}
          id={position}
          type="source"
          position={position}
          isConnectable={isConnectable}
          isConnectableStart
          isConnectableEnd
          style={{
            width: 14,
            height: 14,
            border: "2px solid #ffffff",
            backgroundColor: "#3E63DD",
            zIndex: 10,
          }}
          className={isConnectable ? handleBaseClass : "rounded-full!"}
          title={isConnectable ? "Drag to another handle or click two handles to connect" : "Workflow connection"}
        />
      ))}
      <div className="flex items-center gap-2">
        <span className="shadow-xs size-3.5 shrink-0 rounded-full" style={{ backgroundColor: state.color }} />
        <span className="text-sm truncate font-medium">{state.name}</span>
      </div>
      <div className="mt-1.5 flex items-center justify-between text-[10px] tracking-wide text-tertiary uppercase">
        <span>{state.group}</span>
        <span>
          {state.is_start && "Start"}
          {state.is_start && state.is_end && " · "}
          {state.is_end && "End"}
        </span>
      </div>
    </div>
  );
}

export const workflowNodeTypes = { workflowState: WorkflowStateNode };

function DirectedWorkflowEdge(props: EdgeProps<WorkflowEdge>) {
  const lane = workflowPath({ ...props, reciprocal: props.data?.reciprocal, selfLoop: props.source === props.target });
  return (
    <BaseEdge
      id={props.id}
      path={lane.path}
      markerEnd={props.markerEnd}
      style={{ stroke: props.selected ? "#E5484D" : "#3E63DD", strokeWidth: props.selected ? 3 : 2 }}
      label={props.label}
      labelX={lane.labelX}
      labelY={lane.labelY}
      labelStyle={{ fill: "#334155", fontSize: 11 }}
      labelBgStyle={{ fill: "#ffffff" }}
    />
  );
}

export const workflowEdgeTypes = { directed: DirectedWorkflowEdge };

function errorMessage(error: unknown) {
  const response = (error as { response?: { status?: number; data?: unknown } })?.response;
  if (response?.status === 409)
    return "This draft was updated in another session. Your changes are preserved. Reload the latest draft before saving.";
  return response?.data ? JSON.stringify(response.data) : error instanceof Error ? error.message : "Request failed";
}

function safeJson(value: string, fallback: Record<string, unknown>[]) {
  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed) ? (parsed as Record<string, unknown>[]) : fallback;
  } catch {
    return fallback;
  }
}

type Props = { workspaceSlug: string; projectId: string; workflowId: string };

const WorkflowDesignerInner = observer(function WorkflowDesignerInner({ workspaceSlug, projectId, workflowId }: Props) {
  const { validation, versions, fetchDraft, saveDraft, validateDraft, publishDraft, fetchVersions, rollbackVersion } =
    useWorkflow();
  const [nodes, setNodes] = useState<WorkflowNode[]>([]);
  const [edges, setEdges] = useState<WorkflowEdge[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState("");
  const [showVersions, setShowVersions] = useState(false);
  const [busy, setBusy] = useState(true);
  const busyRef = useRef(true);
  const token = useRef<TWorkflowDraftToken | null>(null);
  const loadGeneration = useRef(0);
  const { fitView } = useReactFlow<WorkflowNode, WorkflowEdge>();
  const { getProjectStateIds, getStateById, fetchProjectStates } = useProjectState();
  const history = useRef<Snapshot[]>([]);
  const future = useRef<Snapshot[]>([]);

  const loadDraft = useCallback(async () => {
    const generation = ++loadGeneration.current;
    busyRef.current = true;
    setBusy(true);
    try {
      const loaded = await fetchDraft(workspaceSlug, projectId, workflowId);
      if (generation !== loadGeneration.current) return;
      const graph = hydrateGraph(loaded);
      token.current = { draft_id: loaded.id, expected_revision: loaded.revision };
      setNodes(graph.nodes);
      setEdges(graph.edges);
      history.current = [];
      future.current = [];
      setSelectedNodeId(null);
      setSelectedEdgeId(null);
      setDirty(false);
    } catch (error) {
      if (generation === loadGeneration.current) setMessage(errorMessage(error));
    } finally {
      if (generation === loadGeneration.current) {
        busyRef.current = false;
        setBusy(false);
      }
    }
  }, [fetchDraft, projectId, workflowId, workspaceSlug]);

  useEffect(() => {
    token.current = null;
    void loadDraft();
    return () => {
      loadGeneration.current += 1;
    };
  }, [loadDraft]);

  useEffect(() => {
    if (!getProjectStateIds(projectId)) void fetchProjectStates(workspaceSlug, projectId);
  }, [fetchProjectStates, getProjectStateIds, projectId, workspaceSlug]);

  const remember = useCallback(() => {
    if (busyRef.current) return;
    history.current.push({ nodes: structuredClone(nodes), edges: structuredClone(edges) });
    if (history.current.length > 50) history.current.shift();
    future.current = [];
  }, [edges, nodes]);

  const onNodesChange = useCallback((changes: NodeChange<WorkflowNode>[]) => {
    if (busyRef.current) changes = changes.filter((change) => change.type === "select" || change.type === "dimensions");
    setNodes((current) => applyNodeChanges(changes, current));
    if (changes.some((change) => change.type !== "select" && change.type !== "dimensions")) setDirty(true);
  }, []);
  const onEdgesChange = useCallback((changes: EdgeChange<WorkflowEdge>[]) => {
    if (busyRef.current) changes = changes.filter((change) => change.type === "select");
    setEdges((current) => applyEdgeChanges(changes, current));
    if (changes.some((change) => change.type !== "select")) setDirty(true);
  }, []);
  const onConnect = useCallback(
    (connection: Connection) => {
      if (busyRef.current || !canConnect(connection, edges)) return;
      remember();
      setEdges((current) => connectWorkflow(connection, current));
      setDirty(true);
    },
    [remember, edges]
  );

  const addState = () => {
    if (busyRef.current) return;
    remember();
    const key = crypto.randomUUID();
    const state: TWorkflowState = {
      key,
      state_id: null,
      name: `State ${nodes.length + 1}`,
      description: "",
      color: "#60646C",
      group: "unstarted",
      is_start: nodes.length === 0,
      is_end: false,
      layout: { position_x: 80 + nodes.length * 40, position_y: 100 + nodes.length * 30 },
    };
    setNodes((current) => [
      ...current,
      {
        id: key,
        type: "workflowState",
        position: { x: state.layout.position_x, y: state.layout.position_y },
        data: { workflowState: state },
      },
    ]);
    setSelectedNodeId(key);
    setSelectedEdgeId(null);
    setDirty(true);
  };

  const updateSelectedState = (patch: Partial<TWorkflowState>) => {
    if (busyRef.current) return;
    setNodes((current) =>
      current.map((node) =>
        node.id === selectedNodeId
          ? { ...node, data: { workflowState: { ...node.data.workflowState, ...patch } } }
          : node
      )
    );
    setDirty(true);
  };
  const updateSelectedTransition = (patch: Partial<TWorkflowTransition>) => {
    if (busyRef.current) return;
    setEdges((current) =>
      current.map((edge) => {
        if (edge.id !== selectedEdgeId || !edge.data) return edge;
        const transition = { ...edge.data.transition, ...patch };
        return { ...edge, label: transition.name, data: { transition } };
      })
    );
    setDirty(true);
  };

  const undo = () => {
    if (busyRef.current) return;
    const previous = history.current.pop();
    if (!previous) return;
    future.current.push({ nodes: structuredClone(nodes), edges: structuredClone(edges) });
    setNodes(previous.nodes);
    setEdges(previous.edges);
    setDirty(true);
  };
  const redo = () => {
    if (busyRef.current) return;
    const next = future.current.pop();
    if (!next) return;
    history.current.push({ nodes: structuredClone(nodes), edges: structuredClone(edges) });
    setNodes(next.nodes);
    setEdges(next.edges);
    setDirty(true);
  };

  // Hold an editor lock across the entire request, including save + publish.
  // The revision is local to the loaded draft, never borrowed from the shared store.
  const persist = async () => {
    if (!token.current) throw new Error("Load a draft before saving.");
    const payload = serializeGraph({ nodes, edges });
    const saved = await saveDraft(
      workspaceSlug,
      projectId,
      workflowId,
      payload.states,
      payload.transitions,
      token.current
    );
    token.current = { draft_id: saved.id, expected_revision: saved.revision };
    setDirty(false);
    setMessage("Draft saved");
  };

  const runExclusive = async (operation: () => Promise<void>) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    try {
      await operation();
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const handleSave = () => runExclusive(persist);

  const handleValidate = () =>
    runExclusive(async () => {
      if (dirty) await persist();
      await validateDraft(workspaceSlug, projectId, workflowId);
    });

  const handlePublish = () =>
    runExclusive(async () => {
      if (dirty) await persist();
      if (!token.current) throw new Error("Load a draft before publishing.");
      const result = await validateDraft(workspaceSlug, projectId, workflowId);
      if (!result.valid) {
        setMessage(result.errors[0]?.message ?? "Fix validation errors before publishing");
        return;
      }
      await publishDraft(workspaceSlug, projectId, workflowId, token.current);
      setMessage("Workflow published successfully!");
      await loadDraft();
    });

  const toggleVersions = async () => {
    const next = !showVersions;
    setShowVersions(next);
    if (next) await fetchVersions(workspaceSlug, projectId, workflowId);
  };

  const handleRollback = (versionId: string) =>
    runExclusive(async () => {
      if (dirty) {
        setMessage("Save or publish the current draft before restoring a version");
        return;
      }
      if (!window.confirm("Restore this published version into a new editable draft?")) return;
      await rollbackVersion(workspaceSlug, projectId, workflowId, versionId);
      await loadDraft();
      setShowVersions(false);
      setMessage("Published version restored as a draft");
    });

  const selectedNode = nodes.find((node) => node.id === selectedNodeId)?.data.workflowState;
  const selectedEdge = edges.find((edge) => edge.id === selectedEdgeId)?.data?.transition;
  const duplicates = duplicateEdges(edges);
  const projectStates = (getProjectStateIds(projectId) ?? [])
    .map((stateId) => getStateById(stateId))
    .filter((state): state is IState => !!state);
  const applyTemplate = () => {
    if (
      busyRef.current ||
      (nodes.length > 0 &&
        !window.confirm(
          "Replace this draft with the default template? Published workflows and work items will not change."
        ))
    )
      return;
    remember();
    const graph = defaultWorkflow(projectStates);
    setNodes(graph.nodes);
    setEdges(graph.edges);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setDirty(true);
    setMessage("Template applied to draft only");
  };
  const layoutGraph = () => {
    if (busyRef.current) return;
    remember();
    setNodes(autoLayout(nodes));
    setDirty(true);
    requestAnimationFrame(() => void fitView({ duration: 300 }));
  };
  const deleteSelected = () => {
    if (busyRef.current || !window.confirm("Delete this selection from the draft?")) return;
    remember();
    if (selectedEdgeId) setEdges((current) => current.filter((edge) => edge.id !== selectedEdgeId));
    else if (selectedNodeId) {
      setNodes((current) => current.filter((node) => node.id !== selectedNodeId));
      setEdges((current) => current.filter((edge) => edge.source !== selectedNodeId && edge.target !== selectedNodeId));
    }
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setDirty(true);
  };
  const panelInput = "h-8 w-full rounded border border-subtle bg-surface-1 px-2 text-sm";

  return (
    <div className="flex h-[calc(100vh-9rem)] min-h-[620px] flex-col overflow-hidden rounded-lg border border-subtle bg-surface-1">
      <div className="flex min-h-12 shrink-0 flex-wrap items-center justify-between gap-2 border-b border-subtle px-3 py-2">
        <fieldset disabled={busy} className="flex items-center gap-2">
          <Button variant="secondary" size="sm" stretch="auto" label="Add state" onClick={addState} />
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label="Undo"
            disabled={!history.current.length}
            onClick={undo}
          />
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label="Redo"
            disabled={!future.current.length}
            onClick={redo}
          />
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label="Versions"
            onClick={() => void toggleVersions().catch((error: unknown) => setMessage(errorMessage(error)))}
          />
          <Button variant="secondary" size="sm" stretch="auto" label="Template" onClick={applyTemplate} />
          <Button variant="secondary" size="sm" stretch="auto" label="Auto Layout" onClick={layoutGraph} />
          {dirty && <span className="text-xs text-warning-primary">Unsaved changes</span>}
        </fieldset>
        <fieldset disabled={busy} className="flex gap-2">
          <Button variant="secondary" size="sm" stretch="auto" label="Validate" onClick={() => void handleValidate()} />
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label={busy ? "Processing…" : "Save draft"}
            onClick={() => void handleSave()}
          />
          <Button variant="primary" size="sm" stretch="auto" label="Publish" onClick={() => void handlePublish()} />
        </fieldset>
      </div>
      {message && (
        <div role="status" aria-live="polite" className="text-xs border-b border-subtle px-3 py-2 text-secondary">
          {message}
        </div>
      )}
      <div className="text-xs flex items-center justify-between gap-3 border-b border-subtle px-3 py-2 text-secondary">
        <div className="flex flex-col gap-1">
          <span>
            All handles support incoming and outgoing connections. Drag between two handles or click them in order; the
            arrow points from the first handle to the second.
          </span>
          <span>
            Ctrl + scroll to zoom at the cursor (Mac: Cmd + scroll). Scroll or drag the background to pan. Use the fit
            view button in the bottom corner to see the entire workflow.
          </span>
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            if (!dirty || window.confirm("Discard unsaved changes and reload?")) void loadDraft();
          }}
        >
          Reload draft
        </button>
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1">
          <ReactFlow<WorkflowNode, WorkflowEdge>
            nodes={nodes}
            edges={reciprocalEdges(edges)}
            nodeTypes={workflowNodeTypes}
            edgeTypes={workflowEdgeTypes}
            nodesDraggable={!busy}
            nodesConnectable={!busy}
            edgesReconnectable={false}
            connectionMode={ConnectionMode.Loose}
            connectOnClick
            connectionRadius={28}
            zoomActivationKeyCode={["Control", "Meta"]}
            zoomOnScroll={false}
            zoomOnPinch
            panOnScroll
            minZoom={0.2}
            maxZoom={3}
            connectionLineType={ConnectionLineType.Step}
            connectionLineStyle={{ stroke: "#3E63DD", strokeWidth: 2 }}
            defaultEdgeOptions={{
              type: "directed",
              markerEnd: { type: MarkerType.ArrowClosed },
            }}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            isValidConnection={(connection) => canConnect(connection as Connection, edges)}
            onNodeClick={(_, node) => {
              setSelectedNodeId(node.id);
              setSelectedEdgeId(null);
            }}
            onEdgeClick={(_, edge) => {
              setSelectedEdgeId(edge.id);
              setSelectedNodeId(null);
            }}
            onNodeDragStart={remember}
            onBeforeDelete={async ({ nodes: deletingNodes, edges: deletingEdges }) => {
              if (busyRef.current) return false;
              const confirmed = window.confirm(
                `Delete ${deletingNodes.length} state(s) and ${deletingEdges.length} transition(s)? This only changes the draft.`
              );
              if (confirmed) remember();
              return confirmed;
            }}
            fitView
            deleteKeyCode={["Backspace", "Delete"]}
          >
            <Background />
            <MiniMap pannable zoomable />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
        <aside className="w-80 shrink-0 overflow-y-auto border-l border-subtle bg-surface-2 p-4">
          <fieldset disabled={busy} className="min-w-0">
            {duplicates.length > 0 && (
              <div className="text-xs mb-4 rounded border border-subtle p-3">
                <div className="font-medium text-warning-primary">This workflow contains duplicate transitions</div>
                <p className="my-2 text-secondary">
                  Select each transition to review its ID, permissions and conditions. Keep only one transition per
                  direction before saving. Published history is preserved.
                </p>
                {duplicates.map((edge) => (
                  <button
                    key={edge.id}
                    type="button"
                    className="my-1 block w-full rounded border border-subtle px-2 py-1 text-left"
                    onClick={() => {
                      setSelectedEdgeId(edge.id);
                      setSelectedNodeId(null);
                    }}
                  >
                    {nodes.find((node) => node.id === edge.source)?.data.workflowState.name} →{" "}
                    {nodes.find((node) => node.id === edge.target)?.data.workflowState.name}
                    <span className="font-mono block break-all text-tertiary">{edge.id}</span>
                  </button>
                ))}
              </div>
            )}
            {showVersions && (
              <div className="mb-5 grid gap-2 border-b border-subtle pb-4">
                <div className="font-medium">Published versions</div>
                {!versions.length && <div className="text-xs text-secondary">No published versions yet.</div>}
                {versions.map((version) => (
                  <div key={version.id} className="flex items-center justify-between rounded border border-subtle p-2">
                    <div>
                      <div className="text-sm">Version {version.version}</div>
                      <div className="text-xs text-secondary">
                        {version.published_at ? new Date(version.published_at).toLocaleString() : "Published"}
                      </div>
                    </div>
                    <Button
                      variant="secondary"
                      size="sm"
                      stretch="auto"
                      label="Restore"
                      onClick={() => void handleRollback(version.id)}
                    />
                  </div>
                ))}
              </div>
            )}
            {!selectedNode && !selectedEdge && (
              <div className="text-sm text-secondary">Select a state or transition to configure it.</div>
            )}
            {selectedNode && (
              <div key={selectedNode.key} className="grid gap-3">
                <div className="font-medium">State configuration</div>
                <div className="text-xs text-secondary">Project state</div>
                <select
                  className={panelInput}
                  value={selectedNode.state_id ?? ""}
                  onFocus={remember}
                  onChange={(event) => {
                    const state = projectStates.find((item) => item.id === event.target.value);
                    if (!state) {
                      updateSelectedState({ state_id: null });
                      return;
                    }
                    updateSelectedState({
                      state_id: state.id,
                      name: state.name,
                      description: state.description,
                      color: state.color,
                      group: state.group,
                    });
                  }}
                >
                  <option value="">Create a new project state</option>
                  {projectStates.map((state) => (
                    <option key={state.id} value={state.id}>
                      {state.name}
                    </option>
                  ))}
                </select>
                <div className="text-xs text-tertiary">
                  Choose an existing state such as Backlog to include its current work items without changing their
                  state.
                </div>
                <div className="text-xs text-secondary">Name</div>
                <input
                  className={panelInput}
                  value={selectedNode.name}
                  onFocus={remember}
                  onChange={(event) => updateSelectedState({ name: event.target.value })}
                />
                <div className="text-xs text-secondary">Description</div>
                <textarea
                  className="text-sm min-h-20 rounded border border-subtle bg-surface-1 p-2"
                  value={selectedNode.description}
                  onFocus={remember}
                  onChange={(event) => updateSelectedState({ description: event.target.value })}
                />
                <div className="text-xs text-secondary">Color</div>
                <input
                  type="color"
                  className="h-9 w-full"
                  value={selectedNode.color}
                  onFocus={remember}
                  onChange={(event) => updateSelectedState({ color: event.target.value })}
                />
                <div className="text-xs text-secondary">Plane group</div>
                <select
                  className={panelInput}
                  value={selectedNode.group}
                  onFocus={remember}
                  onChange={(event) => updateSelectedState({ group: event.target.value as TWorkflowState["group"] })}
                >
                  {STATE_GROUPS.map((group) => (
                    <option key={group} value={group}>
                      {group}
                    </option>
                  ))}
                </select>
                <label className="text-sm flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selectedNode.is_start}
                    onFocus={remember}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      setNodes((current) =>
                        current.map((node) => ({
                          ...node,
                          data: {
                            workflowState: {
                              ...node.data.workflowState,
                              is_start:
                                node.id === selectedNodeId
                                  ? checked
                                  : checked
                                    ? false
                                    : node.data.workflowState.is_start,
                            },
                          },
                        }))
                      );
                      setDirty(true);
                    }}
                  />
                  Start state
                </label>
                <label className="text-sm flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selectedNode.is_end}
                    onFocus={remember}
                    onChange={(event) => updateSelectedState({ is_end: event.target.checked })}
                  />
                  End state
                </label>
              </div>
            )}
            {selectedEdge && (
              <div key={selectedEdgeId} className="grid gap-3">
                <div className="font-medium">Transition configuration</div>
                <div className="text-sm rounded border border-subtle p-2">
                  {nodes.find((node) => node.id === selectedEdge.source_key)?.data.workflowState.name} →{" "}
                  {nodes.find((node) => node.id === selectedEdge.target_key)?.data.workflowState.name}
                  <div className="font-mono text-xs mt-1 break-all text-tertiary">
                    ID: {selectedEdge.id ?? selectedEdgeId}
                  </div>
                </div>
                <div className="text-xs text-secondary">Name</div>
                <input
                  className={panelInput}
                  value={selectedEdge.name}
                  onFocus={remember}
                  onChange={(event) => updateSelectedTransition({ name: event.target.value })}
                />
                <div className="text-xs text-secondary">Allowed project roles</div>
                <div className="text-sm grid gap-1">
                  {[
                    [20, "Admin"],
                    [15, "Member"],
                    [5, "Guest"],
                  ].map(([role, label]) => {
                    const numericRole = Number(role);
                    const roles = selectedEdge.permissions.roles ?? [];
                    return (
                      <label key={numericRole} className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={roles.includes(numericRole)}
                          onFocus={remember}
                          onChange={(event) =>
                            updateSelectedTransition({
                              permissions: {
                                ...selectedEdge.permissions,
                                roles: event.target.checked
                                  ? [...roles, numericRole]
                                  : roles.filter((value) => value !== numericRole),
                              },
                            })
                          }
                        />
                        {label}
                      </label>
                    );
                  })}
                </div>
                <div className="text-xs text-secondary">Conditions (JSON array)</div>
                <textarea
                  className="font-mono text-xs min-h-24 rounded border border-subtle bg-surface-1 p-2"
                  defaultValue={JSON.stringify(selectedEdge.conditions, null, 2)}
                  onFocus={remember}
                  onBlur={(event) =>
                    updateSelectedTransition({ conditions: safeJson(event.target.value, selectedEdge.conditions) })
                  }
                />
                <div className="text-xs text-secondary">Validators (JSON array)</div>
                <textarea
                  className="font-mono text-xs min-h-24 rounded border border-subtle bg-surface-1 p-2"
                  defaultValue={JSON.stringify(selectedEdge.validators, null, 2)}
                  onFocus={remember}
                  onBlur={(event) =>
                    updateSelectedTransition({ validators: safeJson(event.target.value, selectedEdge.validators) })
                  }
                />
              </div>
            )}
            {(selectedNode || selectedEdge) && (
              <Button
                variant="secondary"
                size="sm"
                stretch="auto"
                label={selectedEdge ? "Delete transition" : "Delete state"}
                onClick={deleteSelected}
              />
            )}
          </fieldset>
          {validation && (
            <div className="text-xs mt-6 border-t border-subtle pt-4">
              <div className={validation.valid ? "text-success-primary" : "text-danger-primary"}>
                {validation.valid ? "Workflow is valid" : `${validation.errors.length} validation error(s)`}
              </div>
              {[...validation.errors, ...validation.warnings].map((item) => (
                <div
                  key={`${item.code}-${item.state_id ?? item.transition_id ?? item.message}`}
                  className="mt-2 text-secondary"
                >
                  {item.message}
                </div>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
});

export function WorkflowDesigner(props: Props) {
  return (
    <ReactFlowProvider>
      <WorkflowDesignerInner key={`${props.projectId}:${props.workflowId}`} {...props} />
    </ReactFlowProvider>
  );
}
