# Analytics and Reporting Audit

Audit date: 2026-10-26

## Scope and method

This audit covers the current repository, including local customizations. It does not assume parity with upstream Plane and does not enable or imitate commercial features. Evidence was collected from frontend routes and components, backend endpoints, database models, worker models, and isolated contract tests.

## Summary

The Community codebase already contains a usable analytics foundation:

- Workspace navigation and routes for Analytics.
- Database-level aggregation endpoints for overview, work items, charts, and project statistics.
- Reusable Plane chart components based on Recharts.
- Cycle and Module progress sidebars, including current burndown and burnup views.
- CSV export in both the browser and the asynchronous backend exporter.
- Work Item activity history and custom Work Item Types.
- Custom Automation rule, event, and execution history.

The main gap was not an empty system. It was fragmentation: existing analytics covered only part of the requested metrics, global filters were partially disabled, project and member reporting had no dedicated navigation, and historical limitations were not disclosed.

## Feature matrix

| Feature | Frontend | Backend | Database | Status | Action |
|---|---|---|---|---|---|
| Overview | Workspace Analytics route and existing insight/chart components; new verified KPI report in apps/web/components/analytics/report.tsx | Existing advance endpoints plus WorkspaceReportEndpoint | Issue, State, IssueType, ProjectMember, Cycle | PARTIAL | P0 KPI, state, priority, type, created/resolved, Bug and overdue metrics implemented. Drill-down remains. |
| Work Items | Existing Work Items tab, customizable chart, table and CSV | AdvanceAnalyticsEndpoint, stats and chart endpoints | Work Item fields, assignees, labels, estimates, parent and type | PARTIAL | Existing functionality retained. Parent counting and reopen summary added. Creator and label filters still need one global filter surface. |
| Members | New Members tab and workload table | Member aggregation in WorkspaceReportEndpoint | IssueAssignee, ProjectMember, IssueActivity | PARTIAL | Current-assignee workload is implemented. Historical assignee-at-completion is unavailable and disclosed. |
| Projects | New Projects tab and comparison table | Permission-scoped project aggregation | Project, ProjectMember, Issue | PARTIAL | Total, completed, overdue, open Bugs and progress implemented. Configurable project health is not implemented. |
| Cycles | Existing Cycle analytics sidebar plus new Cycles comparison tab | Existing Cycle analytics/progress APIs plus report aggregation | Cycle, CycleIssue, progress_snapshot | PARTIAL | Current progress is available. Trustworthy historical scope and velocity require additional history. |
| Modules | Existing Module analytics sidebar plus new Modules comparison tab | Existing Module analytics APIs plus report aggregation | Module, ModuleIssue | PARTIAL | Progress, members, overdue and open Bugs implemented. Multi-module totals are explicitly non-additive. |
| Workflow | New Workflow tab; existing workflow designer remains separate | Reopen aggregation from stored activities | IssueActivity, State, custom Workflow models | PARTIAL | Verified reopen transitions implemented. Time-in-state intervals and bottleneck trends remain. |
| Automation | Existing per-rule history plus new Automation summary tab | Existing Automation API and worker; report aggregation added | ProjectAutomationRule, ProjectAutomationEvent, ProjectAutomationExecution | PARTIAL | Rule and status counts implemented. Execution duration cannot be calculated because start/finish timestamps are not stored. |
| Reports | Existing work-item CSV plus new filtered project/member CSV buttons | Existing asynchronous export API and new report API | Existing models only | PARTIAL | CSV is available. Excel and saved custom reports are deferred. |
| Permissions | Sidebar uses workspace context; backend now enforces active, non-deleted project membership | Permission decorators and project-scoped database filters | Workspace and Project membership | COMPLETE | Soft-deleted membership leak in shared analytics filters was fixed and contract-tested. |

## Frontend evidence

- Route: apps/web/app/(all)/[workspaceSlug]/(projects)/analytics/[tabId]/page.tsx
- Route registration: apps/web/app/routes/core.ts
- Sidebar entry: apps/web/components/workspace/sidebar/workspace-menu.tsx
- Navigation tabs: apps/web/components/analytics/tabs.tsx
- Existing overview and work item screens: apps/web/components/analytics/overview, apps/web/components/analytics/work-items
- New P0/P1 summary screens: apps/web/components/analytics/report.tsx
- Shared filters: apps/web/components/analytics/analytics-filter-actions.tsx
- Analytics state: apps/web/store/analytics.store.ts
- Plane charts: packages/blocks/src/charts
- Existing CSV helper: apps/web/components/analytics/export.ts

## Backend evidence

- URL registration: apps/api/plane/app/urls/analytic.py
- Existing workspace analytics: apps/api/plane/app/views/analytic/base.py
- Existing advanced analytics: apps/api/plane/app/views/analytic/advance.py
- Existing project analytics: apps/api/plane/app/views/analytic/project_analytics.py
- Verified reporting endpoint: apps/api/plane/app/views/analytic/report.py
- Shared permission/date filters: apps/api/plane/utils/date_utils.py
- Chart aggregation: apps/api/plane/utils/build_chart.py, apps/api/plane/utils/analytics_plot.py
- CSV background export: apps/api/plane/bgtasks/analytic_plot_export.py
- Cycle analytics: apps/api/plane/app/views/cycle/base.py
- Module analytics: apps/api/plane/app/views/module/base.py

## Data model evidence

- Work Items and activity: apps/api/plane/db/models/issue.py
- Work Item Types: apps/api/plane/db/models/issue_type.py
- Projects and membership: apps/api/plane/db/models/project.py
- Cycles: apps/api/plane/db/models/cycle.py
- Modules: apps/api/plane/db/models/module.py
- States: apps/api/plane/db/models/state.py
- Estimates: apps/api/plane/db/models/estimate.py
- Automation history: apps/api/plane/db/models/automation.py

## Confirmed limitations

1. Issue.completed_at is cleared when a completed Work Item is reopened. A resolved trend based only on this field cannot preserve the earlier completion.
2. IssueActivity records state transitions but is not normalized into continuous state intervals. Time in status and historical WIP need a dedicated statistics service or snapshots.
3. Current assignment can be aggregated. Historical assignee-at-completion is not reliably reconstructable for every older Work Item.
4. Automation executions have status and creation time but no explicit start and finish timestamps, so average execution duration is unavailable.
5. Cycle progress_snapshot supports closed/current views, but complete daily scope history is not guaranteed for every older Cycle.
6. Work Item Type has no built-in semantic is_bug flag. Default Bug detection uses the active type named Bug; the report API also accepts explicit bug_type_ids.

## Security finding fixed

get_analytics_filters previously required an active Project membership but did not exclude a soft-deleted membership row. Both issue and project filters now require deleted_at IS NULL. Contract coverage verifies that a removed member receives zero project data.

## Test evidence

- Combined analytics contract run: 18 passed.
- Expanded workspace report file: 8 passed.
- Frontend navigation and count-mode unit tests: 2 passed.
- Web TypeScript and targeted OxLint checks: passed.
- Live read-only verification: 373 all-scope Work Items and 132 top-level Work Items returned for workspace qldapm; the same values rendered in Overview.
- Test files:
  - apps/api/plane/tests/contract/app/test_workspace_report.py
  - apps/api/plane/tests/contract/app/test_workspace_analytics_project_scope_app.py

No database migration was added during this phase.
