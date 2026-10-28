import assert from "node:assert/strict";
import test from "node:test";
import type { TIssue } from "@plane/types";
import {
  affectsHierarchicalEstimate,
  displayedEstimate,
  refreshHierarchicalEstimateChain,
  usesHierarchicalEstimate,
} from "./hierarchical-estimate";

const issue = (id: string, parentId: string | null, estimate: number): TIssue =>
  ({
    id,
    parent_id: parentId,
    effective_estimate: estimate,
    rolled_up_estimate: estimate,
    is_rolled_up: parentId === null,
    sub_issues_count: parentId === null ? 1 : 0,
  }) as TIssue;

test("refreshes the edited work item and every estimate ancestor", async () => {
  const issues = new Map([
    ["subtask", issue("subtask", "task", 8)],
    ["task", issue("task", "epic", 11)],
    ["epic", issue("epic", null, 14)],
  ]);
  const applied: string[] = [];

  await refreshHierarchicalEstimateChain({
    issueId: "subtask",
    fetchIssue: async (issueId) => {
      const result = issues.get(issueId);
      if (!result) throw new Error("missing fixture");
      return result;
    },
    applyIssue: (result) => applied.push(result.id),
  });

  assert.deepEqual(applied, ["subtask", "task", "epic"]);
});

test("refreshes the previous parent chain after moving a work item", async () => {
  const issues = new Map([
    ["subtask", issue("subtask", "new-parent", 5)],
    ["old-parent", issue("old-parent", null, 3)],
    ["new-parent", issue("new-parent", null, 5)],
  ]);
  const applied: string[] = [];

  await refreshHierarchicalEstimateChain({
    issueId: "subtask",
    previousParentId: "old-parent",
    fetchIssue: async (issueId) => issues.get(issueId) as TIssue,
    applyIssue: (result) => applied.push(result.id),
  });

  assert.deepEqual(applied, ["subtask", "new-parent", "old-parent"]);
});

test("uses rolled-up values only for work items with descendants", () => {
  const parent = issue("task", null, 13);
  const leaf = { ...issue("subtask", null, 5), is_rolled_up: false, sub_issues_count: 0 };

  assert.equal(usesHierarchicalEstimate(parent), true);
  assert.equal(displayedEstimate(parent), 13);
  assert.equal(usesHierarchicalEstimate(leaf), false);
  assert.equal(displayedEstimate(leaf), null);
  assert.equal(affectsHierarchicalEstimate({ estimate_point: "point-id" }), true);
  assert.equal(affectsHierarchicalEstimate({ name: "Renamed" }), false);
});
