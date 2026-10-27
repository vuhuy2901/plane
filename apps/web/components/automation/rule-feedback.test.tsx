import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { AutomationResources, AutomationRule, AutomationService } from "@/services/automation.service";
import { EvaluationDetails, RuleDryRun, RuleSummary } from "./rule-feedback";
import { createBugDraft } from "./rule-presentation";

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
  work_items: [{ id: "source", name: "Task to check" }],
};

test("rendered rule preview distinguishes source Task, state transition, and created Bug", () => {
  const html = renderToStaticMarkup(<RuleSummary definition={createBugDraft(resources)} resources={resources} />);
  assert.match(html, /When<\/dt>/);
  assert.match(html, /Previous state: In Testing/);
  assert.match(html, /New state: In Progress/);
  assert.match(html, /Source work item type is Task/);
  assert.match(html, /Create Bug: Bug:/);
  assert.match(html, /Child of source work item \(nested\)/);
  assert.doesNotMatch(html, /Assign source/);
});

test("rendered evaluation shows expected and actual events instead of a generic condition error", () => {
  const html = renderToStaticMarkup(
    <EvaluationDetails
      resources={resources}
      evaluation={{
        matched: false,
        trigger: {
          matched: false,
          expected: "created",
          actual: ["updated", "state_changed"],
          checks: [
            {
              field: "trigger",
              operator: "contains",
              expected: "created",
              actual: ["updated", "state_changed"],
              matched: false,
            },
          ],
        },
        conditions: [],
      }}
    />
  );
  assert.match(html, /When: Not matched/);
  assert.match(html, /Expected source event: Work item created/);
  assert.match(html, /Evaluated source events: Work item updated, State changed/);
  assert.match(html, /Review the source event/);
  assert.doesNotMatch(html, /\{&quot;/);
});

test("saved rule testing is explicitly a dry-run and blocked while a draft is open", () => {
  const rule: AutomationRule = { ...createBugDraft(resources), id: "saved", revision: 4, enabled: false };
  const service = {} as AutomationService;
  const html = renderToStaticMarkup(
    <RuleDryRun service={service} workspace="w" project="p" rule={rule} resources={resources} resourcesReady hasDraft />
  );
  assert.match(html, /Check latest event \(dry-run\)/);
  assert.match(html, /Save or cancel your open draft/);
  assert.match(html, /never executed/);
  assert.match(html, /<select[^>]*disabled/);
});
