import type { TAnalyticsTab } from "@plane/types";

export const ANALYTICS_TAB_KEYS = [
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
] as const satisfies readonly TAnalyticsTab[];
