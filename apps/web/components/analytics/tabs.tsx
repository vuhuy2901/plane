/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { AnalyticsTab, TAnalyticsTab } from "@plane/types";
import { WorkItems } from "@/components/analytics/work-items";
import {
  AnalyticsReports,
  AutomationAnalytics,
  CyclesAnalytics,
  MembersAnalytics,
  ModulesAnalytics,
  ProjectsAnalytics,
  WorkflowAnalytics,
  WorkspaceReport,
} from "@/components/analytics/report";
import { ANALYTICS_TAB_KEYS } from "./tab-config";

export const getAnalyticsTabs = (t: (key: string, params?: Record<string, any>) => string): AnalyticsTab[] => {
  const tabs: Record<TAnalyticsTab, Omit<AnalyticsTab, "key">> = {
    overview: { label: t("common.overview"), content: WorkspaceReport, isDisabled: false },
    "work-items": { label: t("sidebar.work_items"), content: WorkItems, isDisabled: false },
    members: { label: "Members", content: MembersAnalytics, isDisabled: false },
    projects: { label: "Projects", content: ProjectsAnalytics, isDisabled: false },
    cycles: { label: "Cycles", content: CyclesAnalytics, isDisabled: false },
    modules: { label: "Modules", content: ModulesAnalytics, isDisabled: false },
    workflow: { label: "Workflow", content: WorkflowAnalytics, isDisabled: false },
    automation: { label: "Automation", content: AutomationAnalytics, isDisabled: false },
    report: { label: "Reports", content: AnalyticsReports, isDisabled: false },
  };
  return ANALYTICS_TAB_KEYS.map((key) => ({
    key,
    label: tabs[key].label,
    content: tabs[key].content,
    isDisabled: tabs[key].isDisabled,
  }));
};
