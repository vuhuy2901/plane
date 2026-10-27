import assert from "node:assert/strict";
import { test } from "node:test";
import type { Connection } from "@xyflow/react";
import { Position } from "@xyflow/react";
import {
  autoLayout,
  canConnect,
  connectWorkflow,
  defaultWorkflow,
  duplicateEdges,
  hydrateGraph,
  reciprocalEdges,
  reciprocalPath,
  serializeGraph,
  workflowHandle,
  workflowPath,
  workflowPreviewGraph,
} from "./workflow-graph";

test("default template is opt-in, directed and keeps acceptance in started", () => {
  const graph = defaultWorkflow();
  const serialized = serializeGraph(graph);
  const names = new Map(serialized.states.map((state) => [state.key, state.name]));
  assert.deepEqual(
    serialized.transitions.map((edge) => [names.get(edge.source_key), names.get(edge.target_key)]),
    [
      ["Start", "To Do"],
      ["To Do", "In Progress"],
      ["In Progress", "Ready for Acceptance"],
      ["Ready for Acceptance", "Done"],
      ["Ready for Acceptance", "In Progress"],
    ]
  );
  assert.equal(serialized.states.find((state) => state.name === "Ready for Acceptance")?.group, "started");
  assert.equal(serialized.states.find((state) => state.name === "Done")?.group, "completed");
});

test("task workflow preview highlights the current state and preserves the published graph", () => {
  const saved = serializeGraph(defaultWorkflow());
  saved.states[2].state_id = "current-state";
  const original = structuredClone(saved);
  const preview = workflowPreviewGraph({
    current_state_id: "current-state",
    workflow: { id: "workflow", name: "Task flow", version: 1, ...saved },
  });
  assert.ok(preview);
  assert.deepEqual(
    preview.nodes.filter((node) => node.selected).map((node) => node.id),
    [saved.states[2].key]
  );
  assert.equal(preview.edges.length, saved.transitions.length);
  assert.deepEqual(saved, original);
  assert.equal(workflowPreviewGraph({ current_state_id: null, workflow: null }), null);
});

test("save/reload preserves IDs, ports, direction and coordinates regardless of array order", () => {
  const graph = defaultWorkflow();
  graph.nodes.reverse();
  graph.edges.reverse();
  graph.nodes[0].position = { x: -567.25, y: 89.5 };
  const saved = serializeGraph(graph);
  assert.deepEqual(serializeGraph(hydrateGraph(saved)), saved);
});

test("moving nodes and explicit auto layout cannot change transitions", () => {
  const graph = defaultWorkflow();
  const before = serializeGraph(graph).transitions;
  graph.nodes = graph.nodes.map((node) => ({ ...node, position: { x: -node.position.x, y: node.position.x * 2 } }));
  assert.deepEqual(serializeGraph(graph).transitions, before);
  graph.nodes = autoLayout(graph.nodes);
  assert.deepEqual(serializeGraph(graph).transitions, before);
});

test("every shared port can start or receive a connection without reversing the chosen direction", () => {
  for (const side of ["left", "right", "top", "bottom"]) {
    const connection: Connection = {
      source: "A",
      target: "B",
      sourceHandle: side,
      targetHandle: side,
    };
    assert.equal(canConnect(connection, []), true);
    const reverse = connectWorkflow({ ...connection, source: "B", target: "A" }, []);
    assert.equal(reverse[0].source, "B");
    assert.equal(reverse[0].target, "A");
    assert.equal(canConnect({ ...connection, sourceHandle: "unknown" }, []), false);
    assert.equal(canConnect({ ...connection, targetHandle: null }, []), false);
  }
});

test("duplicate same direction is rejected even with different handles; reverse is independent", () => {
  const graph = defaultWorkflow();
  const edge = graph.edges[0];
  assert.equal(
    canConnect({ source: edge.source, target: edge.target, sourceHandle: "bottom", targetHandle: "top" }, graph.edges),
    false
  );
  assert.equal(
    canConnect({ source: edge.target, target: edge.source, sourceHandle: "left", targetHandle: "right" }, graph.edges),
    true
  );
});

test("connecting needs only React Flow endpoints, supports every port, and survives save/reload", () => {
  for (const sourceSide of ["left", "right", "top", "bottom"]) {
    for (const targetSide of ["left", "right", "top", "bottom"]) {
      const connection: Connection = {
        source: "A",
        target: "B",
        sourceHandle: sourceSide,
        targetHandle: targetSide,
      };
      const edges = connectWorkflow(connection, []);
      assert.equal(edges.length, 1);
      assert.equal(edges[0].source, "A");
      assert.equal(edges[0].target, "B");
      assert.equal(edges[0].sourceHandle, connection.sourceHandle);
      assert.equal(edges[0].targetHandle, connection.targetHandle);
      const saved = serializeGraph({ nodes: [], edges });
      assert.deepEqual(serializeGraph(hydrateGraph(saved)), saved);
      assert.strictEqual(connectWorkflow(connection, edges), edges);
      assert.strictEqual(connectWorkflow({ ...connection, targetHandle: "unknown" }, []).length, 0);
      assert.equal(
        connectWorkflow({ source: "B", target: "A", sourceHandle: "top", targetHandle: "bottom" }, edges).length,
        2
      );
    }
  }
});

