import assert from "node:assert/strict";
import { test } from "node:test";
import type { IMyWorkDashboardIssue } from "@plane/types";
import { buildPersonalDashboard } from "./personal-work-dashboard.utils";

const issue = (overrides: Partial<IMyWorkDashboardIssue>): IMyWorkDashboardIssue => ({
  id: "issue",
  name: "Work item",
  sequence_id: 1,
  project_id: "project",
  project_name: "Project",
  project_identifier: "PRJ",
  priority: "medium",
  state_id: "state",
  state_name: "Todo",
  state_group: "unstarted",
  state_color: "#666",
  start_date: null,
  target_date: null,
  estimate: null,
  parent_id: null,
  parent_name: null,
  is_blocked: false,
  ...overrides,
});

test("classifies assigned work and recommends urgent executable subtasks", () => {
  const dashboard = buildPersonalDashboard(
    [
      issue({ id: "overdue", target_date: "2026-10-27", priority: "high" }),
      issue({ id: "today", target_date: "2026-10-29" }),
      issue({ id: "upcoming", target_date: "2026-11-02" }),
      issue({ id: "blocked", target_date: "2026-10-28", is_blocked: true }),
      issue({ id: "parent", priority: "urgent" }),
      issue({ id: "child", parent_id: "parent", parent_name: "Parent", priority: "high" }),
    ],
    { projectId: "all", priority: "all", window: 7 },
    "2026-10-29"
  );

  assert.deepEqual(
    dashboard.overdue.map(({ id }) => id),
    ["overdue", "blocked"]
  );
  assert.deepEqual(
    dashboard.dueToday.map(({ id }) => id),
    ["today"]
  );
  assert.deepEqual(
    dashboard.upcoming.map(({ id }) => id),
    ["upcoming"]
  );
  assert.equal(dashboard.unscheduled.length, 2);
  assert.equal(
    dashboard.suggestions.some(({ id }) => id === "blocked"),
    false
  );
  assert.equal(
    dashboard.suggestions.some(({ id }) => id === "parent"),
    false
  );
  assert.equal(
    dashboard.suggestions.some(({ id }) => id === "child"),
    true
  );
});
