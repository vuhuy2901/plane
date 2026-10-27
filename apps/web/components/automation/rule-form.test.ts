import assert from "node:assert/strict";
import { test } from "node:test";
import {
  changeConditionField,
  changeConditionOperator,
  editableRule,
  persistRuleDraft,
  prepareRuleDefinition,
  templateDraft,
} from "./rule-form";
import { createBugDraft } from "./rule-presentation";
import type { AutomationResources } from "@/services/automation.service";

test("compatible operator retains a selected project resource ID", () => {
  const condition = { field: "state", operator: "equals", value: "state-a" };
  assert.deepEqual(changeConditionOperator(condition, "not_equals"), {
    field: "state",
    operator: "not_equals",
    value: "state-a",
  });
  assert.deepEqual(changeConditionOperator(condition, "is_empty"), { field: "state", operator: "is_empty" });
  assert.deepEqual(changeConditionField("work_item_type", { work_item_type: ["equals"] }), {
    field: "work_item_type",
    operator: "equals",
  });
});
import type { AutomationRule, AutomationTemplate } from "@/services/automation.service";

test("templates create editable drafts, not enabled saved rules", () => {
  const template: AutomationTemplate = {
    id: "auto_assign_bug",
    name: "Auto Assign Bug",
    category: "assignment",
    requires: ["type_id", "member_id"],
    trigger: "created",
    conditions: [{ field: "work_item_type", operator: "equals", value: "$type_id" }],
    actions: [{ type: "assign_user", mode: "specific_member", member_id: "$member_id", only_if_unassigned: true }],
  };
  const before = structuredClone(template);
  const draft = templateDraft(template);
  assert.equal(draft.conditions[0].value, "");
  assert.equal(draft.actions[0].member_id, "");
  assert.equal("enabled" in draft, false);
  assert.equal("id" in draft, false);
  assert.deepEqual(template, before);
});

test("editing excludes server approval and metadata and does not mutate saved rules", () => {
  const rule: AutomationRule = {
    id: "saved",
    revision: 3,
    enabled: true,
    name: "Rule",
    trigger: "created",
    conditions: [],
    actions: [{ type: "change_priority", priority: "high" }],
  };
  const draft = editableRule(rule);
  draft.actions[0].priority = "urgent";
  assert.equal(rule.actions[0].priority, "high");
  assert.equal("enabled" in draft, false);
  assert.equal("revision" in draft, false);
});

test("parent template keeps target but requires an explicit project state", () => {
  const template: AutomationTemplate = {
    id: "all_subtasks_completed",
    name: "Review parent",
    category: "parent_subtask",
    requires: ["state_id"],
    trigger: "SUBTASK_COMPLETED",
    conditions: [{ field: "ALL_SUBTASKS_COMPLETED", operator: "is_true" }],
    actions: [{ type: "CHANGE_PARENT_STATE", target: "parent", state_id: "$state_id" }],
  };
  const draft = templateDraft(template);
  assert.equal(draft.actions[0].target, "parent");
  assert.equal(draft.actions[0].state_id, "");
  assert.equal(draft.conditions[0].value, undefined);
  assert.equal("enabled" in draft, false);
});

const resources: AutomationResources = {
  types: [
    { id: "task", name: "Task" },
    { id: "bug", name: "Bug" },
  ],
  states: [
    { id: "testing", name: "In Testing" },
    { id: "progress", name: "In Progress" },
  ],
  members: [],
  labels: [],
  work_items: [],
};

test("saving preserves the selected Task transition and Bug creation without mutating the draft", () => {
  const draft = { ...createBugDraft(resources), name: "  Create Bug  " };
  const before = structuredClone(draft);
  const payload = prepareRuleDefinition(draft, resources);
  assert.equal(payload.name, "Create Bug");
  assert.equal(payload.trigger, "state_changed");
  assert.deepEqual(payload.trigger_options, { from_state: "testing", to_state: "progress" });
  assert.equal(payload.conditions[0].value, "task");
  assert.equal(payload.actions[0].type_id, "bug");
  assert.equal(payload.actions[0].parent_mode, "source");
  assert.deepEqual(draft, before);
  assert.notEqual(payload.conditions, draft.conditions);
});

