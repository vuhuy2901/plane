import { useMemo } from "react";
import { AlertCircle, CalendarClock, CircleDot, Clock3, ListTodo } from "lucide-react";
import { Link } from "react-router";
import { PriorityIcon } from "@plane/blocks/icons";
import { useLocalStorage } from "@plane/hooks";
import type { IMyWorkDashboardData, IMyWorkDashboardIssue, TIssuePriorities } from "@plane/types";
import {
  buildPersonalDashboard,
  getSuggestionReason,
  getTodayInTimezone,
  type TDashboardFilters,
  type TDashboardWindow,
} from "./personal-work-dashboard.utils";

type Props = {
  data?: IMyWorkDashboardData;
  error?: unknown;
  isLoading: boolean;
  workspaceSlug: string;
  userId: string;
};

const priorityLabel: Record<TIssuePriorities, string> = {
  urgent: "Urgent",
  high: "High",
  medium: "Medium",
  low: "Low",
  none: "No priority",
};

const formatDate = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat("en", { day: "numeric", month: "short" }).format(new Date(`${value}T00:00:00`))
    : "No due date";

const WorkItemRow = ({
  issue,
  reason,
  workspaceSlug,
}: {
  issue: IMyWorkDashboardIssue;
  reason?: string;
  workspaceSlug: string;
}) => (
  <Link
    to={`/${workspaceSlug}/projects/${issue.project_id}/issues/${issue.id}`}
    className="group grid gap-2 border-b border-subtle px-4 py-3 last:border-b-0 hover:bg-layer-1 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
  >
    <div className="min-w-0">
      <div className="flex min-w-0 items-center gap-2">
        <span className="shrink-0 text-11 font-medium text-placeholder">
          {issue.project_identifier}-{issue.sequence_id}
        </span>
        <span className="truncate text-13 font-medium text-primary">{issue.name}</span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-11 text-tertiary">
        <span>{issue.project_name}</span>
        {issue.parent_name && <span className="truncate">Subtask of {issue.parent_name}</span>}
        {reason && <span className="font-medium text-accent-primary">{reason}</span>}
      </div>
    </div>
    <div className="flex items-center gap-3 text-11 text-tertiary sm:justify-end">
      <span className="flex items-center gap-1.5">
        <span className="size-2 rounded-full" style={{ backgroundColor: issue.state_color }} />
        {issue.state_name}
      </span>
      <span className="flex items-center gap-1.5">
        <PriorityIcon priority={issue.priority} className="size-3.5" />
        {priorityLabel[issue.priority]}
      </span>
      <span className={issue.target_date ? "font-medium text-secondary" : "text-placeholder"}>
        {formatDate(issue.target_date)}
      </span>
      {issue.start_date && <span>Starts {formatDate(issue.start_date)}</span>}
      {issue.estimate !== null && <span>{issue.estimate} pts</span>}
    </div>
  </Link>
);

const EmptyState = ({ children }: { children: string }) => (
  <div className="flex min-h-24 items-center justify-center px-4 text-center text-13 text-placeholder">{children}</div>
);

const Section = ({
  title,
  description,
  issues,
  empty,
  workspaceSlug,
  userId,
  reasonForIssue,
}: {
  title: string;
  description: string;
  issues: IMyWorkDashboardIssue[];
  empty: string;
  workspaceSlug: string;
  userId: string;
  reasonForIssue?: (issue: IMyWorkDashboardIssue) => string;
}) => (
  <section className="overflow-hidden rounded-lg border border-subtle bg-surface-1">
    <div className="flex items-start justify-between gap-3 border-b border-subtle px-4 py-3">
      <div>
        <h3 className="text-13 font-semibold text-primary">{title}</h3>
        <p className="mt-0.5 text-11 text-tertiary">{description}</p>
      </div>
      <Link
        to={`/${workspaceSlug}/profile/${userId}/assigned`}
        className="shrink-0 text-11 font-medium text-accent-primary hover:underline"
      >
        View all
      </Link>
    </div>
    {issues.length > 0 ? (
      issues
        .slice(0, 6)
        .map((issue) => (
          <WorkItemRow key={issue.id} issue={issue} workspaceSlug={workspaceSlug} reason={reasonForIssue?.(issue)} />
        ))
    ) : (
      <EmptyState>{empty}</EmptyState>
    )}
  </section>
);