test("self transitions can join different shared ports but cannot join a port to itself", () => {
  assert.equal(
    connectWorkflow({ source: "A", target: "A", sourceHandle: "top", targetHandle: "bottom" }, []).length,
    1
  );
  assert.equal(connectWorkflow({ source: "A", target: "A", sourceHandle: "top", targetHandle: "top" }, []).length, 0);
});

test("opposite edges have separate routes with arrow endpoints unchanged", () => {
  const graph = defaultWorkflow();
  const routed = reciprocalEdges(graph.edges);
  assert.equal(routed.filter((edge) => edge.data?.reciprocal).length, 2);
  const forward = reciprocalPath(100, 0, 500, 0);
  const back = reciprocalPath(500, 0, 100, 0);
  assert.notEqual(forward.labelY, back.labelY);
  assert.ok(forward.path.startsWith("M 100,0"));
  assert.ok(forward.path.endsWith("500,0"));
  assert.ok(back.path.startsWith("M 500,0"));
  assert.ok(back.path.endsWith("100,0"));
});

test("all workflow routes use only horizontal/vertical segments and sharp corners on every port", () => {
  const sides = [Position.Left, Position.Right, Position.Top, Position.Bottom];
  for (const sourcePosition of sides) {
    for (const targetPosition of sides) {
      for (const mode of [{}, { reciprocal: true }, { selfLoop: true }]) {
        for (const target of [
          { x: 500, y: 120 },
          { x: -200, y: -150 },
          { x: 100, y: 0 },
        ]) {
          const route = workflowPath({
            sourceX: 100,
            sourceY: 0,
            targetX: target.x,
            targetY: target.y,
            sourcePosition,
            targetPosition,
            ...mode,
          });
          assert.doesNotMatch(route.path, /[CSAHV]/i);
          // React Flow emits zero-radius Q commands with coincident control/end points.
          for (const bend of route.path.matchAll(/Q\s*(-?[\d.]+),(-?[\d.]+)\s+(-?[\d.]+),(-?[\d.]+)/g)) {
            assert.equal(bend[1], bend[3]);
            assert.equal(bend[2], bend[4]);
          }
          const coordinates = route.path.match(/-?\d+(?:\.\d+)?(?:e[+-]?\d+)?/gi)!.map(Number);
          const points = Array.from({ length: coordinates.length / 2 }, (_, index) => ({
            x: coordinates[index * 2],
            y: coordinates[index * 2 + 1],
          }));
          assert.deepEqual(points[0], { x: 100, y: 0 });
          assert.deepEqual(points.at(-1), target);
          assert.ok(Number.isFinite(route.labelX) && Number.isFinite(route.labelY));
          for (let index = 1; index < points.length; index++) {
            const from = points[index - 1];
            const to = points[index];
            assert.ok(from.x === to.x || from.y === to.y, `Diagonal segment in ${route.path}`);
          }
        }
      }
    }
  }
});

test("deleting an edge does not remove nodes or auto-create reverse edges", () => {
  const graph = defaultWorkflow();
  const originalNodes = structuredClone(graph.nodes);
  graph.edges = graph.edges.filter((_, index) => index !== 0);
  assert.equal(serializeGraph(graph).transitions.length, 4);
  assert.deepEqual(graph.nodes, originalNodes);
});

test("legacy handles normalize by role without inferring graph direction", () => {
  const graph = defaultWorkflow();
  const saved = serializeGraph(graph);
  const transition = saved.transitions[0];
  transition.source_handle = "left-1";
  transition.target_handle = "top-3";
  const loaded = hydrateGraph(saved).edges[0];
  assert.equal(loaded.source, transition.source_key);
  assert.equal(loaded.target, transition.target_key);
  assert.equal(loaded.sourceHandle, "left");
  assert.equal(loaded.targetHandle, "top");
  assert.equal(workflowHandle(null, "out"), "right");
  assert.equal(workflowHandle(null, "in"), "left");
});

test("old in/out handles migrate to shared ports while keeping IDs, direction and transition rules", () => {
  const saved = serializeGraph(defaultWorkflow());
  const transition = saved.transitions[0];
  transition.source_handle = "out-top";
  transition.target_handle = "in-right";
  transition.conditions = [{ field: "priority", value: "high" }];
  const migrated = serializeGraph(hydrateGraph(saved));
  assert.deepEqual(migrated.transitions[0], {
    ...transition,
    source_handle: "top",
    target_handle: "right",
    permissions: { ...transition.permissions, source_handle: "top", target_handle: "right" },
  });
  assert.deepEqual(serializeGraph(hydrateGraph(migrated)), migrated);
  for (const side of ["top", "right", "bottom", "left"]) {
    assert.equal(workflowHandle(`out-${side}`, "out"), side);
    assert.equal(workflowHandle(`in-${side}`, "in"), side);
    assert.equal(workflowHandle(side, "out"), side);
    assert.equal(workflowHandle(side, "in"), side);
  }
});

test("legacy duplicates are reported without deleting or reversing any stored edge", () => {
  const graph = defaultWorkflow();
  const duplicate = { ...graph.edges[0], id: crypto.randomUUID() };
  graph.edges.push(duplicate);
  const snapshot = serializeGraph(graph);
  assert.equal(duplicateEdges(graph.edges).length, 2);
  assert.deepEqual(serializeGraph(graph), snapshot);
});
