# Analytics User Guide

## Open Analytics

Choose Analytics in the Workspace sidebar. The page contains:

1. Overview
2. Work Items
3. Members
4. Projects
5. Cycles
6. Modules
7. Workflow
8. Automation
9. Reports

Only data from projects you can access is included.

## Filters

Use the filters above the tabs:

- Project selects one or more projects.
- Duration selects Yesterday, Last 7 days, Last 30 days or Last 3 months.
- Count mode selects All work items or Top-level only.

All visible P0 report values use the same selected scope.

## Overview

Overview displays:

- Total, completed, in-progress, unstarted and overdue Work Items.
- Completion rate.
- Total, open and completed Bugs.
- Active members and active Cycles.
- Average completion time when data is sufficient.
- Created vs resolved trend.
- State, priority and Work Item Type distributions.

Bug metrics come from Work Item Type. Moving a Task from Testing to In Progress does not turn it into a Bug.

## Members

Members shows current assigned, completed, in-progress, overdue and Bug workload. A Work Item with two assignees counts once for each assignee. Do not sum the member table to calculate unique Work Items.

The table is for workload visibility, not employee ranking.

## Projects

Projects compares total, completed, overdue, open Bugs and progress. Project health is not guessed when baseline and health rules are absent.

## Cycles and Modules

These tabs compare current scope and progress. A Work Item may belong to multiple Modules, so Module totals must not be added together to derive the Project total.

## Workflow

Workflow currently reports verified reopen transitions. Time in State and bottleneck trends remain unavailable until historical intervals are normalized.

## Automation

Automation reports rule status and execution outcomes. Average duration shows Insufficient Data because current execution records do not have both start and finish timestamps.

## Reports and CSV

Reports can download filtered Project and Member summaries as CSV. The Work Items tab retains its existing chart and table CSV exports.

## Count mode

- All work items includes child Work Items.
- Top-level only excludes any Work Item that has a parent.

Use one mode consistently when comparing periods.

## Data notes

The Reports tab lists limitations returned by the API. These notes are part of the report and explain where historical data is incomplete.
