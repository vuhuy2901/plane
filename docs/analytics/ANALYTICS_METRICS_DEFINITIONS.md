# Analytics Metric Definitions

## Shared scope

All metrics are limited to projects the requester can access through an active, non-deleted Project membership. Archived projects, archived Work Items, draft Work Items, triage items and soft-deleted records are excluded by existing managers and report filters.

The current report date filter uses Issue.created_at. The response exposes this as meta.date_basis = work_item_created_at.

## Count modes

### All work items

Counts every matching Work Item, including children.

### Top-level only

Counts only Work Items where parent_id is null.

Totals from these modes must not be combined. Module totals are also non-additive because a Work Item can belong to multiple Modules.

## Completion rate

Formula: completed / (total - cancelled) * 100

Total work items still displays the raw total. The response includes completion_denominator so the UI and exports disclose the denominator.

## Overdue work items

A Work Item is overdue when:

- target_date is before the report reference date, and
- state group is neither completed nor cancelled.

The report reference date is the earlier of today and the filter end date.

## Bug metrics

Bug counts use Work Item Type, never a transition pattern. By default, active Work Item Types named Bug are used case-insensitively. Installations with another semantic type can supply explicit bug_type_ids.

Open Bug state groups are backlog, unstarted and started.

## Average completion time

Current implementation: completed_at - created_at

Only currently completed Work Items with a non-null completed_at are included. Reopened items lose the earlier completed_at, so this metric does not preserve previous completion attempts.

## Reopen count

A reopen transition is an IssueActivity state change whose old State belongs to group completed and whose new State does not belong to group completed.

- transitions: number of matching transitions.
- work_items: distinct Work Items with at least one matching transition.

This does not infer the reason for reopening.

## Member workload

- Assigned: current distinct Work Items assigned to the member.
- Completed: assigned Work Items currently in a completed State.
- In progress: assigned Work Items currently in a started State.
- Overdue: assigned Work Items matching the overdue definition.
- Bugs assigned/resolved: current Bug-type assignment counts.

For multiple assignees, each assignee receives one workload count. Counts must not be summed to infer unique Work Items. These metrics are not employee rankings.

## Project progress

Uses the completion-rate formula for each project. No On Track, At Risk or Off Track classification is emitted until baseline and configurable health rules exist.

## Cycle and Module progress

Current progress is completed / total * 100 for matching Work Items linked through active relation rows. Module totals are not additive.

Historical Burndown, Burnup and Velocity must use stored scope and state history. If complete history is absent, the UI must state Insufficient Data.

## Cycle time and lead time

Not implemented in the current report.

Planned definitions:

- Lead time: valid creation timestamp to first valid completion.
- Cycle time: first transition into a configured active State group to valid completion.
- Time in State: sum of closed state intervals, with the current interval ending at the report reference time.

These definitions require normalized historical intervals and versioned configuration.

## Automation

- Executions are grouped by stored status: success, failed or skipped.
- Rule totals use current enabled state.
- Average execution time is Insufficient Data until start and finish timestamps are stored.
- Worker payload content is never returned by the summary endpoint.

## Timezone and boundaries

Date filters are inclusive. Date values use Django's configured timezone for current-day evaluation. A future historical engine must store UTC timestamps and convert reporting boundaries with the workspace or project timezone.
