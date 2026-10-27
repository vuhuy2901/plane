# Analytics Test Report

Report date: 2026-10-26

## Automated evidence

### Backend contract suite

Command scope:

- test_workspace_report.py
- test_workspace_analytics_project_scope_app.py

Combined result: 18 passed in 54.43 seconds.

This verified existing workspace/project membership scoping, saved Analytics scoping and export worker user scoping before the P0 expansion.

### Expanded report contract

File: apps/api/plane/tests/contract/app/test_workspace_report.py

Result: 8 passed.

Covered:

- Exclusion of inaccessible projects.
- Invalid UUID rejection.
- Total, completed, overdue and Bug KPI calculations.
- Parent/Subtask all-items and top-level modes.
- Priority filtering.
- Member and Project aggregation.
- Soft-deleted Project membership exclusion.
- Invalid date, priority and count-mode filters.

## Static verification

Results:

- Python formatting and Ruff: passed.
- Web TypeScript type check: passed.
- Targeted frontend OxLint with warnings denied: passed.
- Frontend Analytics unit tests: 2 passed.

## Live read-only verification

The API service was restarted without changing the database or volumes, then verified using the existing qldapm user and workspace data.

- `GET /api/workspaces/qldapm/analytics-report/?date_filter=last_30_days&count_mode=all`: 200.
- All mode: 373 Work Items, 5 Bugs, 4 Projects, 5 Members, 31 trend points and 23 Automation executions.
- Top-level mode: 132 Work Items and 0 child Work Items.
- Warm API requests completed in approximately 0.3-0.6 seconds on the local Docker stack. A cold Django management-shell request took longer and is not treated as browser latency.
- Desktop browser: all nine tabs rendered, Members and Reports tables/actions were present, and changing All work items to Top-level only updated Overview from 373 to 132.
- A filter-and-tab race found during verification was fixed by hoisting the report request to one shared provider. Repeating the rapid Reports/Overview switch retained the correct 132 result without an error state.

Not covered in this pass: responsive viewport matrix and dark-mode visual regression.

## Integration verification still required

- Work Item created, then reflected in Overview.
- Work Item completed, then completion rate changes.
- Testing to In Progress transition increments rework but not Bug count.
- Assignee change updates current workload.
- Automation-created Bug appears in Bug metrics.
- Cycle assignment updates Cycle Analytics.
- Direct API access by a removed member returns no Project data.

Integration tests must use isolated fixtures and must not alter the live workspace.

## Data-quality gates

The following metrics are intentionally not reported as available:

- Automation average execution time.
- Historical assignee-at-completion.
- Complete historical Cycle velocity without scope history.
- Time in State before interval normalization.

No feature is marked COMPLETE solely because a screen renders.
