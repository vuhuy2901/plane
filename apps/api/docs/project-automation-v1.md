# Project Automations — audit and implementation contract

## Parent–Subtask extension

The module exposes exactly eight triggers, seven conditions, and seven action groups. It includes `ALL_SUBTASKS_COMPLETED`, parent state changes, real Work Item relation events, comment events, scheduled daily/weekly runs, dry runs, bounded retries, and seven disabled templates. Existing persisted aliases are normalized when read so earlier rules remain understandable without replaying old events.

Events capture the original parent ID only when a typed Subtask enters the Completed **group** from a non-completed group. Editing an already completed Subtask does not repeat this trigger. Worker evaluation uses current, complete, unpaginated direct children; deleted children are excluded, but cross-project, archived, missing-state, inactive/unconfigured-type and non-Subtask children fail closed with skipped history. Only an active, typed Task parent in the same project is supported; Epic/Bug parents are excluded. No ancestor traversal or background scan of all work items is added.

Normal serializer family writes acquire the related parent lock before mutating a child; workers use the same parent-first order. Parent conditions and actions are evaluated while that lock is held. The worker rechecks all siblings, actor access and the parent's published outgoing workflow transitions. An already-at-target parent is skipped without an update or transition audit. Existing event deduplication and automation-origin suppression remain in use. History includes the source Subtask, related parent ID and skipped/failed reason. No data migration or automatic rule enablement is needed.

Run parent regressions with `pytest plane/tests/unit/services/test_automation_family.py` inside the isolated test stack. Browser interaction checks remain manual; automated tests cover API persistence/dry-run/history, worker concurrency, guards and frontend template transformation.

## Current status

Implemented: project rule CRUD/duplicate/status/validation/template APIs; persistent rules, events and execution history; serializer event capture for session and token writes; background Celery dispatch; eight triggers; seven conditions; seven action groups; three assignment modes; Work Item creation with idempotent blocking relation retry; scheduled bounded batches; project-resource validation; workflow enforcement; disabled-by-default creation/editing; and Templates / My Rules / History in the existing settings page. Existing maintenance controls remain present.

No rule has been created or enabled on live data during implementation. Migrations only add the automation tables/columns. Runtime tests use an isolated test database. Manual browser interaction testing remains outstanding; TypeScript and form transformation unit tests cover the UI code, not a full browser walkthrough.

Usage: open Project Settings → Automations → Templates → Auto Assign Task → Use Template, choose the Task type, choose Specific Member and a project member, then Save Disabled. Enable the saved rule explicitly. New tasks with no assignee produce events; existing Celery beat dispatches pending events every five seconds. History lists success/failed/skipped outcomes and immutable execution configuration/work-item snapshots. Disable stops future capture for that rule and prevents pending events from applying it. Editing disables the rule; re-enable is explicit.

The six templates reuse the original catalog. Project references must be explicitly selected; templates do not guess users, types, labels, or states by name. Test Rule lets the user choose one of the 200 most recent project work items and checks conditions, resource validity, actor access and state transitions without saving or dispatching tasks.

Set `PROJECT_AUTOMATIONS_ENABLED=0` in the API AND background worker environment to stop capture and processing. Existing issue APIs and maintenance automation remain independent. Local worker/beat containers now use their existing RabbitMQ service via `PLANE_BACKGROUND_WORKER` / `PLANE_WORKER_BROKER_URL`; API core-mode cookies, storage and eager legacy tasks are unchanged. Development background concurrency is capped at two Python processes.

Delivery is idempotent by `(event, rule_key)` and serialized per event with a PostgreSQL advisory lock. Effects and successful history commit in one transaction. Work Item creation stores a checkpoint before relation creation, so relation retry reuses the created Work Item. Configuration/workflow errors are terminal failed history; database operational errors retry with configurable bounded backoff. Automation-originated serializer writes do not emit further automation events. A rule revision/enable timestamp guard prevents delayed events from running a newly edited/re-enabled rule.

API base: `/api/workspaces/{slug}/projects/{project_id}/automations/`. Routes: `rules/`, `rules/{id}/` (GET/PUT/DELETE), `rules/{id}/{duplicate|status|validate|test}/` (POST), `templates/`, `resources/`, `history/?page=0&status=success`. PUT requires `expected_revision`; a stale write returns 409. History pages contain up to 50 entries. Only project administrators (including the existing workspace-admin policy) manage rules. Execution separately requires an active project member with work-item write access.

## Repository audit

