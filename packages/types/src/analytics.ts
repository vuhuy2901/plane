/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TChartData } from "./charts";

export enum ChartXAxisProperty {
  STATES = "STATES",
  STATE_GROUPS = "STATE_GROUPS",
  LABELS = "LABELS",
  ASSIGNEES = "ASSIGNEES",
  ESTIMATE_POINTS = "ESTIMATE_POINTS",
  CYCLES = "CYCLES",
  MODULES = "MODULES",
  PRIORITY = "PRIORITY",
  START_DATE = "START_DATE",
  TARGET_DATE = "TARGET_DATE",
  CREATED_AT = "CREATED_AT",
  COMPLETED_AT = "COMPLETED_AT",
  CREATED_BY = "CREATED_BY",
  WORK_ITEM_TYPES = "WORK_ITEM_TYPES",
  PROJECTS = "PROJECTS",
  EPICS = "EPICS",
}

export enum ChartYAxisMetric {
  WORK_ITEM_COUNT = "WORK_ITEM_COUNT",
  ESTIMATE_POINT_COUNT = "ESTIMATE_POINT_COUNT",
  PENDING_WORK_ITEM_COUNT = "PENDING_WORK_ITEM_COUNT",
  COMPLETED_WORK_ITEM_COUNT = "COMPLETED_WORK_ITEM_COUNT",
  IN_PROGRESS_WORK_ITEM_COUNT = "IN_PROGRESS_WORK_ITEM_COUNT",
  WORK_ITEM_DUE_THIS_WEEK_COUNT = "WORK_ITEM_DUE_THIS_WEEK_COUNT",
  WORK_ITEM_DUE_TODAY_COUNT = "WORK_ITEM_DUE_TODAY_COUNT",
  BLOCKED_WORK_ITEM_COUNT = "BLOCKED_WORK_ITEM_COUNT",
  EPIC_WORK_ITEM_COUNT = "EPIC_WORK_ITEM_COUNT",
}

export type TAnalyticsTabsBase = "overview" | "work-items";
export type TAnalyticsTab =
  | TAnalyticsTabsBase
  | "members"
  | "projects"
  | "cycles"
  | "modules"
  | "workflow"
  | "automation"
  | "report";
export type TAnalyticsGraphsBase = "projects" | "work-items" | "custom-work-items";
export interface AnalyticsTab {
  key: TAnalyticsTab;
  label: string;
  content: React.FC;
  isDisabled: boolean;
}
export type TAnalyticsFilterParams = {
  date_filter?: string;
  project_ids?: string;
  cycle_id?: string;
  module_id?: string;
};

export type TAnalyticsCountMode = "all" | "top_level";

export type TWorkspaceReportParams = {
  project_ids?: string;
  date_filter?: string;
  count_mode?: TAnalyticsCountMode;
  type_ids?: string;
  state_ids?: string;
  assignee_ids?: string;
  cycle_ids?: string;
  module_ids?: string;
  priorities?: string;
};

export interface IWorkspaceReport {
  meta: {
    generated_at: string;
    date_from: string;
    date_to: string;
    date_basis: "work_item_created_at";
    count_mode: TAnalyticsCountMode;
    reference_date: string;
    member_allocation: "full_count_per_assignee";
    limits: { max_days: number; max_rows_per_dimension: number };
    limitations: string[];
  };
  totals: {
    total: number;
    completed: number;
    cancelled: number;
    in_progress: number;
    unstarted: number;
    overdue: number;
    subtasks: number;
    completion_rate: number;
    completion_denominator: number;
    average_completion_seconds: number | null;
    total_bugs: number;
    open_bugs: number;
    completed_bugs: number;
    active_members: number;
    active_cycles: number;
  };
  states: {
    state_id: string | null;
    state__name: string | null;
    state__group: string | null;
    state__color: string | null;
    count: number;
  }[];
  priorities: { priority: string; count: number }[];
  types: { type_id: string | null; type__name: string | null; type__color: string | null; count: number }[];
  bugs: {
    total: number;
    open: number;
    completed: number;
    overdue: number;
    by_state: IWorkspaceReport["states"];
    by_priority: IWorkspaceReport["priorities"];
  };
  parenting: {
    subtasks: number;
    completed_subtasks: number;
    parents_with_open_children: number;
  };
  reopen: { transitions: number; work_items: number };
  members: {
    assignee_id: string;
    assignee__display_name: string;
    assignee__first_name: string;
    assignee__last_name: string;
    assigned: number;
    completed: number;
    in_progress: number;
    overdue: number;
    bugs_assigned: number;
    bugs_resolved: number;
  }[];
  projects: {
    id: string;
    name: string;
    identifier: string;
    total: number;
    completed: number;
    overdue: number;
    open_bugs: number;
    progress: number;
  }[];
  cycles: TWorkspaceProgressRow[];
  modules: TWorkspaceProgressRow[];
  trend: { date: string; created: number; resolved: number }[];
  automation: {
    rules: number;
    enabled_rules: number;
    disabled_rules: number;
    executions: number;
    successful: number;
    failed: number;
    skipped: number;
    average_execution_seconds: number | null;
    average_execution_time_status: "available" | "insufficient_data";
  };
  worklogs_available: boolean;
}

export interface TWorkspaceProgressRow {
  id: string;
  name: string;
  project_id: string;
  project__name: string;
  start_date: string | null;
  end_date?: string | null;
  target_date?: string | null;
  total: number;
  completed: number;
  overdue: number;
  open_bugs: number;
  active_members: number;
  progress: number;
}

// service types

export interface IAnalyticsResponse {
  [key: string]: any;
}

export interface IAnalyticsResponseFields {
  count: number;
  filter_count: number;
}

// chart types

export interface IChartResponse {
  schema: Record<string, string>;
  data: TChartData<string, string>[];
}

// table types

export interface WorkItemInsightColumns {
  project_id?: string;
  project__name?: string;
  cancelled_work_items: number;
  completed_work_items: number;
  backlog_work_items: number;
  un_started_work_items: number;
  started_work_items: number;
  // in case of peek view, we will display the display_name instead of project__name
  display_name?: string;
  avatar_url?: string;
  assignee_id?: string;
}

export type AnalyticsTableDataMap = {
  "work-items": WorkItemInsightColumns;
};

export interface IAnalyticsParams {
  x_axis: ChartXAxisProperty;
  y_axis: ChartYAxisMetric;
  group_by?: ChartXAxisProperty;
}