test("saving an explicitly top-level create action never silently switches it to a child", () => {
  const draft = createBugDraft(resources);
  draft.actions[0].parent_mode = "none";
  assert.equal(prepareRuleDefinition(draft, resources).actions[0].parent_mode, "none");
  const legacy = structuredClone(draft);
  delete legacy.actions[0].parent_mode;
  assert.equal(prepareRuleDefinition(legacy, resources).actions[0].parent_mode, undefined);
});

test("invalid required fields and scheduled filters are blocked before requests", () => {
  const draft = createBugDraft(resources);
  assert.throws(() => prepareRuleDefinition({ ...draft, name: " " }, resources), /rule name/);
  assert.throws(
    () => prepareRuleDefinition({ ...draft, conditions: [{ field: "work_item_type", operator: "equals" }] }, resources),
    /If, condition 1/
  );
  assert.throws(
    () =>
      prepareRuleDefinition(
        { ...draft, trigger_options: { filters: [{ field: "priority", operator: "equals" }] } },
        resources
      ),
    /When filters, condition 1/
  );
  assert.throws(
    () =>
      prepareRuleDefinition(
        { ...draft, actions: [{ type: "create_work_item", type_id: "deleted", title: "Bug" }] },
        resources
      ),
    /Then, action 1.*available type/
  );
  assert.throws(
    () =>
      prepareRuleDefinition(
        { ...draft, actions: [{ type: "create_work_item", type_id: "bug", title: " " }] },
        resources
      ),
    /title/
  );
  assert.throws(
    () =>
      prepareRuleDefinition({ ...draft, actions: [{ type: "set_due_date", mode: "relative", days: NaN }] }, resources),
    /whole number/
  );
});

test("save-and-enable uses returned saved ID and revision, then returns enabled rule", async () => {
  const draft = createBugDraft(resources);
  const existing: AutomationRule = { ...draft, id: "existing", revision: 3, enabled: true };
  const saved: AutomationRule = { ...draft, id: "existing", revision: 4, enabled: false };
  const calls: string[] = [];
  const result = await persistRuleDraft({
    draft,
    resources,
    workspace: "workspace",
    project: "project",
    rule: existing,
    enable: true,
    service: {
      save: async (workspace, project, payload, rule) => {
        calls.push("save");
        assert.equal(workspace, "workspace");
        assert.equal(project, "project");
        assert.equal(rule?.revision, 3);
        assert.equal(payload.trigger, "state_changed");
        assert.equal(payload.actions[0].type, "create_work_item");
        return saved;
      },
      setEnabled: async (_workspace, _project, id, enabled) => {
        calls.push("enable");
        assert.equal(id, saved.id);
        assert.equal(enabled, true);
        return { ...saved, enabled: true, revision: 5 };
      },
    },
  });
  assert.deepEqual(calls, ["save", "enable"]);
  assert.equal(result.rule.revision, 5);
  assert.equal(result.rule.enabled, true);
});

test("failed save preserves the unsaved draft and never enables the previous saved rule", async () => {
  const draft = createBugDraft(resources);
  const before = structuredClone(draft);
  let enabled = false;
  await assert.rejects(
    persistRuleDraft({
      draft,
      resources,
      workspace: "w",
      project: "p",
      enable: true,
      service: {
        save: async () => {
          throw new Error("Revision conflict");
        },
        setEnabled: async () => {
          enabled = true;
          throw new Error("Unexpected enable");
        },
      },
    }),
    /Revision conflict/
  );
  assert.equal(enabled, false);
  assert.deepEqual(draft, before);
});

test("enable failure reports a successful disabled save; save-disabled never enables", async () => {
  const draft = createBugDraft(resources);
  const saved: AutomationRule = { ...draft, id: "saved", revision: 4, enabled: false };
  const enableError = new Error("Enabled rule limit reached");
  let enables = 0;
  const service = {
    save: async () => saved,
    setEnabled: async () => {
      enables++;
      throw enableError;
    },
  };
  const result = await persistRuleDraft({ draft, resources, service, workspace: "w", project: "p", enable: true });
  assert.equal(result.rule, saved);
  assert.equal(result.enableError, enableError);
  const disabled = await persistRuleDraft({ draft, resources, service, workspace: "w", project: "p", enable: false });
  assert.equal(disabled.rule.enabled, false);
  assert.equal(enables, 1);
});
