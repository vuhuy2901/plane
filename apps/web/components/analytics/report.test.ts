import assert from "node:assert/strict";
import test from "node:test";
import { BaseAnalyticsStore } from "@/store/analytics.store";
import type { IWorkspaceReport } from "@plane/types";
import { normalizeWorkspaceEstimateAnalytics } from "./estimate-report-compat";
import { ANALYTICS_TAB_KEYS } from "./tab-config";

test("analytics exposes the complete workspace navigation", () => {
  assert.deepEqual(
    [...ANALYTICS_TAB_KEYS],
    [
      "overview",
      "work-items",
      "estimates",
      "members",
      "projects",
      "cycles",
      "modules",
      "workflow",
      "automation",
      "report",
    ]
  );
});

test("count mode defaults to all work items and can switch to top-level only", () => {
  const store = new BaseAnalyticsStore();

  assert.equal(store.countMode, "all");
  store.updateCountMode("top_level");
  assert.equal(store.countMode, "top_level");
});

test("normalizes cached reports created before estimate analytics was added", () => {
  const legacyReport = {} as IWorkspaceReport;
  const report = normalizeWorkspaceEstimateAnalytics(legacyReport);

  assert.equal(report.estimates.configuration.is_available, false);
  assert.equal(report.estimates.summary.total_estimated_points, 0);
  assert.deepEqual(report.estimates.projects, []);
});
