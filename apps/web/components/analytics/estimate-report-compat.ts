import type { IWorkspaceReport, TWorkspaceEstimateAnalytics } from "@plane/types";

const emptyEstimateAnalytics = (): TWorkspaceEstimateAnalytics => ({
  configuration: {
    points_projects: 0,
    incompatible_projects: [],
    is_available: false,
  },
  summary: {
    total_estimated_points: 0,
    completed_points: 0,
    remaining_points: 0,
    in_progress_points: 0,
    completion_rate: 0,
    coverage: 0,
    eligible_items: 0,
    estimated_items: 0,
    unestimated_items: 0,
    average_points: 0,
  },
  progress: [],
  distribution: [],
  by_type: [],
  members: [],
  projects: [],
  cycles: [],
  completion_trend: [],
});

export const normalizeWorkspaceEstimateAnalytics = (report: IWorkspaceReport): IWorkspaceReport => {
  const estimates = (report as IWorkspaceReport & { estimates?: TWorkspaceEstimateAnalytics }).estimates;
  if (estimates) return report;

  return { ...report, estimates: emptyEstimateAnalytics() };
};
