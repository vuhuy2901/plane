import assert from "node:assert/strict";
import test from "node:test";
import { BaseAnalyticsStore } from "@/store/analytics.store";
import { ANALYTICS_TAB_KEYS } from "./tab-config";

test("analytics exposes the complete workspace navigation", () => {
  assert.deepEqual(
    [...ANALYTICS_TAB_KEYS],
    ["overview", "work-items", "members", "projects", "cycles", "modules", "workflow", "automation", "report"]
  );
});

test("count mode defaults to all work items and can switch to top-level only", () => {
  const store = new BaseAnalyticsStore();

  assert.equal(store.countMode, "all");
  store.updateCountMode("top_level");
  assert.equal(store.countMode, "top_level");
});
