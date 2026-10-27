# Analytics Implementation Plan

## Architecture decision

Keep the current Plane architecture:

- React screens use MobX filter state and SWR.
- UI primitives remain @makeplane/propel.
- Plane-specific charts and empty states remain @plane/blocks.
- Django performs aggregation in PostgreSQL.
- Existing Redis, Celery worker, and beat worker remain unchanged.
- No commercial feature flag or license path is bypassed.
- No new container is required.

The reporting API is an additive extension of the existing Analytics module. It does not replace Work Item list APIs or calculate large datasets in the browser.

## P0: Core Analytics

Implemented:

- Nine-tab Analytics navigation: Overview, Work Items, Members, Projects, Cycles, Modules, Workflow, Automation, Reports.
- Workspace KPI report with state, priority and Work Item Type distributions.
- Created vs resolved trend.
- Bug counts based on Work Item Type.
- Overdue calculation.
- Parent/Subtask count modes.
- Member workload table with fair-use explanation.
- Project comparison.
- Project and date filters.
- CSV export for member and project summaries.
- Backend enforcement of active, non-deleted project membership.
- Empty, loading and error states.
- One shared SWR report request across all report tabs, preserving data while filters or tabs change.
- Browser verification of all nine tabs, live KPI data, CSV controls and both parent-count modes.

Remaining before P0 can be marked fully complete:

- Unified filters for member, type, state, priority, Cycle and Module in the header.
- Drill-down from every KPI and chart segment to the matching Work Item list.
- Dedicated project-level Analytics route in the project navigation.
- Responsive and dark-mode browser coverage beyond the verified desktop light-mode flow.
- Configurable project health rules. Until configured, show no health classification.

## P1: Advanced Analytics

Current partial foundation:

- Cycle and Module current progress.
- Existing Cycle burndown/burnup UI.
- Reopen events from state history.
- Automation rule and execution outcome totals.
- Existing and new CSV exports.

Required next increments:

1. Normalize state transitions into intervals for time-in-state, cycle time and lead time.
2. Record or reconstruct reliable Cycle scope changes for historical burnup and velocity.
3. Add configurable workflow bottleneck thresholds.
4. Store Automation execution start and finish timestamps and retry count.
5. Add paginated drill-down endpoints rather than returning Work Item details in summary responses.
6. Add trend comparison with the previous period.

Any new snapshot table must include workspace, project, source timestamp, timezone, calculation version and idempotency key. A migration is justified only when existing history cannot answer the metric accurately.

## P2: Optional extensions

- Versioned scoring rules, disabled by default.
- Saved Analytics filters.
- Custom report definitions.
- Excel export.
- Cross-project comparison beyond the P0 summary.

Scoring must remain separate from objective KPIs and must not rank members until an approved rule is configured.

## Performance plan

- Keep summary aggregation in PostgreSQL.
- Use distinct counts when joining assignees, Cycles or Modules.
- Limit date ranges to 366 days and dimension rows to 100.
- Add pagination to future detail APIs.
- Measure query count and execution plans on production-sized fixtures before adding indexes.
- Cache only stable, permission-scoped payloads with filter-aware keys.

## Rollout

1. Run backend contract tests.
2. Run frontend type, lint and component tests.
3. Verify the API against local real data without modifying it.
4. Verify all tabs in light and dark mode.
5. Deploy with the existing API and web services.
6. Monitor endpoint latency and errors before starting historical aggregation work.