export const PersonalWorkDashboard = ({ data, error, isLoading, workspaceSlug, userId }: Props) => {
  const defaultFilters: TDashboardFilters = { projectId: "all", priority: "all", window: 7 };
  const { storedValue, setValue } = useLocalStorage<TDashboardFilters>(
    `my-work-dashboard-filters-${workspaceSlug}`,
    defaultFilters
  );
  const filters = storedValue ?? defaultFilters;
  const projects = useMemo(
    () =>
      // oxlint-disable-next-line unicorn/no-array-sort -- Array.from returns a private copy and the app targets ES2022.
      Array.from(new Map((data?.issues ?? []).map((issue) => [issue.project_id, issue.project_name])).entries()).sort(
        (a, b) => a[1].localeCompare(b[1])
      ),
    [data?.issues]
  );
  const today = getTodayInTimezone(data?.timezone ?? "UTC");
  const dashboard = buildPersonalDashboard(data?.issues ?? [], filters, today);

  if (isLoading)
    return (
      <div className="space-y-4">
        <div className="h-28 animate-pulse rounded-lg bg-layer-2" />
        <div className="h-56 animate-pulse rounded-lg bg-layer-2" />
      </div>
    );

  if (error)
    return (
      <div className="border-red-300/60 bg-red-50/50 text-red-700 rounded-lg border px-4 py-5 text-13">
        Your work dashboard could not be loaded. Refresh the page to try again.
      </div>
    );

  const kpis = [
    { label: "Due today", value: dashboard.dueToday.length, icon: CalendarClock },
    { label: "Overdue", value: dashboard.overdue.length, icon: AlertCircle },
    { label: `Due in ${filters.window} days`, value: dashboard.upcoming.length, icon: Clock3 },
    { label: "In progress", value: dashboard.inProgress.length, icon: CircleDot },
    { label: "Blocked", value: dashboard.blocked.length, icon: ListTodo },
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-primary">My day</h2>
          <p className="mt-1 text-13 text-tertiary">
            Your most actionable assigned work, ordered by deadline and readiness.
          </p>
          {dashboard.dueToday.length === 0 && <p className="mt-1 text-11 text-placeholder">No tasks due today.</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <select
            aria-label="Filter by project"
            value={filters.projectId}
            onChange={(event) => setValue({ ...filters, projectId: event.target.value })}
            className="focus:border-accent-primary h-8 max-w-48 rounded-md border border-subtle bg-surface-1 px-2 text-12 text-secondary outline-none"
          >
            <option value="all">All projects</option>
            {projects.map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
          <select
            aria-label="Filter by priority"
            value={filters.priority}
            onChange={(event) => setValue({ ...filters, priority: event.target.value as TIssuePriorities | "all" })}
            className="focus:border-accent-primary h-8 rounded-md border border-subtle bg-surface-1 px-2 text-12 text-secondary outline-none"
          >
            <option value="all">All priorities</option>
            {Object.entries(priorityLabel).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <select
            aria-label="Upcoming window"
            value={filters.window}
            onChange={(event) => setValue({ ...filters, window: Number(event.target.value) as TDashboardWindow })}
            className="focus:border-accent-primary h-8 rounded-md border border-subtle bg-surface-1 px-2 text-12 text-secondary outline-none"
          >
            <option value={7}>Next 7 days</option>
            <option value={14}>Next 14 days</option>
            <option value={30}>Next 30 days</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
        {kpis.map(({ label, value, icon: Icon }) => (
          <div key={label} className="rounded-lg border border-subtle bg-surface-1 px-3 py-3">
            <div className="flex items-center justify-between gap-2 text-tertiary">
              <span className="text-11 font-medium">{label}</span>
              <Icon className="size-3.5" />
            </div>
            <p className="text-xl mt-2 font-semibold text-primary tabular-nums">{value}</p>
          </div>
        ))}
      </div>

      <section className="overflow-hidden rounded-lg border border-subtle bg-surface-1">
        <div className="border-b border-subtle px-4 py-3">
          <h3 className="text-13 font-semibold text-primary">Suggested for today</h3>
          <p className="mt-0.5 text-11 text-tertiary">
            Up to five unblocked tasks ranked by urgency, progress, and priority.
          </p>
        </div>
        {dashboard.suggestions.length > 0 ? (
          dashboard.suggestions.map((issue) => (
            <WorkItemRow
              key={issue.id}
              issue={issue}
              workspaceSlug={workspaceSlug}
              reason={getSuggestionReason(issue, today)}
            />
          ))
        ) : (
          <EmptyState>You&apos;re all caught up! No executable assigned work matches these filters.</EmptyState>
        )}
      </section>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Section
          title="Upcoming"
          description={`Deadlines in the next ${filters.window} days`}
          issues={dashboard.upcoming}
          empty="Nothing due in this window."
          workspaceSlug={workspaceSlug}
          userId={userId}
        />
        <Section
          title="Overdue"
          description="Oldest deadlines first"
          issues={dashboard.overdue}
          empty="You have no overdue work."
          workspaceSlug={workspaceSlug}
          userId={userId}
          reasonForIssue={(issue) => getSuggestionReason(issue, today)}
        />
      </div>
      <Section
        title="Unscheduled"
        description="Assigned work without a due date"
        issues={dashboard.unscheduled}
        empty="All assigned work is scheduled."
        workspaceSlug={workspaceSlug}
        userId={userId}
      />
    </div>
  );
};
