/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { createContext, useContext, useMemo } from "react";
import type { ReactNode } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import useSWR from "swr";
import type { SWRResponse } from "swr";
import { DownloadOutline, RefreshOutline } from "@makeplane/propel/icons";
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { AreaChart } from "@plane/blocks/charts/area-chart";
import type { IWorkspaceReport, TWorkspaceProgressRow } from "@plane/types";
import { useAnalytics } from "@/hooks/store/use-analytics";
import { AnalyticsService } from "@/services/analytics.service";
import AnalyticsWrapper from "./analytics-wrapper";
import { normalizeWorkspaceEstimateAnalytics } from "./estimate-report-compat";
import { exportRowsCSV } from "./export";

const analyticsService = new AnalyticsService();

const formatNumber = (value: number) => new Intl.NumberFormat().format(value);

const formatDuration = (seconds: number | null) => {
  if (seconds === null) return "Insufficient data";
  const hours = Math.round((seconds / 3600) * 10) / 10;
  if (hours < 24) return `${hours}h`;
  return `${Math.round((hours / 24) * 10) / 10}d`;
};

const memberName = (member: IWorkspaceReport["members"][number]) =>
  member.assignee__display_name ||
  [member.assignee__first_name, member.assignee__last_name].filter(Boolean).join(" ") ||
  "Unnamed member";

type TWorkspaceReportContext = SWRResponse<IWorkspaceReport, unknown> & { slug: string };

const WorkspaceReportContext = createContext<TWorkspaceReportContext | null>(null);

export function WorkspaceReportProvider({ children }: { children: ReactNode }) {
  const { workspaceSlug } = useParams();
  const slug = String(workspaceSlug);
  const { countMode, selectedDuration, selectedProjects } = useAnalytics();
  const report = useSWR<IWorkspaceReport>(
    ["workspace-report", slug, selectedDuration, selectedProjects.join(","), countMode],
    () =>
      analyticsService.getWorkspaceReport(slug, {
        date_filter: selectedDuration,
        count_mode: countMode,
        ...(selectedProjects.length ? { project_ids: selectedProjects.join(",") } : {}),
      }),
    // A filter change represents a different report. Rendering the previous
    // response while the new request is in flight makes old numbers look like
    // they belong to the newly selected filters.
    { keepPreviousData: false }
  );
  const contextValue = useMemo(
    () => ({
      slug,
      ...report,
      data: report.data ? normalizeWorkspaceEstimateAnalytics(report.data) : undefined,
    }),
    [slug, report]
  );

  return <WorkspaceReportContext.Provider value={contextValue}>{children}</WorkspaceReportContext.Provider>;
}

export function useWorkspaceReport() {
  const context = useContext(WorkspaceReportContext);
  if (!context) throw new Error("WorkspaceReportProvider is required for analytics reporting");
  return context;
}

function LoadingState() {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" role="status" aria-label="Loading analytics">
      {Array.from({ length: 8 }, (_, index) => (
        <div key={index} className="h-24 animate-pulse rounded-md bg-layer-1" />
      ))}
    </div>
  );
}

function ErrorState({ retry }: { retry: () => void }) {
  return (
    <div
      className="flex min-h-64 flex-col items-center justify-center gap-3 rounded-md border border-subtle"
      role="alert"
    >
      <p className="text-sm font-medium text-primary">Analytics could not be loaded.</p>
      <p className="text-sm text-secondary">Check the selected filters or try again.</p>
      <Button
        variant="secondary"
        size="sm"
        stretch="auto"
        label="Retry"
        icon={<Icon icon={RefreshOutline} />}
        iconPosition="start"
        onClick={retry}
      />
    </div>
  );
}

function ReportPage({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <AnalyticsWrapper i18nTitle="common.analytics">
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-primary">{title}</h2>
        <p className="text-sm mt-1 max-w-3xl text-secondary">{description}</p>
      </div>
      {children}
    </AnalyticsWrapper>
  );
}

