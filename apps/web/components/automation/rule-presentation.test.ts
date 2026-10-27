import assert from "node:assert/strict";
import { test } from "node:test";
import type { AutomationHistory, AutomationResources, AutomationTestResult } from "@/services/automation.service";
import {
  actionSummary,
  automationError,
  checkExplanation,
  conditionSummary,
  createBugDraft,
  displayValue,
  dryRunSummary,
  historyTriggerMismatch,
  historyCreatedWorkItemIds,
  triggerSummary,
  sourceTransitionHint,
} from "./rule-presentation";

const resources: AutomationResources = {
  types: [
    { id: "task-id", name: "Task" },
    { id: "bug-id", name: "Bug" },
  ],
  states: [
    { id: "testing-id", name: "IN TESTING" },
    { id: "progress-id", name: "In Progress" },
  ],
  members: [{ id: "member-id", name: "Alex" }],
  labels: [],
  work_items: [],
};

test("Bug starter uses actual project IDs for source Task transition and newly created Bug", () => {
  const before = structuredClone(resources);
  const draft = createBugDraft(resources);
  assert.equal(draft.trigger, "state_changed");
  assert.deepEqual(draft.trigger_options, { from_state: "testing-id", to_state: "progress-id" });
  assert.deepEqual(draft.conditions, [{ field: "work_item_type", operator: "equals", value: "task-id" }]);
  assert.equal(draft.actions[0].type, "create_work_item");
  assert.equal(draft.actions[0].type_id, "bug-id");
  assert.equal(draft.actions[0].parent_mode, "source");
  assert.equal("id" in draft, false);
  assert.deepEqual(resources, before);
  assert.match(triggerSummary(draft, resources), /Previous state: IN TESTING.*New state: In Progress/);
  assert.equal(conditionSummary(draft.conditions[0], resources), "Source work item type is Task");
  assert.equal(
    actionSummary(draft.actions[0], resources),
    "Create Bug: Bug: {work_item_title} · Child of source work item (nested)"
  );
});

test("creation placement summaries distinguish child Bugs from existing top-level rules", () => {
  const action = createBugDraft(resources).actions[0];
  assert.match(actionSummary(action, resources), /Child of source work item/);
  assert.match(actionSummary({ ...action, parent_mode: "none" }, resources), /Top-level work item/);
  assert.match(actionSummary({ ...action, parent_mode: undefined }, resources), /Top-level work item/);
});

test("missing Bug or Task never silently selects another project type", () => {
  const draft = createBugDraft({ ...resources, types: [{ id: "story-id", name: "Story" }] });
  assert.equal(draft.actions[0].type_id, undefined);
  assert.equal(draft.conditions[0].value, undefined);
  assert.match(actionSummary(draft.actions[0], resources), /select type/);
});

test("same-group transitions stay allowed in starters; existing group-only filters require an explicit correction", () => {
  const sameGroup = { ...resources, states: resources.states.map((state) => ({ ...state, group: "started" })) };
  const draft = createBugDraft(sameGroup);
  assert.equal(draft.trigger_options?.enter_group_only, undefined);
  assert.match(sourceTransitionHint(draft, sameGroup) ?? "", /including changes within that group/);
  const existing = { ...draft, trigger_options: { ...draft.trigger_options, enter_group_only: true } };
  assert.match(sourceTransitionHint(existing, sameGroup) ?? "", /transition will be skipped/);
  assert.equal(existing.trigger_options.enter_group_only, true);
  const compactStateName = {
    ...resources,
    states: [
      { id: "testing", name: "IN TESTING" },
      { id: "progress", name: "InProgress" },
    ],
  };
  assert.equal(createBugDraft(compactStateName).trigger_options?.to_state, "progress");
});

test("rule action summary exposes an assign-only rule even if its name says create Bug", () => {
  assert.equal(
    actionSummary({ type: "assign_user", mode: "project_lead", only_if_unassigned: true }, resources),
    "Assign source work item to project lead, only if unassigned"
  );
  assert.equal(
    actionSummary({ type: "change_state", target: "parent", state_id: "progress-id" }, resources),
    "Change parent state to In Progress"
  );
});

