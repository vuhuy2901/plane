/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export type WorkflowTransitionDirection = "forward" | "backward";

export type WorkflowTransitionLike = {
  id?: string;
  name?: string;
  source_key?: string;
  target_key?: string;
  target_state_id?: string | null;
  targetStateId?: string | null;
  direction?: WorkflowTransitionDirection;
  target_state?: {
    id?: string;
    name?: string;
    color?: string;
    group?: string;
    order?: number;
  } | null;
  targetState?: {
    id?: string;
    name?: string;
    color?: string;
    group?: string;
    order?: number;
  } | null;
};

export type WorkflowStateNodeLike = {
  key?: string;
  id?: string;
  state_id?: string | null;
  name?: string;
  is_start?: boolean;
  is_end?: boolean;
  group?: string;
  layout?: {
    position_x?: number;
    position_y?: number;
  };
};

export type WorkflowTransitionSortOptions = {
  currentStateId?: string | null;
  currentSourceKey?: string | null;
  states?: WorkflowStateNodeLike[];
  allTransitions?: {
    source_key?: string;
    target_key?: string;
  }[];
};

const GROUP_ORDER: Record<string, number> = {
  backlog: 0,
  unstarted: 1,
  started: 2,
  completed: 3,
  cancelled: 3,
  triage: 0,
};

/**
 * Sorts workflow transitions based on the directed workflow graph:
 * 1. Forward transitions (progressing towards workflow completion) come first.
 * 2. Backward / reopen transitions follow.
 * 3. Preserves distinct transitions even when they target the same state.
 * 4. Resolves branch ordering and loops safely without infinite recursion.
 */