function StatCard({ label, value, detail }: { label: string; value: number | string; detail?: string }) {
  return (
    <div className="min-w-0 rounded-md border border-subtle bg-surface-1 p-4">
      <p className="text-xs truncate font-medium text-secondary">{label}</p>
      <p className="text-2xl mt-2 font-semibold text-primary tabular-nums">
        {typeof value === "number" ? formatNumber(value) : value}
      </p>
      {detail && <p className="text-xs mt-1 text-tertiary">{detail}</p>}
    </div>
  );
}

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="rounded-md border border-subtle bg-surface-1 p-5">
      <div className="mb-4">
        <h3 className="text-base font-semibold text-primary">{title}</h3>
        {description && <p className="text-xs mt-1 text-secondary">{description}</p>}
      </div>
      {children}
    </section>
  );
}

function Distribution({
  rows,
  total,
}: {
  rows: { key: string; label: string; count: number; color?: string | null }[];
  total: number;
}) {
  if (!rows.length) return <p className="text-sm text-secondary">No data for the selected filters.</p>;
  return (
    <div className="space-y-3">
      {rows.map((row) => (
        <div key={row.key} className="text-sm grid grid-cols-[minmax(7rem,1fr)_3fr_auto] items-center gap-3">
          <span className="truncate text-primary" title={row.label}>
            {row.label}
          </span>
          <span className="h-1.5 overflow-hidden rounded-full bg-layer-1">
            <span
              className="block h-full rounded-full"
              style={{
                width: `${total ? Math.max((row.count / total) * 100, 2) : 0}%`,
                backgroundColor: row.color || "var(--text-color-secondary)",
              }}
            />
          </span>
          <span className="w-10 text-right text-secondary tabular-nums">{row.count}</span>
        </div>
      ))}
    </div>
  );
}

function StateDistribution({ rows, total }: { rows: IWorkspaceReport["states"]; total: number }) {
  const nameCounts = rows.reduce<Record<string, number>>((counts, row) => {
    const name = row.state__name ?? "No state";
    counts[name] = (counts[name] ?? 0) + 1;
    return counts;
  }, {});

  return (
    <Distribution
      total={total}
      rows={rows.map((row) => {
        const name = row.state__name ?? "No state";
        const projectName = row.state__project__name;
        return {
          key: row.state_id ?? `${row.state__group}-none`,
          label: nameCounts[name] > 1 && projectName ? `${name} (${projectName})` : name,
          count: row.count,
          color: row.state__color,
        };
      })}
    />
  );
}

