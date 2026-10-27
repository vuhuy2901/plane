# Testing-rejected automation repair (2026-10-26)

The reported project rule was enabled at revision 3, but its saved definition was
`created -> assign_user(project_lead)`, with no conditions. Its name said
"autmation create bug". The reported events were updates/state changes, so they
could not match this rule. The old runtime incorrectly described every trigger
mismatch as a condition failure.

## Corrected behavior

- Runtime and previews share trigger checks and condition checks. Execution
  snapshots record expected/actual values and distinguish trigger filters,
  conditions, missing work items, and action validation failures.
- Read-only previews use a selected or latest project-scoped recorded event.
  Without history, creation may be simulated explicitly; other changes are not
  invented from the current snapshot. Previews always report zero writes.
- The builder separates source events/conditions from the new work item's type,
  supplies a Task testing-rejected Bug starter, and shows the saved When/If/Then
  configuration. A sticky save footer distinguishes disabled saves from saving
  and enabling. Failed saves retain the draft.
- History shows meaningful mismatch explanations, including a factual fallback
  for older rows, and scopes created-item links to the execution's rule.
- IN TESTING and InProgress both belong to the `started` state group. Specific
  state transitions between them remain supported; group-entry-only rules now
  have an explicit warning in the editor.

## Live rule repair

The user's existing rule `4c8a5ab8-74d8-4b3c-8483-abe6681244d5` in project
`46fdbf9a-9260-4a15-a64a-a2cefe169142` was validated, updated to revision 4, and
left enabled:

1. When: IN TESTING -> InProgress.
2. If: source work item type is Task.
3. Then: create a Bug titled `Bug: {work_item_title}`, priority Medium, and link
   it to the source with `relates_to`. The Bug starts at its workflow's initial
   state.

The repair checked revision 3 before writing to avoid overwriting a newer edit.
The API's preview on the original Task #12 transition returned HTTP 200,
`valid=true`, both trigger/conditions matched, `action_count=1`, and `writes=0`.
No historical event was replayed, no source state was changed, and no live test
Bug was created. Old execution history remains unchanged. Future matching
transitions use the corrected rule. Worker and beat were reloaded; worker ping
returned `pong`, and beat dispatch runs every five seconds.

## Verification

- Backend: **132 passed**, including **35 new regression tests**. Coverage
  includes the actual issue PATCH API for Task IN TESTING -> InProgress, one Bug
  creation, disabled rules, retries, creation checkpoints, relation completion,
  duplicate deliveries, diagnostics, scope checks, and zero-write previews.
- Frontend: **21 unit/SSR tests passed** for draft preservation, save/enable
  behavior, presentation, history, starters, and diagnostics.
- Web TypeScript passed. Changed Python files passed Ruff checks/formatting;
  frontend formatting passed, with no lint errors (two pre-existing warnings).
- Live web and API returned HTTP 200. Vite served the updated automation modules
  as JavaScript, including the new save action and feedback components.
- Visual browser verification was unavailable: the computer-use tool stopped
  because it could not determine Chrome's current URL reliably. SSR tests and
  module compilation do not replace an interactive visual check.
- The temporary `plane-automation-check` test services were stopped afterward.

Reproduction commands:

```powershell
docker compose -p plane-automation-check -f docker-compose-test.yml run --rm api-tests pytest plane/tests/unit/services plane/tests/contract/app -k automation -q --tb=short
pnpm --filter @plane/i18n exec tsx --tsconfig ../../apps/web/tsconfig.json --test ../../apps/web/components/automation/rule-form.test.ts ../../apps/web/components/automation/rule-presentation.test.ts ../../apps/web/components/automation/rule-feedback.test.tsx
```

## Follow-up: created Bug placement

The user requested `Epic -> Task -> Bug`, retaining the Bug work item type.
The create action now accepts `parent_mode: "source"` to set the new item's
`parent_id` to the triggering Task. Omitted/`none` placement retains the old
top-level behavior for other saved rules. Placement is independent of link
relations such as `relates_to` and `blocking`. The Bug starter and Testing
Rejected template default to child placement.

The existing rule was updated to revision 5 with child placement enabled.
The execution checkpoint proved Bug #210 originated from Task #18; that active
Bug was reparented through the normal issue serializer. The source Task's parent
was verified before and after, and the real sub-issues API returned Bug #210.
The resulting hierarchy is Epic #3 -> Task #18 -> Bug #210. Deleted Bug #209 was
not restored. Worker code was reloaded after this repair.

The broader regression run also found that transition ordering accessed an
optional `WorkflowStateLayout` reverse relation as if it were a dictionary.
Workflows without canvas layout rows raised `RelatedObjectDoesNotExist`, breaking
parent automation. Layout coordinates now safely default to zero when missing
and read the model attributes when present, including cyclic graph ordering.
