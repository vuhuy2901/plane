import type { Connection, Edge, MarkerType, Node } from "@xyflow/react";
import { getSmoothStepPath, Position } from "@xyflow/react";
import type {
  IState,
  TWorkflowState,
  TWorkflowTransition,
  TWorkflowVersion,
  TWorkItemWorkflowPreview,
} from "@plane/types";

export type WorkflowNode = Node<{ workflowState: TWorkflowState }, "workflowState">;
export type WorkflowEdge = Edge<{ transition: TWorkflowTransition; reciprocal?: boolean }, "directed">;
export type WorkflowGraph = { nodes: WorkflowNode[]; edges: WorkflowEdge[] };

export const WORKFLOW_HANDLE_POSITIONS = [Position.Top, Position.Right, Position.Bottom, Position.Left];
const workflowHandles = new Set<string>(WORKFLOW_HANDLE_POSITIONS);

/** Merge legacy in/out ports by side without changing the stored transition direction. */
export function workflowHandle(handle: string | null | undefined, role: "out" | "in") {
  const side = handle?.replace(/^(out|in)-/, "").split("-")[0];
  return side && workflowHandles.has(side) ? side : role === "out" ? "right" : "left";
}

export function transitionEdge(transition: TWorkflowTransition): WorkflowEdge {
  return {
    id: transition.id ?? crypto.randomUUID(),
    source: transition.source_key,
    target: transition.target_key,
    sourceHandle: workflowHandle(transition.source_handle ?? transition.permissions?.source_handle, "out"),
    targetHandle: workflowHandle(transition.target_handle ?? transition.permissions?.target_handle, "in"),
    type: "directed",
    label: transition.name,
    markerEnd: { type: "arrowclosed" as MarkerType, width: 22, height: 22, color: "#3E63DD" },
    data: { transition },
  };
}

export function hydrateGraph(version: Pick<TWorkflowVersion, "states" | "transitions">): WorkflowGraph {
  return {
    nodes: version.states.map((state) => ({
      id: state.key,
      type: "workflowState",
      position: { x: state.layout.position_x, y: state.layout.position_y },
      data: { workflowState: state },
    })),
    edges: version.transitions.map(transitionEdge),
  };
}

export function workflowPreviewGraph(preview: TWorkItemWorkflowPreview): WorkflowGraph | null {
  if (!preview.workflow) return null;
  const graph = hydrateGraph({
    states: preview.workflow.states,
    transitions: preview.workflow.transitions.map((transition) => ({
      ...transition,
      permissions: {},
      conditions: [],
      validators: [],
      post_actions: [],
    })),
  });
  return {
    nodes: graph.nodes.map((node) => ({
      ...node,
      selected: !!preview.current_state_id && node.data.workflowState.state_id === preview.current_state_id,
    })),
    edges: reciprocalEdges(graph.edges),
  };
}

export function serializeGraph({ nodes, edges }: WorkflowGraph) {
  return {
    states: nodes.map((node) => ({
      ...node.data.workflowState,
      layout: { position_x: node.position.x, position_y: node.position.y },
    })),
    transitions: edges.map((edge) => ({
      ...edge.data!.transition,
      id: edge.id,
      source_key: edge.source,
      target_key: edge.target,
      source_handle: edge.sourceHandle,
      target_handle: edge.targetHandle,
      permissions: {
        ...edge.data!.transition.permissions,
        source_handle: edge.sourceHandle,
        target_handle: edge.targetHandle,
      },
    })),
  };
}

export function canConnect(connection: Connection, edges: WorkflowEdge[]) {
  return Boolean(
    connection.source &&
    connection.target &&
    workflowHandles.has(connection.sourceHandle ?? "") &&
    workflowHandles.has(connection.targetHandle ?? "") &&
    !(connection.source === connection.target && connection.sourceHandle === connection.targetHandle) &&
    !edges.some((edge) => edge.source === connection.source && edge.target === connection.target)
  );
}

/** React Flow supplies the same directed connection for dragging and click-to-connect. */
export function connectWorkflow(connection: Connection, edges: WorkflowEdge[]): WorkflowEdge[] {
  if (!canConnect(connection, edges)) return edges;
  return [
    ...edges,
    transitionEdge({
      id: crypto.randomUUID(),
      source_key: connection.source,
      target_key: connection.target,
      source_handle: connection.sourceHandle,
      target_handle: connection.targetHandle,
      name: "Transition",
      conditions: [],
      validators: [],
      post_actions: [],
      permissions: { roles: [20, 15] },
    }),
  ];
}

export function reciprocalEdges(edges: WorkflowEdge[]): WorkflowEdge[] {
  const pairs = new Set(edges.map((edge) => `${edge.source}:${edge.target}`));
  return edges.map((edge) => ({
    ...edge,
    data: {
      transition: edge.data!.transition,
      reciprocal: edge.source !== edge.target && pairs.has(`${edge.target}:${edge.source}`),
    },
  }));
}

export function duplicateEdges(edges: WorkflowEdge[]): WorkflowEdge[] {
  const counts = new Map<string, number>();
  for (const edge of edges) {
    const pair = `${edge.source}:${edge.target}`;
    counts.set(pair, (counts.get(pair) ?? 0) + 1);
  }
  return edges.filter((edge) => (counts.get(`${edge.source}:${edge.target}`) ?? 0) > 1);
}

type Point = { x: number; y: number };

const sideVectors: Record<string, Point> = {
  right: { x: 1, y: 0 },
  left: { x: -1, y: 0 },
  top: { x: 0, y: -1 },
  bottom: { x: 0, y: 1 },
};