function ProgressTable({ rows, entity }: { rows: TWorkspaceProgressRow[]; entity: "Cycle" | "Module" }) {
  if (!rows.length) return <p className="text-sm text-secondary">No {entity.toLowerCase()} data is available.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="text-sm w-full min-w-[760px] text-left">
        <thead className="text-xs border-b border-subtle text-secondary">
          <tr>
            <th className="pb-3 font-medium">{entity}</th>
            <th className="pb-3 font-medium">Project</th>
            <th className="pb-3 text-right font-medium">Total</th>
            <th className="pb-3 text-right font-medium">Completed</th>
            <th className="pb-3 text-right font-medium">Overdue</th>
            <th className="pb-3 text-right font-medium">Open bugs</th>
            <th className="pb-3 text-right font-medium">Progress</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-subtle last:border-0">
              <td className="py-3 font-medium text-primary">{row.name}</td>
              <td className="py-3 text-secondary">{row.project__name}</td>
              <td className="py-3 text-right tabular-nums">{row.total}</td>
              <td className="py-3 text-right tabular-nums">{row.completed}</td>
              <td className="py-3 text-right tabular-nums">{row.overdue}</td>
              <td className="py-3 text-right tabular-nums">{row.open_bugs}</td>
              <td className="py-3 text-right tabular-nums">{row.progress}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DataRange({ data }: { data: IWorkspaceReport }) {
  return (
    <p className="text-xs mb-5 text-tertiary">
      Created from {data.meta.date_from} to {data.meta.date_to}. Overdue is evaluated on {data.meta.reference_date}.
    </p>
  );
}

function EstimateConfigurationNotice({ data }: { data: IWorkspaceReport }) {
  const incompatible = data.estimates.configuration.incompatible_projects;
  if (!incompatible.length) return null;
  return (
    <div className="text-sm rounded-md border border-warning-subtle bg-warning-subtle p-4 text-primary">
      {incompatible.length} selected project{incompatible.length === 1 ? " is" : "s are"} excluded from Story Points
      totals because estimates are missing or use categories.
    </div>
  );
}

function EstimateSummaryCards({ data, compact = false }: { data: IWorkspaceReport; compact?: boolean }) {
  const summary = data.estimates.summary;
  return (
    <div className={`grid grid-cols-2 gap-3 ${compact ? "lg:grid-cols-5" : "md:grid-cols-4 xl:grid-cols-7"}`}>
      <StatCard label="Total estimated points" value={`${summary.total_estimated_points} SP`} />
      <StatCard label="Completed points" value={`${summary.completed_points} SP`} />
      <StatCard label="Remaining points" value={`${summary.remaining_points} SP`} />
      {!compact && <StatCard label="In progress points" value={`${summary.in_progress_points} SP`} />}
      <StatCard label="SP completion rate" value={`${summary.completion_rate}%`} />
      <StatCard
        label="Estimate coverage"
        value={`${summary.coverage}%`}
        detail={`${summary.estimated_items}/${summary.eligible_items} eligible work items`}
      />
      {!compact && <StatCard label="Unestimated work items" value={summary.unestimated_items} />}
    </div>
  );
}

function EstimateEmptyState({ data }: { data: IWorkspaceReport }) {
  if (!data.estimates.configuration.is_available)
    return (
      <p className="text-sm rounded-md border border-subtle p-5 text-secondary">
        Estimates are not configured for the selected projects. Configure a Points estimate system in Project Settings →
        Estimates.
      </p>
    );
  if (!data.estimates.summary.estimated_items)
    return <p className="text-sm rounded-md border border-subtle p-5 text-secondary">No estimated work items yet.</p>;
  return null;
}

function EstimateMemberTable({ data }: { data: IWorkspaceReport }) {
  return (
    <div className="overflow-x-auto">
      <table className="text-sm w-full min-w-[780px] text-left">
        <thead className="text-xs border-b border-subtle text-secondary">
          <tr>
            <th className="pb-3 font-medium">Member</th>
            <th className="pb-3 text-right font-medium">Allocated SP</th>
            <th className="pb-3 text-right font-medium">Completed SP</th>
            <th className="pb-3 text-right font-medium">Remaining SP</th>
            <th className="pb-3 text-right font-medium">Estimated items</th>
            <th className="pb-3 text-right font-medium">Unestimated items</th>
          </tr>
        </thead>
        <tbody>
          {data.estimates.members.map((member) => (
            <tr key={member.assignee_id ?? "unassigned"} className="border-b border-subtle last:border-0">
              <td className="py-3 font-medium text-primary">
                {member.assignee__display_name ||
                  [member.assignee__first_name, member.assignee__last_name].filter(Boolean).join(" ") ||
                  "Unassigned"}
              </td>
              <td className="py-3 text-right tabular-nums">{member.assigned_points}</td>
              <td className="py-3 text-right tabular-nums">{member.completed_points}</td>
              <td className="py-3 text-right tabular-nums">{member.remaining_points}</td>
              <td className="py-3 text-right tabular-nums">{member.estimated_items}</td>
              <td className="py-3 text-right tabular-nums">{member.unestimated_items}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EstimateCycleTable({ data }: { data: IWorkspaceReport }) {
  if (!data.estimates.cycles.length) return <p className="text-sm text-secondary">No cycle data is available.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="text-sm w-full min-w-[820px] text-left">
        <thead className="text-xs border-b border-subtle text-secondary">
          <tr>
            <th className="pb-3 font-medium">Cycle</th>
            <th className="pb-3 font-medium">Project</th>
            <th className="pb-3 text-right font-medium">Current scope SP</th>
            <th className="pb-3 text-right font-medium">Completed SP</th>
            <th className="pb-3 text-right font-medium">Remaining SP</th>
            <th className="pb-3 text-right font-medium">Completion</th>
            <th className="pb-3 text-right font-medium">Unestimated</th>
          </tr>
        </thead>
        <tbody>
          {data.estimates.cycles.map((cycle) => (
            <tr key={cycle.id} className="border-b border-subtle last:border-0">
              <td className="py-3 font-medium text-primary">{cycle.name}</td>
              <td className="py-3 text-secondary">{cycle.project__name}</td>
              <td className="py-3 text-right tabular-nums">{cycle.current_scope_points}</td>
              <td className="py-3 text-right tabular-nums">{cycle.completed_points}</td>
              <td className="py-3 text-right tabular-nums">{cycle.remaining_points}</td>
              <td className="py-3 text-right tabular-nums">{cycle.completion_rate}%</td>
              <td className="py-3 text-right tabular-nums">{cycle.unestimated_items}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EstimateWorkItemsSection() {
  const { data, error, isLoading } = useWorkspaceReport();
  if (isLoading) return <LoadingState />;
  if (error || !data) return null;
  const empty = <EstimateEmptyState data={data} />;
  if (!data.estimates.configuration.is_available || !data.estimates.summary.estimated_items) return empty;
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
      <Section title="Work items by estimate size" description="Estimate levels come from the selected projects.">
        <Distribution
          total={data.estimates.summary.estimated_items}
          rows={data.estimates.distribution.map((row) => ({
            key: String(row.value),
            label: row.label,
            count: row.work_items,
          }))}
        />
      </Section>
      <Section title="Story Points by work item type">
        <Distribution
          total={data.estimates.summary.total_estimated_points}
          rows={data.estimates.by_type.map((row) => ({
            key: row.type_id ?? "no-type",
            label: row.type_name,
            count: row.points,
          }))}
        />
      </Section>
    </div>
  );
}

export const EstimatesAnalytics = observer(function EstimatesAnalytics() {
  const { data, error, isLoading, mutate } = useWorkspaceReport();
  if (isLoading)
    return (
      <ReportPage title="Estimate analytics" description="Loading Story Points metrics.">
        <LoadingState />
      </ReportPage>
    );
  if (error || !data)
    return (
      <ReportPage title="Estimate analytics" description="Story Points across the selected scope.">
        <ErrorState retry={() => void mutate()} />
      </ReportPage>
    );
  const noEstimateData = !data.estimates.configuration.is_available || data.estimates.summary.estimated_items === 0;
  const trend = data.estimates.completion_trend.map((row) => ({
    ...row,
    key: row.date,
    name: row.date,
    count: row.completed_points,
  }));
  return (
    <ReportPage
      title="Estimate analytics"
      description="Current Story Points workload and completed points during the selected period. Parent estimates are replaced by leaf work item totals."
    >
      <DataRange data={data} />
      <div className="space-y-5">
        <EstimateConfigurationNotice data={data} />
        {noEstimateData ? (
          <EstimateEmptyState data={data} />
        ) : (
          <>
            <EstimateSummaryCards data={data} />
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
              <Section title="Story Points progress" description="Cancelled work items are excluded.">
                <Distribution
                  total={data.estimates.summary.total_estimated_points}
                  rows={data.estimates.progress.map((row) => ({
                    key: row.group,
                    label: row.group.replace("_", " "),
                    count: row.points,
                  }))}
                />
              </Section>
              <Section title="Work items by estimate size" description="Values come from configured estimate systems.">
                <Distribution
                  total={data.estimates.summary.estimated_items}
                  rows={data.estimates.distribution.map((row) => ({
                    key: String(row.value),
                    label: row.label,
                    count: row.work_items,
                  }))}
                />
              </Section>
              <Section title="Completed Story Points over time" description="Uses the current completed_at value.">
                <AreaChart
                  className="h-[320px] w-full"
                  data={trend}
                  areas={[
                    {
                      key: "completed_points",
                      label: "Completed SP",
                      fill: "#46A75833",
                      fillOpacity: 1,
                      stackId: "completed-points",
                      strokeColor: "#46A758",
                      strokeOpacity: 1,
                      showDot: false,
                      smoothCurves: true,
                    },
                  ]}
                  xAxis={{ key: "name", label: "Date" }}
                  yAxis={{ key: "count", label: "Story Points", allowDecimals: true }}
                  legend={{ align: "left", verticalAlign: "bottom", layout: "horizontal" }}
                />
              </Section>
              <Section title="Story Points by work item type">
                <Distribution
                  total={data.estimates.summary.total_estimated_points}
                  rows={data.estimates.by_type.map((row) => ({
                    key: row.type_id ?? "no-type",
                    label: row.type_name,
                    count: row.points,
                  }))}
                />
              </Section>
            </div>
            <Section
              title="Estimated workload by member"
              description="Allocated SP is split equally across current assignees and is not a performance score."
            >
              <EstimateMemberTable data={data} />
            </Section>
            <Section
              title="Estimated vs completed points by cycle"
              description="Current scope only; no historical baseline is inferred."
            >
              <EstimateCycleTable data={data} />
            </Section>
          </>
        )}
      </div>
    </ReportPage>
  );
});

export const WorkspaceReport = observer(function WorkspaceReport() {
  const { data, error, isLoading, mutate } = useWorkspaceReport();
  if (isLoading)
    return (
      <ReportPage title="Workspace report" description="Loading verified workspace metrics.">
        <LoadingState />
      </ReportPage>
    );
  if (error || !data)
    return (
      <ReportPage title="Workspace report" description="Verified metrics across projects you can access.">
        <ErrorState retry={() => void mutate()} />
      </ReportPage>
    );

  const trendData = data.trend.map((row) => ({
    ...row,
    key: row.date,
    name: row.date,
    count: row.created + row.resolved,
  }));
  return (
    <ReportPage
      title="Workspace report"
      description="Verified work item, delivery, quality, and workload metrics. All values follow the filters above."
    >
      <DataRange data={data} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard
          label="Total work items"
          value={data.totals.total}
          detail={data.meta.count_mode === "all" ? "Includes child work items" : "Top-level only"}
        />
        <StatCard label="Completed" value={data.totals.completed} />
        <StatCard label="In progress" value={data.totals.in_progress} />
        <StatCard label="Unstarted" value={data.totals.unstarted} />
        <StatCard label="Overdue" value={data.totals.overdue} detail="Excludes completed and cancelled" />
        <StatCard label="Completion rate" value={`${data.totals.completion_rate}%`} />
        <StatCard label="Total bugs" value={data.totals.total_bugs} />
        <StatCard label="Open bugs" value={data.totals.open_bugs} />
        <StatCard label="Completed bugs" value={data.totals.completed_bugs} />
        <StatCard label="Active members" value={data.totals.active_members} />
        <StatCard label="Active cycles" value={data.totals.active_cycles} />
        <StatCard label="Average completion" value={formatDuration(data.totals.average_completion_seconds)} />
      </div>
      <div className="mt-5 space-y-3">
        <Section
          title="Estimate summary"
          description="Story Points from eligible leaf work items; cancelled work is excluded."
        >
          {data.estimates.configuration.is_available ? (
            <EstimateSummaryCards data={data} compact />
          ) : (
            <EstimateEmptyState data={data} />
          )}
        </Section>
        <EstimateConfigurationNotice data={data} />
      </div>
      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Section title="Created vs resolved" description="Based on work items created inside the selected period.">
          <AreaChart
            className="h-[320px] w-full"
            data={trendData}
            areas={[
              {
                key: "created",
                label: "Created",
                fill: "#3E63DD33",
                fillOpacity: 1,
                stackId: "created",
                strokeColor: "#3E63DD",
                strokeOpacity: 1,
                showDot: false,
                smoothCurves: true,
              },
              {
                key: "resolved",
                label: "Resolved",
                fill: "#46A75833",
                fillOpacity: 1,
                stackId: "resolved",
                strokeColor: "#46A758",
                strokeOpacity: 1,
                showDot: false,
                smoothCurves: true,
              },
            ]}
            xAxis={{ key: "name", label: "Date" }}
            yAxis={{ key: "count", label: "Work items", allowDecimals: false }}
            legend={{ align: "left", verticalAlign: "bottom", layout: "horizontal" }}
          />
        </Section>
        <Section title="Work items by state">
          <StateDistribution rows={data.states} total={data.totals.total} />
        </Section>
        <Section title="Work items by priority">
          <Distribution
            total={data.totals.total}
            rows={data.priorities.map((row) => ({ key: row.priority, label: row.priority, count: row.count }))}
          />
        </Section>
        <Section title="Work items by type">
          <Distribution
            total={data.totals.total}
            rows={data.types.map((row) => ({
              key: row.type_id ?? "no-type",
              label: row.type__name ?? "No type",
              count: row.count,
              color: row.type__color,
            }))}
          />
        </Section>
      </div>
    </ReportPage>
  );
});

export const MembersAnalytics = observer(function MembersAnalytics() {
  const { data, error, isLoading, mutate } = useWorkspaceReport();
  if (isLoading)
    return (
      <ReportPage title="Member analytics" description="Loading workload data.">
        <LoadingState />
      </ReportPage>
    );
  if (error || !data)
    return (
      <ReportPage title="Member analytics" description="Current assignment and completion metrics.">
        <ErrorState retry={() => void mutate()} />
      </ReportPage>
    );
  return (
    <ReportPage
      title="Member analytics"
      description="Each work item is counted once for every current assignee. This is workload reporting, not employee ranking."
    >
      <DataRange data={data} />
      <Section
        title="Workload by member"
        description="Completion is attributed to current assignees because historical assignee-at-completion is not available."
      >
        {data.members.length ? (
          <div className="overflow-x-auto">
            <table className="text-sm w-full min-w-[820px] text-left">
              <thead className="text-xs border-b border-subtle text-secondary">
                <tr>
                  <th className="pb-3 font-medium">Member</th>
                  <th className="pb-3 text-right font-medium">Assigned</th>
                  <th className="pb-3 text-right font-medium">Completed</th>
                  <th className="pb-3 text-right font-medium">In progress</th>
                  <th className="pb-3 text-right font-medium">Overdue</th>
                  <th className="pb-3 text-right font-medium">Bugs assigned</th>
                  <th className="pb-3 text-right font-medium">Bugs resolved</th>
                </tr>
              </thead>
              <tbody>
                {data.members.map((member) => (
                  <tr key={member.assignee_id} className="border-b border-subtle last:border-0">
                    <td className="py-3 font-medium text-primary">{memberName(member)}</td>
                    <td className="py-3 text-right tabular-nums">{member.assigned}</td>
                    <td className="py-3 text-right tabular-nums">{member.completed}</td>
                    <td className="py-3 text-right tabular-nums">{member.in_progress}</td>
                    <td className="py-3 text-right tabular-nums">{member.overdue}</td>
                    <td className="py-3 text-right tabular-nums">{member.bugs_assigned}</td>
                    <td className="py-3 text-right tabular-nums">{member.bugs_resolved}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-secondary">No assigned work items match the selected filters.</p>
        )}
      </Section>
      {data.estimates.configuration.is_available && (
        <div className="mt-5">
          <Section
            title="Allocated Story Points by member"
            description="Points are split equally for multi-assignee work items and do not represent performance."
          >
            <EstimateMemberTable data={data} />
          </Section>
        </div>
      )}
    </ReportPage>
  );
});

export const ProjectsAnalytics = observer(function ProjectsAnalytics() {
  const { data, error, isLoading, mutate } = useWorkspaceReport();
  if (isLoading)
    return (
      <ReportPage title="Project analytics" description="Loading project metrics.">
        <LoadingState />
      </ReportPage>
    );
  if (error || !data)
    return (
      <ReportPage title="Project analytics" description="Comparison across accessible projects.">
        <ErrorState retry={() => void mutate()} />
      </ReportPage>
    );
  return (
    <ReportPage
      title="Project analytics"
      description="Compare delivery progress, overdue work, and open bugs across accessible projects."
    >
      <DataRange data={data} />
      <Section title="Project comparison">
        <div className="overflow-x-auto">
          <table className="text-sm w-full min-w-[720px] text-left">
            <thead className="text-xs border-b border-subtle text-secondary">
              <tr>
                <th className="pb-3 font-medium">Project</th>
                <th className="pb-3 text-right font-medium">Total</th>
                <th className="pb-3 text-right font-medium">Completed</th>
                <th className="pb-3 text-right font-medium">Overdue</th>
                <th className="pb-3 text-right font-medium">Open bugs</th>
                <th className="pb-3 text-right font-medium">Progress</th>
                <th className="pb-3 text-right font-medium">Estimated SP</th>
                <th className="pb-3 text-right font-medium">Completed SP</th>
                <th className="pb-3 text-right font-medium">Remaining SP</th>
              </tr>
            </thead>
            <tbody>
              {data.projects.map((project) => {
                const estimate = data.estimates.projects.find((row) => row.id === project.id);
                return (
                  <tr key={project.id} className="border-b border-subtle last:border-0">
                    <td className="py-3 font-medium text-primary">
                      {project.identifier} {project.name}
                    </td>
                    <td className="py-3 text-right tabular-nums">{project.total}</td>
                    <td className="py-3 text-right tabular-nums">{project.completed}</td>
                    <td className="py-3 text-right tabular-nums">{project.overdue}</td>
                    <td className="py-3 text-right tabular-nums">{project.open_bugs}</td>
                    <td className="py-3 text-right tabular-nums">{project.progress}%</td>
                    <td className="py-3 text-right tabular-nums">{estimate?.total_points ?? "—"}</td>
                    <td className="py-3 text-right tabular-nums">{estimate?.completed_points ?? "—"}</td>
                    <td className="py-3 text-right tabular-nums">{estimate?.remaining_points ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Section>
    </ReportPage>
  );
});

function ProgressAnalytics({ entity }: { entity: "Cycle" | "Module" }) {
  const { data, error, isLoading, mutate } = useWorkspaceReport();
  const title = `${entity} analytics`;
  if (isLoading)
    return (
      <ReportPage title={title} description={`Loading ${entity.toLowerCase()} metrics.`}>
        <LoadingState />
      </ReportPage>
    );
  if (error || !data)
    return (
      <ReportPage title={title} description={`Progress across accessible ${entity.toLowerCase()}s.`}>
        <ErrorState retry={() => void mutate()} />
      </ReportPage>
    );
  return (
    <ReportPage
      title={title}
      description={`Progress, overdue work, bugs, and active members by ${entity.toLowerCase()}.`}
    >
      <DataRange data={data} />
      <Section title={`${entity} comparison`}>
        <ProgressTable rows={entity === "Cycle" ? data.cycles : data.modules} entity={entity} />
      </Section>
      {entity === "Cycle" && data.estimates.configuration.is_available && (
        <div className="mt-5">
          <Section
            title="Cycle Story Points"
            description="Current scope and completed points; no original baseline is inferred."
          >
            <EstimateCycleTable data={data} />
          </Section>
        </div>
      )}
    </ReportPage>
  );
}

export const CyclesAnalytics = observer(function CyclesAnalytics() {
  return <ProgressAnalytics entity="Cycle" />;
});

export const ModulesAnalytics = observer(function ModulesAnalytics() {
  return <ProgressAnalytics entity="Module" />;
});

export const WorkflowAnalytics = observer(function WorkflowAnalytics() {
  const { data, error, isLoading, mutate } = useWorkspaceReport();
  if (isLoading)
    return (
      <ReportPage title="Workflow analytics" description="Loading workflow history.">
        <LoadingState />
      </ReportPage>
    );
  if (error || !data)
    return (
      <ReportPage title="Workflow analytics" description="Reopen and rework history.">
        <ErrorState retry={() => void mutate()} />
      </ReportPage>
    );
  return (
    <ReportPage title="Workflow analytics" description="Verified reopen events from stored state-change history.">
      <DataRange data={data} />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <StatCard label="Reopened work items" value={data.reopen.work_items} />
        <StatCard label="Reopen transitions" value={data.reopen.transitions} />
        <StatCard label="Average completion" value={formatDuration(data.totals.average_completion_seconds)} />
      </div>
      <div className="text-sm mt-5 rounded-md border border-warning-subtle bg-warning-subtle p-4 text-primary">
        Time in state, cycle time, and bottleneck trends are not displayed yet because historical state intervals have
        not been normalized.
      </div>
    </ReportPage>
  );
});

export const AutomationAnalytics = observer(function AutomationAnalytics() {
  const { data, error, isLoading, mutate } = useWorkspaceReport();
  if (isLoading)
    return (
      <ReportPage title="Automation analytics" description="Loading automation executions.">
        <LoadingState />
      </ReportPage>
    );
  if (error || !data)
    return (
      <ReportPage title="Automation analytics" description="Rule and execution health.">
        <ErrorState retry={() => void mutate()} />
      </ReportPage>
    );
  return (
    <ReportPage
      title="Automation analytics"
      description="Rule status and execution outcomes without exposing worker payloads."
    >
      <DataRange data={data} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Total rules" value={data.automation.rules} />
        <StatCard label="Enabled rules" value={data.automation.enabled_rules} />
        <StatCard label="Disabled rules" value={data.automation.disabled_rules} />
        <StatCard label="Executions" value={data.automation.executions} />
        <StatCard label="Successful" value={data.automation.successful} />
        <StatCard label="Failed" value={data.automation.failed} />
        <StatCard label="Skipped" value={data.automation.skipped} />
        <StatCard label="Average execution time" value="Insufficient data" />
      </div>
    </ReportPage>
  );
});

export const AnalyticsReports = observer(function AnalyticsReports() {
  const { data, error, isLoading, mutate, slug } = useWorkspaceReport();
  if (isLoading)
    return (
      <ReportPage title="Reports" description="Preparing export data.">
        <LoadingState />
      </ReportPage>
    );
  if (error || !data)
    return (
      <ReportPage title="Reports" description="Download filtered analytics.">
        <ErrorState retry={() => void mutate()} />
      </ReportPage>
    );
  return (
    <ReportPage title="Reports" description="Export the filtered project or member summary as CSV.">
      <DataRange data={data} />
      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label="Export projects CSV"
          icon={<Icon icon={DownloadOutline} />}
          iconPosition="start"
          onClick={() =>
            exportRowsCSV(
              data.projects.map((project) => ({
                Project: project.name,
                Identifier: project.identifier,
                Total: project.total,
                Completed: project.completed,
                Overdue: project.overdue,
                "Open bugs": project.open_bugs,
                "Progress percent": project.progress,
              })),
              slug,
              "projects"
            )
          }
        />
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label="Export members CSV"
          icon={<Icon icon={DownloadOutline} />}
          iconPosition="start"
          onClick={() =>
            exportRowsCSV(
              data.members.map((member) => ({
                Member: memberName(member),
                Assigned: member.assigned,
                Completed: member.completed,
                "In progress": member.in_progress,
                Overdue: member.overdue,
                "Bugs assigned": member.bugs_assigned,
                "Bugs resolved": member.bugs_resolved,
              })),
              slug,
              "members"
            )
          }
        />
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label="Export estimates CSV"
          icon={<Icon icon={DownloadOutline} />}
          iconPosition="start"
          onClick={() =>
            exportRowsCSV(
              data.estimates.projects.map((project) => ({
                Project: project.name,
                Identifier: project.identifier,
                "Estimate type": project.estimate_type ?? "Not configured",
                "Estimated SP": project.total_points,
                "Completed SP": project.completed_points,
                "Remaining SP": project.remaining_points,
                "SP completion percent": project.completion_rate,
                "Estimated items": project.estimated_items,
                "Unestimated items": project.unestimated_items,
              })),
              slug,
              "estimates"
            )
          }
        />
      </div>
      <Section
        title="Data quality notes"
        description="These constraints prevent apparently precise but incorrect metrics."
      >
        <ul className="text-sm space-y-2 text-secondary">
          {data.meta.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </Section>
    </ReportPage>
  );
});
