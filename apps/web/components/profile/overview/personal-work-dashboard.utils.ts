import type { IMyWorkDashboardIssue, TIssuePriorities } from "@plane/types";

export type TDashboardWindow = 7 | 14 | 30;
export type TDashboardFilters = {
  projectId: string;
  priority: TIssuePriorities | "all";
  window: TDashboardWindow;
};

const PRIORITY_WEIGHT: Record<TIssuePriorities, number> = {
  urgent: 4,
  high: 3,
  medium: 2,
  low: 1,
  none: 0,
};

const dateValue = (value: string) => new Date(`${value}T00:00:00`).getTime();

export const getTodayInTimezone = (timezone: string) => {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}`;
};

export const differenceInDays = (date: string, today: string) =>
  Math.round((dateValue(date) - dateValue(today)) / 86_400_000);

export const filterDashboardIssues = (issues: IMyWorkDashboardIssue[], filters: TDashboardFilters) =>
  issues.filter(
    (issue) =>
      (filters.projectId === "all" || issue.project_id === filters.projectId) &&
      (filters.priority === "all" || issue.priority === filters.priority)
  );

const suggestionScore = (issue: IMyWorkDashboardIssue, today: string) => {
  const dueIn = issue.target_date ? differenceInDays(issue.target_date, today) : null;
  let score = PRIORITY_WEIGHT[issue.priority] * 10;
  if (dueIn !== null && dueIn < 0) score += 1_400 + Math.abs(dueIn) * 20;
  else if (dueIn === 0) score += 1_250;
  else if (dueIn !== null && dueIn <= 7) score += 900 - dueIn * 40;
  else if (dueIn !== null) score += Math.max(0, 300 - dueIn);
  if (issue.state_group === "started") score += 180;
  if (issue.start_date && differenceInDays(issue.start_date, today) <= 0) score += 80;
  if (!issue.target_date && ["urgent", "high"].includes(issue.priority)) score += 100;
  return score;
};

export const getSuggestionReason = (issue: IMyWorkDashboardIssue, today: string) => {
  if (issue.target_date) {
    const dueIn = differenceInDays(issue.target_date, today);
    if (dueIn < 0) return `Overdue by ${Math.abs(dueIn)} day${Math.abs(dueIn) === 1 ? "" : "s"}`;
    if (dueIn === 0) return "Due today";
    if (dueIn <= 7) return `Due in ${dueIn} day${dueIn === 1 ? "" : "s"}`;
  }
  if (issue.state_group === "started") return "Already in progress";
  if (issue.start_date && differenceInDays(issue.start_date, today) <= 0) return "Ready to start";
  if (["urgent", "high"].includes(issue.priority)) return "High priority";
  return "Next executable work";
};

export const buildPersonalDashboard = (issues: IMyWorkDashboardIssue[], filters: TDashboardFilters, today: string) => {
  const filtered = filterDashboardIssues(issues, filters);
  const dueToday = filtered.filter((issue) => issue.target_date === today);
  const overdue = filtered
    .filter((issue) => issue.target_date && differenceInDays(issue.target_date, today) < 0)
    // oxlint-disable-next-line unicorn/no-array-sort -- filter returns a private copy and the app targets ES2022.
    .sort((a, b) => {
      const dateDelta = dateValue(a.target_date ?? today) - dateValue(b.target_date ?? today);
      return (
        dateDelta ||
        PRIORITY_WEIGHT[b.priority] - PRIORITY_WEIGHT[a.priority] ||
        a.state_name.localeCompare(b.state_name)
      );
    });
  const upcoming = filtered
    .filter((issue) => {
      if (!issue.target_date) return false;
      const dueIn = differenceInDays(issue.target_date, today);
      return dueIn > 0 && dueIn <= filters.window;
    })
    // oxlint-disable-next-line unicorn/no-array-sort -- filter returns a private copy and the app targets ES2022.
    .sort((a, b) => dateValue(a.target_date ?? today) - dateValue(b.target_date ?? today));
  const unscheduled = filtered
    .filter((issue) => !issue.target_date)
    // oxlint-disable-next-line unicorn/no-array-sort -- filter returns a private copy and the app targets ES2022.
    .sort(
      (a, b) => PRIORITY_WEIGHT[b.priority] - PRIORITY_WEIGHT[a.priority] || a.state_name.localeCompare(b.state_name)
    );

  const isReady = (issue: IMyWorkDashboardIssue) =>
    !issue.is_blocked && (!issue.start_date || differenceInDays(issue.start_date, today) <= 0);
  const childParentIds = new Set(
    filtered.filter((issue) => issue.parent_id && isReady(issue)).map((issue) => issue.parent_id)
  );
  const suggestions = filtered
    .filter((issue) => isReady(issue) && !childParentIds.has(issue.id))
    // oxlint-disable-next-line unicorn/no-array-sort -- filter returns a private copy and the app targets ES2022.
    .sort((a, b) => suggestionScore(b, today) - suggestionScore(a, today))
    .slice(0, 5);

  return {
    dueToday,
    overdue,
    upcoming,
    unscheduled,
    suggestions,
    inProgress: filtered.filter((issue) => issue.state_group === "started"),
    blocked: filtered.filter((issue) => issue.is_blocked),
  };
};