function polylinePath(points: Point[]) {
  let longest = 0;
  let labelX = points[0].x;
  let labelY = points[0].y;
  for (let index = 1; index < points.length; index++) {
    const from = points[index - 1];
    const to = points[index];
    const length = Math.abs(to.x - from.x) + Math.abs(to.y - from.y);
    if (length > longest) {
      longest = length;
      labelX = (from.x + to.x) / 2;
      labelY = (from.y + to.y) / 2;
    }
  }
  return {
    path: points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x},${point.y}`).join(" "),
    labelX,
    labelY,
  };
}

/** Orthogonal lanes keep reverse transitions distinct and preserve their ports. */
export function reciprocalPath(
  sx: number,
  sy: number,
  tx: number,
  ty: number,
  sourceSide = "right",
  targetSide = "left"
) {
  const source = sideVectors[sourceSide];
  const target = sideVectors[targetSide];
  const start = { x: sx + source.x * 30, y: sy + source.y * 30 };
  const end = { x: tx + target.x * 30, y: ty + target.y * 30 };
  const horizontal = source.x !== 0;
  const lane = horizontal ? (sy + ty) / 2 + (tx >= sx ? 65 : -65) : (sx + tx) / 2 + (ty >= sy ? -65 : 65);
  return polylinePath([
    { x: sx, y: sy },
    start,
    horizontal ? { x: start.x, y: lane } : { x: lane, y: start.y },
    horizontal ? { x: end.x, y: lane } : { x: lane, y: end.y },
    end,
    { x: tx, y: ty },
  ]);
}

export function workflowPath({
  reciprocal,
  selfLoop,
  ...params
}: Parameters<typeof getSmoothStepPath>[0] & { reciprocal?: boolean; selfLoop?: boolean }) {
  const { sourceX: sx, sourceY: sy, targetX: tx, targetY: ty } = params;
  const sourceSide = params.sourcePosition ?? Position.Right;
  const targetSide = params.targetPosition ?? Position.Left;
  if (selfLoop) {
    // Route around an outer rectangle, leaving and entering on the chosen sides.
    const left = Math.min(sx, tx) - 80;
    const right = Math.max(sx, tx) + 80;
    const top = Math.min(sy, ty) - 80;
    const bottom = Math.max(sy, ty) + 80;
    const project = (x: number, y: number, side: Position): Point => ({
      x: side === Position.Left ? left : side === Position.Right ? right : x,
      y: side === Position.Top ? top : side === Position.Bottom ? bottom : y,
    });
    const sides = [Position.Top, Position.Right, Position.Bottom, Position.Left];
    const corners = [
      { x: right, y: top },
      { x: right, y: bottom },
      { x: left, y: bottom },
      { x: left, y: top },
    ];
    const points = [{ x: sx, y: sy }, project(sx, sy, sourceSide)];
    for (let side = sides.indexOf(sourceSide); side !== sides.indexOf(targetSide); side = (side + 1) % 4) {
      points.push(corners[side]);
    }
    points.push(project(tx, ty, targetSide), { x: tx, y: ty });
    return polylinePath(points);
  }
  if (reciprocal) return reciprocalPath(sx, sy, tx, ty, sourceSide, targetSide);
  const [path, labelX, labelY] = getSmoothStepPath({ ...params, borderRadius: 0 });
  return { path, labelX, labelY };
}

/** Explicit toolbar action only: stable ordering, positions only, cycles allowed. */
export function autoLayout(nodes: WorkflowNode[]): WorkflowNode[] {
  const sortedNodes = [...nodes];
  // oxlint-disable-next-line unicorn/no-array-sort -- The app targets ES2022; sort only this private copy.
  sortedNodes.sort((a, b) => a.id.localeCompare(b.id));
  return sortedNodes.map((node, index) =>
    Object.assign({}, node, {
      position: { x: 80 + (index % 4) * 300, y: 100 + Math.floor(index / 4) * 200 },
    })
  );
}

export function defaultWorkflow(projectStates: IState[] = []): WorkflowGraph {
  const names = ["Start", "To Do", "In Progress", "Ready for Acceptance", "Done"];
  const states: TWorkflowState[] = names.map((name, index) => {
    const group = index === 4 ? "completed" : index >= 2 ? "started" : "unstarted";
    const existing = projectStates.find(
      (state) => state.name.toLowerCase() === name.toLowerCase() && state.group === group
    );
    return {
      key: crypto.randomUUID(),
      state_id: existing?.id ?? null,
      name,
      description: "",
      color: existing?.color ?? (index === 4 ? "#30A46C" : "#3E63DD"),
      group,
      is_start: index === 0,
      is_end: index === 4,
      layout: { position_x: 50 + index * 300, position_y: 160 },
    };
  });
  const transitions: TWorkflowTransition[] = [
    [0, 1],
    [1, 2],
    [2, 3],
    [3, 4],
    [3, 2],
  ].map(([source, target]) => ({
    id: crypto.randomUUID(),
    source_key: states[source].key,
    target_key: states[target].key,
    name: source === 3 && target === 2 ? "Request changes" : "Transition",
    source_handle: source === 3 && target === 2 ? "bottom" : "right",
    target_handle: source === 3 && target === 2 ? "bottom" : "left",
    permissions: { roles: [20, 15] },
    conditions: [],
    validators: [],
    post_actions: [],
  }));
  return hydrateGraph({ states, transitions });
}
