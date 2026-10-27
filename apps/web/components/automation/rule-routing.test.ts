import assert from "node:assert/strict";
import { test } from "node:test";
import type {
  AutomationResources,
  AutomationRule,
  AutomationService,
  AutomationTemplate,
} from "@/services/automation.service";
import { automationRulePaths, loadAutomationEditor } from "./rule-routing";

const resources: AutomationResources = {
  types: [
    { id: "task", name: "Task" },
    { id: "bug", name: "Bug" },
  ],
  states: [
    { id: "testing", name: "IN TESTING" },
    { id: "progress", name: "InProgress" },
  ],
  members: [],
  labels: [],
  work_items: [],
  timezone: "Asia/Bangkok",
};
const unusedService: Pick<AutomationService, "rule" | "templates"> = {
  rule: async () => {
    throw new Error("A new rule should not fetch an existing rule.");
  },
  templates: async () => {
    throw new Error("A new rule should not fetch templates.");
  },
};

test("fresh create and Bug starter URLs initialize without list-page state or writes", async () => {
  const paths = automationRulePaths("qldapm", "project");
  const url = new URL(paths.bug, "http://localhost:3000");
  assert.equal(url.pathname, `${paths.create}`);
  const { draft } = await loadAutomationEditor(
    { preset: url.searchParams.get("preset")! },
    resources,
    unusedService,
    "qldapm",
    "project"
  );
  assert.equal(draft.trigger, "state_changed");
  assert.deepEqual(draft.trigger_options, { from_state: "testing", to_state: "progress" });
  assert.equal(draft.actions[0].type, "create_work_item");
  const fresh = await loadAutomationEditor({}, resources, unusedService, "qldapm", "project");
  assert.equal(fresh.draft.name, "");
  assert.equal(fresh.draft.trigger, "");
  assert.equal(fresh.rule, undefined);
});

test("a direct edit URL reloads only its saved rule and keeps server revision for saving", async () => {
  const rule: AutomationRule = {
    name: "Saved",
    trigger: "created",
    conditions: [],
    actions: [{ type: "add_comment", text: "Saved text" }],
    id: "rule-id",
    revision: 8,
    enabled: true,
  };
  const result = await loadAutomationEditor(
    { ruleId: "rule-id" },
    resources,
    {
      ...unusedService,
      rule: async (workspace, project, id) => {
        assert.deepEqual([workspace, project, id], ["workspace", "project", "rule-id"]);
        return rule;
      },
    },
    "workspace",
    "project"
  );
  assert.equal(result.rule?.revision, 8);
  result.draft.actions[0].text = "Edited";
  assert.equal(rule.actions[0].text, "Saved text");
  await assert.rejects(
    loadAutomationEditor(
      { ruleId: "missing" },
      resources,
      {
        ...unusedService,
        rule: async () => {
          throw new Error("Rule not found");
        },
      },
      "workspace",
      "project"
    ),
    /Rule not found/
  );
});

test("template selection survives a shared URL and a missing template never creates a blank rule", async () => {
  const template: AutomationTemplate = {
    id: "scheduled template",
    category: "Schedules",
    requires: [],
    name: "Daily",
    trigger: "scheduled",
    conditions: [],
    actions: [{ type: "add_comment", text: "Hello" }],
  };
  const url = new URL(automationRulePaths("w", "p").template(template.id), "http://localhost:3000");
  const service = { ...unusedService, templates: async () => [template] };
  const result = await loadAutomationEditor(
    { templateId: url.searchParams.get("template")! },
    resources,
    service,
    "w",
    "p"
  );
  assert.equal(result.draft.name, "Daily");
  assert.equal(result.draft.trigger_options?.timezone, "Asia/Bangkok");
  assert.equal(result.rule, undefined);
  await assert.rejects(loadAutomationEditor({ templateId: "removed" }, resources, service, "w", "p"), /unavailable/);
});