test("history detects the reported created-vs-updated skip without claiming conditions failed", () => {
  const row: AutomationHistory = {
    id: "execution",
    status: "skipped",
    detail: "Conditions were not met",
    created_at: "2026-10-26T09:33:00Z",
    snapshot: {
      definition: {
        name: "autmation create bug",
        trigger: "created",
        conditions: [],
        actions: [{ type: "assign_user", mode: "project_lead" }],
      },
      work_item: { id: "source", name: "Task", sequence_id: 1 },
      triggers: ["updated", "state_changed"],
    },
  };
  assert.match(
    historyTriggerMismatch(row) ?? "",
    /waits for Work item created, but recorded Work item updated, State changed/
  );
  assert.doesNotMatch(historyTriggerMismatch(row) ?? "", /conditions/);
  assert.equal(historyTriggerMismatch({ ...row, snapshot: { ...row.snapshot, triggers: undefined } }), undefined);
  assert.equal(historyTriggerMismatch({ ...row, snapshot: { ...row.snapshot, triggers: ["created"] } }), undefined);
  assert.equal(
    historyTriggerMismatch({
      ...row,
      snapshot: {
        ...row.snapshot,
        evaluation: { matched: false, trigger: { matched: false, checks: [] }, conditions: [] },
      },
    }),
    undefined
  );
});

test("mismatch explanations resolve resources and show expected and actual source types", () => {
  assert.equal(
    checkExplanation(
      { field: "work_item_type", operator: "equals", expected: "bug-id", actual: "task-id", matched: false },
      resources
    ),
    "Not matched: Source work item type is Bug. Actual: Task. Review this filter or the source work item."
  );
  assert.match(
    checkExplanation(
      { field: "from_state", operator: "equals", expected: "testing-id", actual: "progress-id", matched: false },
      resources
    ),
    /Previous state is IN TESTING. Actual: In Progress/
  );
  assert.match(
    checkExplanation({ field: "assignee", operator: "is_not_empty", actual: [], matched: false }, resources),
    /Assignee is not empty. Actual: Empty/
  );
  assert.equal(displayValue("assignee", ["member-id", "deleted-member"], resources), "Alex, deleted-member");
  assert.equal(displayValue("label", undefined, resources), "Not recorded");
  assert.match(
    checkExplanation(
      { field: "ALL_SUBTASKS_COMPLETED", operator: "is_true", matched: false, reason: "Parent is missing." },
      resources
    ),
    /Parent is missing/
  );
});

test("created-work-item history links belong only to this execution's rule", () => {
  const row: AutomationHistory = {
    id: "execution",
    rule_id: "own-rule",
    status: "success",
    detail: "Created",
    created_at: "2026-10-26T09:33:00Z",
    snapshot: {
      definition: createBugDraft(resources),
      work_item: { id: "source", name: "Task", sequence_id: 1 },
      steps: {
        "own-rule": { first: { created_issue_id: "own-bug" }, retry: { created_issue_id: "own-bug" } },
        "other-rule": { first: { created_issue_id: "someone-elses-bug" } },
      },
    },
  };
  assert.deepEqual(historyCreatedWorkItemIds(row), ["own-bug"]);
  assert.deepEqual(historyCreatedWorkItemIds({ ...row, rule_id: null }), []);
  assert.deepEqual(historyCreatedWorkItemIds({ ...row, rule_id: "missing" }), []);
});

test("dry-run never calls a trigger mismatch a pass even when all zero conditions match", () => {
  const result: AutomationTestResult = {
    valid: true,
    conditions_match: true,
    trigger_match: false,
    action_count: 0,
    writes: 0,
    preview_mode: "recorded_event",
  };
  assert.match(dryRunSummary(result), /does not match/);
  assert.doesNotMatch(dryRunSummary(result), /passed|executed successfully/);
  assert.match(dryRunSummary({ ...result, trigger_match: true, action_count: 1 }), /1 actions prepared; none executed/);
  assert.match(dryRunSummary({ ...result, writes: 1 }), /did not confirm zero writes/);
  assert.match(dryRunSummary({ ...result, valid: false }), /could not validate/);
  assert.match(
    dryRunSummary({
      ...result,
      valid: false,
      trigger_match: true,
      evaluation: { matched: true, trigger: { matched: true, checks: [] }, conditions: [] },
    }),
    /could not validate/
  );
});

test("validation errors retain nested field context without dumping JSON; conflicts explain recovery", () => {
  const error = { response: { data: { actions: [{ type_id: ["Select an available type."] }] } } };
  assert.equal(automationError(error), "actions 1 type id 1: Select an available type.");
  assert.equal(automationError({ response: { data: { detail: "Permission denied." } } }), "Permission denied.");
  assert.match(automationError({ response: { status: 409 } }), /draft is still here.*reopen the latest saved rule/);
  assert.equal(automationError(new Error("Network unavailable")), "Network unavailable");
  assert.equal(automationError(null), "Request failed. Please try again.");
});