- The existing Project Settings → Automations route already exists in `apps/web/app/routes/core.ts`. Its page renders `AutoArchiveAutomation` and `AutoCloseAutomation`, backed by project `archive_in` / `close_in` settings. Keep these controls working.
- `plane/bgtasks/issue_automation_task.py` implements archive/close maintenance and intake unsnoozing, not a configurable project rule engine.
- No reusable project automation rule/node/edge/activity models or CRUD endpoints were found in this self-hosted tree. Do not assume commercial Plane APIs exist locally. The automation module needs no graph/node/edge schema because it has one trigger and linear conditions/actions.
- Reuse Celery, its existing worker/broker and `transaction.on_commit`. Do not add a container or a second queueing system.
- `plane/services/workflow.py:transition_issue` is the state-change authority. Use it for automation state actions, with an explicitly authorized project member actor and audit metadata. Do not update the state column directly.
- Existing issue activity dispatches are not a complete durable automation event/outbox contract. Capture creation/update events only after all labels and assignees are saved, covering session API, token API, MCP and work item types. A model post-save hook alone misses final M2M state and can observe incomplete changes.

## Implementation design (audit record)

1. Models/migration: project-scoped rule with configuration/version/enabled timestamp/execution actor; durable event/outbox with event UUID and canonical before/after snapshot; execution history with unique `(event, rule)` and frozen rule configuration. Index project/time and delivery status. Preserve historical execution information when deleting a rule.
2. Project-admin API: template catalog, rule CRUD/duplicate/enable/disable, paginated history, and read-only Test Rule. Validate all referenced types/states/labels/members in the destination project on save AND at execution. Clones and template instances start disabled. Bind an explicit execution actor, recheck current membership/permissions, and record that actor in history.
3. Worker: dispatch durable events on commit; retry failed delivery without blocking issue saves; lock event/rule/issue, deduplicate executions, and recheck enabled state. Evaluate trigger and conditions against the event snapshot; read fresh issue state when validating actions. No replay of events older than the rule's enable timestamp. Rule failures must not abort other rules.
4. Actions: assign valid specific member/project lead/creator, respecting unassigned-only; workflow-gated state change; priority; additive project label; escaped plain-text comment; due date relative to the project timezone. Validate both actions before execution; run them and the success record atomically. On failure roll back actions and write failed history outside the rolled-back transaction. Test Rule uses the same preflight checks without performing any save, comment, activity, or queue dispatch.
5. Loop prevention: mark automation-originated operations and do not emit fresh automation events for them. This intentionally excludes rule chaining in this module. Delivery retries must not duplicate comments or any other action. Recheck actual changes to avoid no-op events.
6. UI: retain the existing maintenance controls, add Templates / My Rules / History, searchable local templates, card-based WHEN / IF / THEN form with project resource selectors, create/edit/duplicate/toggle/delete, Vietnamese-readable summary, and Test Rule results. Do not expose raw JSON as the primary authoring flow.
7. Kill switch: module flag disables event capture and execution, without disabling issue APIs or maintenance automations. Do not automatically enable any rule in existing projects.

## Regression and acceptance coverage

- All six user acceptance scenarios in the supplied brief, through both session and API-token writes.
- Assign modes, invalid/removed members, work type and project isolation, active label/state references, unassigned-only, and multi-assignee behavior.
- Workflow forward/return transitions and rejected direct completion, including conditions and project-role permissions; dry-run must leave no writes.
- Duplicate delivery and concurrent workers; disable-before-delivery; edits between event and execution; broker failure; rollback of the first action when the second action fails; automation-generated changes cannot recurse.
- Exact preservation of parent/subtask relationships, project IDs, Sprint/Cycle membership and untouched dates/priorities/estimates/assignees. Check Vietnamese and HTML escaping in comments.
- Frontend form unit tests, TypeScript, API contract tests and a real in-process Celery worker integration test are included. A browser walkthrough and production-scale load test are not established by these checks.

Current checks:

```powershell
docker compose -f docker-compose-test.yml run --rm api-tests pytest plane/tests/unit/services/test_automation_definition.py -q
docker compose -f docker-compose-test.yml run --rm api-tests pytest plane/tests/unit/services/test_automation_runtime.py plane/tests/contract/app/test_automation_rules_api.py plane/tests/contract/app/test_automation_events_api.py plane/tests/contract/app/test_automation_worker_integration.py -q
pnpm --filter @plane/i18n exec tsx --test ../../apps/web/components/automation/rule-form.test.ts
pnpm --filter web exec tsc --noEmit --pretty false
```

When changing model fields, add `--create-db` to the isolated pytest command because the repository's default `--reuse-db --nomigrations` otherwise retains an old test schema. Do not reset or remove the live database or Docker volumes.

Validation record (2026-10-23): targeted trigger, action, parent/subtask, relation, scheduler, API and real Celery worker tests passed; 48 runtime/parent/event tests passed in one run, three frontend form tests passed, TypeScript, OxLint, Ruff and Django checks passed. The latest isolated p95 benchmark measured create +3.96% and update +31.50% with event capture; the update path remains above the 10% target and is reported as unresolved rather than marked passed. CPU and memory samples are printed by the benchmark. Live validation found 373 work items, 187 Cycle assignments, five relations, no enabled rules/events, and no work item updated during implementation.