export function sortWorkflowTransitions<T extends WorkflowTransitionLike>(
  transitions: T[],
  options?: WorkflowTransitionSortOptions
): T[] {
  if (!transitions || transitions.length <= 1) {
    return transitions ? [...transitions] : [];
  }

  const { states, allTransitions, currentStateId, currentSourceKey } = options ?? {};

  // If a full graph is provided, compute BFS depths
  if (states && states.length > 0 && allTransitions && allTransitions.length > 0) {
    const adj = new Map<string, string[]>();
    const revAdj = new Map<string, string[]>();

    for (const s of states) {
      const nodeKey = s.key ?? s.id;
      if (nodeKey) {
        adj.set(nodeKey, []);
        revAdj.set(nodeKey, []);
      }
    }

    for (const edge of allTransitions) {
      if (edge.source_key && edge.target_key) {
        adj.get(edge.source_key)?.push(edge.target_key);
        revAdj.get(edge.target_key)?.push(edge.source_key);
      }
    }

    // Identify start states
    let startKeys = states.filter((s) => s.is_start).map((s) => s.key ?? s.id).filter(Boolean) as string[];
    if (startKeys.length === 0) {
      // Nodes with zero in-degree
      startKeys = states
        .map((s) => s.key ?? s.id)
        .filter((k): k is string => Boolean(k && (!revAdj.get(k) || revAdj.get(k)!.length === 0)));
    }
    if (startKeys.length === 0 && states.length > 0) {
      // Fallback: minimal position_x
      const sortedByX = [...states].sort((a, b) => (a.layout?.position_x ?? 0) - (b.layout?.position_x ?? 0));
      const firstKey = sortedByX[0]?.key ?? sortedByX[0]?.id;
      if (firstKey) startKeys = [firstKey];
    }

    // BFS for forward depth from start states
    const depth = new Map<string, number>();
    const queue: string[] = [];
    for (const sk of startKeys) {
      depth.set(sk, 0);
      queue.push(sk);
    }
    let head = 0;
    while (head < queue.length) {
      const curr = queue[head++];
      const d = depth.get(curr) ?? 0;
      for (const next of adj.get(curr) ?? []) {
        if (!depth.has(next)) {
          depth.set(next, d + 1);
          queue.push(next);
        }
      }
    }

    // Identify end states
    let endKeys = states.filter((s) => s.is_end).map((s) => s.key ?? s.id).filter(Boolean) as string[];
    if (endKeys.length === 0) {
      endKeys = states
        .map((s) => s.key ?? s.id)
        .filter((k): k is string => Boolean(k && (!adj.get(k) || adj.get(k)!.length === 0)));
    }

    // Reverse BFS for distance to end states
    const distToEnd = new Map<string, number>();
    const rQueue: string[] = [];
    for (const ek of endKeys) {
      distToEnd.set(ek, 0);
      rQueue.push(ek);
    }
    let rHead = 0;
    while (rHead < rQueue.length) {
      const curr = rQueue[rHead++];
      const d = distToEnd.get(curr) ?? 0;
      for (const prev of revAdj.get(curr) ?? []) {
        if (!distToEnd.has(prev)) {
          distToEnd.set(prev, d + 1);
          rQueue.push(prev);
        }
      }
    }

    // Determine source node
    const sourceNode =
      states.find((s) => (currentSourceKey && (s.key === currentSourceKey || s.id === currentSourceKey)) ||
        (currentStateId && s.state_id === currentStateId));
    const sourceKey = sourceNode?.key ?? sourceNode?.id ?? currentSourceKey;
    const sourceDepth = sourceKey ? (depth.get(sourceKey) ?? 0) : 0;
    const sourceDistEnd = sourceKey ? (distToEnd.get(sourceKey) ?? 9999) : 9999;
    const sourceX = sourceNode?.layout?.position_x ?? 0;

    return [...transitions].sort((a, b) => {
      const aTargetKey = a.target_key;
      const bTargetKey = b.target_key;
      const aTargetNode = states.find((s) => (aTargetKey && (s.key === aTargetKey || s.id === aTargetKey)) ||
        (a.target_state_id && s.state_id === a.target_state_id) ||
        (a.targetStateId && s.state_id === a.targetStateId));
      const bTargetNode = states.find((s) => (bTargetKey && (s.key === bTargetKey || s.id === bTargetKey)) ||
        (b.target_state_id && s.state_id === b.target_state_id) ||
        (b.targetStateId && s.state_id === b.targetStateId));

      const aKey = aTargetNode?.key ?? aTargetNode?.id ?? aTargetKey ?? "";
      const bKey = bTargetNode?.key ?? bTargetNode?.id ?? bTargetKey ?? "";

      const aDepth = depth.get(aKey) ?? 9999;
      const bDepth = depth.get(bKey) ?? 9999;

      const aDistEnd = distToEnd.get(aKey) ?? 9999;
      const bDistEnd = distToEnd.get(bKey) ?? 9999;

      const aDir = a.direction ?? (aDepth > sourceDepth
        ? "forward"
        : aDepth < sourceDepth
        ? "backward"
        : aDistEnd < sourceDistEnd
        ? "forward"
        : aDistEnd > sourceDistEnd
        ? "backward"
        : (aTargetNode?.layout?.position_x ?? 0) >= sourceX
        ? "forward"
        : "backward");

      const bDir = b.direction ?? (bDepth > sourceDepth
        ? "forward"
        : bDepth < sourceDepth
        ? "backward"
        : bDistEnd < sourceDistEnd
        ? "forward"
        : bDistEnd > sourceDistEnd
        ? "backward"
        : (bTargetNode?.layout?.position_x ?? 0) >= sourceX
        ? "forward"
        : "backward");

      // Group 1: Forward (0) before Backward (1)
      const aDirRank = aDir === "forward" ? 0 : 1;
      const bDirRank = bDir === "forward" ? 0 : 1;
      if (aDirRank !== bDirRank) return aDirRank - bDirRank;

      if (aDirRank === 0) {
        // Forward: nearest next step first
        if (aDepth !== bDepth) return aDepth - bDepth;
        if (aDistEnd !== bDistEnd) return aDistEnd - bDistEnd;
        const aY = aTargetNode?.layout?.position_y ?? 0;
        const bY = bTargetNode?.layout?.position_y ?? 0;
        if (aY !== bY) return aY - bY;
      } else {
        // Backward: nearest previous step first
        if (aDepth !== bDepth) return bDepth - aDepth;
      }

      // Name comparison
      const aName = aTargetNode?.name ?? a.target_state?.name ?? a.targetState?.name ?? a.name ?? "";
      const bName = bTargetNode?.name ?? b.target_state?.name ?? b.targetState?.name ?? b.name ?? "";
      const nameCmp = aName.localeCompare(bName);
      if (nameCmp !== 0) return nameCmp;

      // Stable tie-breaker by id
      return (a.id ?? "").localeCompare(b.id ?? "");
    });
  }

  // Fallback when full graph is not provided: use direction attribute, group rank, and target names
  return [...transitions].sort((a, b) => {
    const aDir = a.direction ?? "forward";
    const bDir = b.direction ?? "forward";
    const aDirRank = aDir === "forward" ? 0 : 1;
    const bDirRank = bDir === "forward" ? 0 : 1;
    if (aDirRank !== bDirRank) return aDirRank - bDirRank;

    const aTarget = a.target_state ?? a.targetState;
    const bTarget = b.target_state ?? b.targetState;

    const aOrder = aTarget?.order ?? GROUP_ORDER[aTarget?.group ?? "unstarted"] ?? 0;
    const bOrder = bTarget?.order ?? GROUP_ORDER[bTarget?.group ?? "unstarted"] ?? 0;

    if (aDirRank === 0) {
      if (aOrder !== bOrder) return aOrder - bOrder;
    } else {
      if (aOrder !== bOrder) return bOrder - aOrder;
    }

    const aName = aTarget?.name ?? a.name ?? "";
    const bName = bTarget?.name ?? b.name ?? "";
    const nameCmp = aName.localeCompare(bName);
    if (nameCmp !== 0) return nameCmp;

    return (a.id ?? "").localeCompare(b.id ?? "");
  });
}
