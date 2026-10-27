import { describe, expect, it } from "vitest";
import { sortWorkflowTransitions } from "./workflow-transition-order";
import type {
  WorkflowStateNodeLike,
  WorkflowTransitionLike,
} from "./workflow-transition-order";

describe("Workflow Transition Graph Ordering", () => {
  it("orders a linear workflow A -> B -> C with forward direction", () => {
    const states: WorkflowStateNodeLike[] = [
      { key: "state-a", name: "To Do", is_start: true, group: "unstarted", layout: { position_x: 100 } },
      { key: "state-b", name: "In Progress", group: "started", layout: { position_x: 200 } },
      { key: "state-c", name: "Done", is_end: true, group: "completed", layout: { position_x: 300 } },
    ];
    const allTransitions = [
      { source_key: "state-a", target_key: "state-b" },
      { source_key: "state-b", target_key: "state-c" },
    ];

    const outgoingFromA: WorkflowTransitionLike[] = [
      { id: "t1", name: "Start Work", source_key: "state-a", target_key: "state-b" },
    ];

    const sortedFromA = sortWorkflowTransitions(outgoingFromA, {
      currentSourceKey: "state-a",
      states,
      allTransitions,
    });
    expect(sortedFromA).toHaveLength(1);
    expect(sortedFromA[0].id).toBe("t1");

    const outgoingFromB: WorkflowTransitionLike[] = [
      { id: "t2", name: "Complete", source_key: "state-b", target_key: "state-c" },
    ];

    const sortedFromB = sortWorkflowTransitions(outgoingFromB, {
      currentSourceKey: "state-b",
      states,
      allTransitions,
    });
    expect(sortedFromB).toHaveLength(1);
    expect(sortedFromB[0].id).toBe("t2");
  });

  it("handles branching workflows (A -> B and A -> C) preserving all branches", () => {
    const states: WorkflowStateNodeLike[] = [
      { key: "state-a", name: "Triage", is_start: true, group: "triage" },
      { key: "state-b", name: "Accepted", group: "unstarted", layout: { position_y: 100 } },
      { key: "state-c", name: "Rejected", group: "cancelled", layout: { position_y: 200 } },
    ];
    const allTransitions = [
      { source_key: "state-a", target_key: "state-b" },
      { source_key: "state-a", target_key: "state-c" },
    ];

    const transitions: WorkflowTransitionLike[] = [
      { id: "t-reject", name: "Reject Ticket", source_key: "state-a", target_key: "state-c" },
      { id: "t-accept", name: "Accept Ticket", source_key: "state-a", target_key: "state-b" },
    ];

    const sorted = sortWorkflowTransitions(transitions, {
      currentSourceKey: "state-a",
      states,
      allTransitions,
    });

    expect(sorted).toHaveLength(2);
    expect(sorted.map((t) => t.id)).toEqual(["t-accept", "t-reject"]);
  });

  it("prioritizes forward transitions over backward transitions (C -> B vs C -> Done)", () => {
    const states: WorkflowStateNodeLike[] = [
      { key: "state-a", name: "Ready for Review", is_start: true, group: "unstarted" },
      { key: "state-b", name: "In Review", group: "started" },
      { key: "state-c", name: "Needs Changes", group: "unstarted" },
      { key: "state-d", name: "Done", is_end: true, group: "completed" },
    ];
    const allTransitions = [
      { source_key: "state-a", target_key: "state-b" },
      { source_key: "state-b", target_key: "state-c" },
      { source_key: "state-b", target_key: "state-d" },
      { source_key: "state-c", target_key: "state-b" },
    ];

    // From In Review (state-b), there is a forward transition to Done (state-d)
    // and a backward / return transition to Needs Changes (state-c)
    const transitions: WorkflowTransitionLike[] = [
      { id: "t-changes", name: "Request Changes", source_key: "state-b", target_key: "state-c" },
      { id: "t-approve", name: "Approve Directly", source_key: "state-b", target_key: "state-d" },
    ];

    const sorted = sortWorkflowTransitions(transitions, {
      currentSourceKey: "state-b",
      states,
      allTransitions,
    });

    expect(sorted[0].id).toBe("t-approve"); // Forward transition first
    expect(sorted[1].id).toBe("t-changes"); // Backward transition second
  });

  it("handles workflows with loops/cycles safely without infinite loops", () => {
    const states: WorkflowStateNodeLike[] = [
      { key: "node-1", name: "Draft", is_start: true },
      { key: "node-2", name: "Review" },
      { key: "node-3", name: "QA" },
    ];
    const allTransitions = [
      { source_key: "node-1", target_key: "node-2" },
      { source_key: "node-2", target_key: "node-3" },
      { source_key: "node-3", target_key: "node-1" }, // cycle back to start
    ];

    const transitionsFromQA: WorkflowTransitionLike[] = [
      { id: "loop-restart", name: "Reject to Draft", source_key: "node-3", target_key: "node-1" },
    ];

    const sorted = sortWorkflowTransitions(transitionsFromQA, {
      currentSourceKey: "node-3",
      states,
      allTransitions,
    });
    expect(sorted).toHaveLength(1);
    expect(sorted[0].id).toBe("loop-restart");
  });

  it("preserves separate transitions targeting the exact same state", () => {
    const states: WorkflowStateNodeLike[] = [
      { key: "s1", name: "In Progress", is_start: true },
      { key: "s2", name: "Done", is_end: true },
    ];
    const allTransitions = [
      { source_key: "s1", target_key: "s2" },
    ];

    const transitions: WorkflowTransitionLike[] = [
      { id: "t-normal", name: "Submit for Approval", source_key: "s1", target_key: "s2" },
      { id: "t-fast", name: "Fast-track Approval", source_key: "s1", target_key: "s2" },
    ];

    const sorted = sortWorkflowTransitions(transitions, {
      currentSourceKey: "s1",
      states,
      allTransitions,
    });

    expect(sorted).toHaveLength(2);
    expect(sorted.map((t) => t.id)).toEqual(["t-fast", "t-normal"]);
  });

  it("sorts correctly even when API returns transitions in arbitrary/backward order", () => {
    const transitions: WorkflowTransitionLike[] = [
      {
        id: "t-back",
        name: "Reopen",
        direction: "backward",
        target_state: { name: "Backlog", order: 0, group: "backlog" },
      },
      {
        id: "t-forward-2",
        name: "Archive",
        direction: "forward",
        target_state: { name: "Done", order: 20, group: "completed" },
      },
      {
        id: "t-forward-1",
        name: "Start Review",
        direction: "forward",
        target_state: { name: "Review", order: 10, group: "started" },
      },
    ];

    const sorted = sortWorkflowTransitions(transitions);

    // Forward transitions come first (Review, Done), then Backward (Reopen)
    expect(sorted.map((t) => t.id)).toEqual(["t-forward-1", "t-forward-2", "t-back"]);
  });

  it("handles states with no outgoing transitions gracefully", () => {
    const sorted = sortWorkflowTransitions([]);
    expect(sorted).toEqual([]);
  });
});
