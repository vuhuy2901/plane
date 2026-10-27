# Automation full audit

Audit date: 2026-10-23. Scope: current repository and read-only inspection of local QLDP project. No production code or user data changed for this audit. “Confirmed” means supported by inspected code or local database; the reported empty dropdown has not been reproduced in a browser session.

## A. Architecture overview

The project settings page mounts `ProjectAutomationRules` (`apps/web/components/automation/project-rules.tsx`). On project change, it requests rules, templates and resources together via `AutomationService` (`apps/web/services/automation.service.ts`). Resources come from `AutomationResourcesAPIView` at `workspaces/<slug>/projects/<project_id>/automations/resources/` (`apps/api/plane/app/urls/automation.py`), guarded by `ProjectAdminPermission`. The builder uses resource IDs as native `<option value>` values; rule definitions are JSON sent to rules endpoints. `AutomationDefinitionInput` and `validate_definition` enforce syntax and project resources before saving/enabling.

`IssueCreateSerializer` calls `capture_context` before writes and `emit_event` afterward. Comment, relation and schedule adapters create other events. `ProjectAutomationEvent` stores before/after snapshots and candidate rule revisions. `process_event` locks and evaluates the event; `prepare_actions` validates resources/workflow; `ProjectAutomationExecution` records outcomes. Worker polling is in `apps/api/plane/bgtasks/project_automation_task.py`. The feature gate is `PROJECT_AUTOMATIONS_ENABLED` (default enabled).

Actual tables: `project_automation_rules` (definition JSON, enabled, revision, actor), `project_automation_events` (snapshots, candidates, deduplication key, progress), `project_automation_executions` (unique event/rule history). Related models/tables: `ProjectIssueType`/`IssueType`, `State`, `ProjectMember`, `Label`, `Issue`, `IssueAssignee`, `IssueLabel`, `Cycle`, `Module` (`apps/api/plane/db/models`). No separate condition/action tables.

## B. Feature inventory

| Feature | Frontend | Backend | Database | Status | Evidence |
|---|---|---|---|---|---|
| Rule CRUD, enable, duplicate, test, history | Yes | Yes | Three automation tables | Implemented | `project-rules.tsx`, `automation.py`, `automation.py` model |
| Dynamic project types/states/members/labels | Resources request | Resources API | Project-scoped models | Implemented with loading defects | `project-rules.tsx:181`, `automation.py:146` |
| Eight triggers | Eight labels | Eight registry entries | Event JSON | Implemented; paths differ | `project-rules.tsx:18`, `automation_definition.py:10`, runtime/events/schedule |
| Seven actions | Seven editors | Seven validators/executors | Issue/relations/comments | Implemented with constraints | `automation_definition.py:45`, `automation_runtime.py:239` |
| Cycle/module/boolean/number conditions | No editor | No registry entry | Models exist | Unsupported | `automation_definition.py:30`, `project-rules.tsx:35` |
| Previous/current arbitrary field condition | No editor | No evaluator | Before/after event snapshots | Unsupported (state transition trigger supported) | `automation_runtime.py:191` |

## C. Dynamic values audit and reported symptom

Trace: `choices("work_item_type")` returns `resources.types` (`project-rules.tsx:236`); `Select` renders one option per element (`:81`). `resources.types` is populated only after `Promise.all([rules, templates, resources])` resolves (`:181`). API builds it from active `ProjectIssueType` rows for the requested project (`automation.py:146`). QLDP local data has four active mappings: Task, Bug, EPIC, Sub-task; zero automation rules (read-only DB query). Thus missing QLDP type mappings are ruled out. A failed rules/templates request, failed resources request, stale client state, or wrong project context can leave the dropdown empty. The exact browser failure remains unconfirmed because no browser session/network trace was available.

| Field | Source | Actual options in builder | UI result / issue | Priority |
|---|---|---|---|---|
| Work Item Type | Active `ProjectIssueType.issue_type` | Project types by UUID/name; QLDP: Task, Bug, EPIC, Sub-task | Can be empty after any grouped fetch failure; no field-level error | P1 |
| State / State Group | Project `State`; five group constants | State UUID/name plus `group:*` sentinels | Project states dynamic; groups are fixed schema values | P2 |
| Priority | `PRIORITIES` registry | none/low/medium/high/urgent | Static enum intentionally | OK |
| Assignee | Active project members role >=15 | User UUID/display name | Project scoped; old/deactivated selection has no fallback display | P2 |
| Label | Project `Label` | Label UUID/name | Project scoped; old/deleted selection has no fallback | P2 |
| Cycle / Module | Models exist | None | Not supported by condition/action registry | New scope |
| Date / Number | Native date/number inputs for due date | ISO date or 0–3650 days | Backend validates; input bounds shared across text/date controls | P2 |
| Boolean | `ALL_SUBTASKS_COMPLETED` uses `is_true` | No value input | Only this specialized predicate; no general boolean field | Supported narrowly |
| Previous / Current | Event `before_snapshot`/`snapshot` | Transition fields in trigger; conditions see current only | Arbitrary old/new comparisons unsupported | New scope |
| Work item relation target | Last 200 issues | ID/name | Valid older issue IDs hidden; saved selection may appear blank | P2 |

The resources response is unpaginated for types/states/labels/members; work item targets are capped at 200. Type options originate from the same project mapping used by work item type assignment, but the builder excludes inactive types. Backend rejects inactive/unmapped types on save. No loading/no-values/failure/invalid-selection distinction is rendered per selector.

Dependency behavior from source: changing condition field reconstructs `{field, operator}` and clears value (A). Changing operator reconstructs `{field, operator}` and drops a still-valid value (B: confirmed bug). Project prop change triggers new fetch but does not reset `resources`, `draft`, `editing` or `testIssue`; the previous project's options/draft can remain visible until fetch resolves or even after a failed fetch (C: confirmed bug). Editing clones saved conditions/actions, then selects by ID; missing IDs have no named fallback (D: possible stale-resource issue). All three fetches share one `Promise.all` catch, so 401/403/404/500/timeout from any call leaves resources at old/empty state and only sets a generic global message (E: confirmed). Response-shape validation is absent; malformed `types` can crash the editor.

## D. Trigger audit

| Trigger | Event source / payload | Execution support | Status |
|---|---|---|---|
| `created` | Issue serializer, after snapshot | Type filter, candidate revision | Implemented |
| `updated` | Issue serializer, before/after snapshots | Optional `field` compares selected key | Implemented; inspect field coverage per write path |
| `state_changed` | Issue serializer, state/group before/after | From/to state/group, entered group, subtask filter | Implemented |
| `assignee_changed` | Issue serializer, assignee arrays | Previous/new membership or unassigned | Implemented |
| `priority_changed` | Issue serializer, old/new priority | From/to filter | Implemented |
| `comment_added` | `automation_events.comment_created` | Author filter; comment-ID dedup key | Implemented |
| `work_item_linked` | `automation_events.relation_created` | Relation/source/target filter | Implemented; direction normalized |
| `scheduled` | `automation_schedule.dispatch_schedules` | Daily/weekly project occurrence | Implemented; filters evaluated on current snapshot |

`matches_trigger` for `updated` compares only the configured field (`automation_runtime.py:144`); a title-only event must not match a state-only rule. `state_changed` compares actual old/new state IDs and supports `In Testing → In Progress` when those states exist in the project. Event candidates and revisions limit execution to eligible rules; `automation_origin` suppresses cascades, event/rule uniqueness and advisory lock suppress duplicate delivery. Comment/relation dedup keys and scheduled occurrence handling should remain in regression coverage.

## E. Condition audit

| Condition | Operators | Value source / type | Backend evaluation | Status |
|---|---|---|---|---|
| Work item type | equals, not_equals, empty, not_empty | Project type UUID | Current snapshot type | Supported |
| State | equals, not_equals, empty, not_empty | Project state UUID or `group:*` | Current state/group | Supported |
| Priority | equals, not_equals, empty, not_empty | Priority enum | Current string | Supported |
| Assignee | equals, not_equals, contains, does_not_contain, empty, not_empty | Project member UUID | Current UUID list | Supported |
| Label | Same as assignee | Project label UUID | Current UUID list | Supported |
| Due date | equals, not_equals, empty, not_empty, overdue, within_next_days | ISO date or days integer | Current target_date | Supported |
| All subtasks completed | is_true | No value | `completed_parent` | Supported in state-change rules |

`ConditionInput` rejects unrecognized fields/operators and most missing/extra values (`automation_definition.py:74`). `validate_definition` checks project ownership/active status (`automation_rules.py`). Multiple conditions are AND; empty list matches. Runtime reads current event snapshot only (`automation_runtime.py:191`). A concrete risk: `capture_context` on update uses only supplied changed fields for non-core snapshot data, although rules may need labels/assignees/due date as conditions; `matches_conditions` can then see `None` for an unchanged field. Verify with a focused test before changing snapshot capture. Deleted resources are revalidated in `prepare_actions`, which can fail an enabled rule and produce execution history.

## F. Action audit

| Action | Target values | Validation / execution | Status |
|---|---|---|---|
| Assign user | Project member or lead/creator | Active member checked at run time; optional replace/only-unassigned | Supported |
| Change state | Project state UUID, current/parent | Workflow transition checked at run time | Supported with workflow restriction |
| Change priority | Priority enum | Serializer update | Supported |
| Manage labels | Project label UUID, add/remove | Project reference checked; serializer update | Supported |
| Add comment | Text/template tokens | Escaped HTML; execution actor | Supported |
| Set due date | Fixed ISO date or relative days/timezone | Start-date ordering checked | Supported |
| Create work item | Project type/state/member/priority; optional relation | Serializer + workflow start state + checkpoint | Supported, state choice can fail at runtime |

`create_work_item` is generic; creating a Bug means selecting the actual project Bug type. State/type selector currently offers every project state pair, including choices inconsistent with that type's workflow start state. Execution actor must still be active project member; API management requires `ProjectAdminPermission`. Failures become execution rows; multi-action writes use transactions/checkpoint for created items (`automation_runtime.py:392`). No unconditional action on another project is exposed.

## G. Bug list

| ID | Severity | Root cause and evidence | Reproduce / actual versus expected | Proposed fix; regression risk |
|---|---|---|---|---|
| AUT-01 | P1 | Grouped `Promise.all` and empty initial resources, `project-rules.tsx:154,181` | Make templates request fail, open Type Value: placeholder only, generic message. Expected independently loaded types/error state. | Fetch resources independently, validate shape, show loading/failure/empty; risk: concurrent response ordering. |
| AUT-02 | P1 | Project change retains resource/draft state, `project-rules.tsx:154-198` | Navigate A→B while editor open: A's options/IDs persist. Expected B-only resources and cleared or safely scoped draft. | Key editor by project and guard request generation; risk: unsaved draft loss, prompt appropriately. |
| AUT-03 | P2 | Operator handler drops value, `project-rules.tsx:285` | State Is X → Is Not: state disappears. Expected valid X retained. | Preserve value where input type remains compatible; risk: no-value operators require clearing. |
| AUT-04 | P2 | Native `Select` has no missing-ID display, `project-rules.tsx:81` | Edit rule with deleted/inactive value: placeholder appears. Expected explicit invalid reference. | Render unavailable saved option and block enable with explanation; risk: preserving legacy rules. |
| AUT-05 | P2 | Work item target list capped at 200, `automation.py:178` | Edit relation filter targeting older item: ID absent. Expected resolvable saved target. | Search/paginate endpoint plus ID lookup; risk: query load/authorization. |
| AUT-06 | P1 suspected | Narrow `capture_context` snapshot fields may omit unchanged condition field, `automation_runtime.py:69,191` | Update title under rule with Label condition; determine whether before/after label list exists. Expected condition evaluates actual current labels. | Capture all fields needed by candidate conditions; risk: snapshot query cost. |
| AUT-07 | P2 | Create action state list not filtered by type workflow, `project-rules.tsx:809`, `automation_runtime.py:332` | Choose valid project state incompatible with selected type, then run: failure. Expected only legal start states or immediate validation. | Resolve type workflow start state in resource/UI and validate pair on save; risk: legacy definitions. |
| AUT-08 | P1 reported, cause unconfirmed | User reports empty Type Value; local QLDP has four active mappings | User path: Updated→Any→Type→Is→Value, only placeholder. Expected four QLDP types. | Capture browser Network response/context and correlate with AUT-01; do not assert DB absence. |

## H. Test results and matrix

| Test ID | Test case | Expected | Actual | Result |
|---|---|---|---|---|
| T01 | Template draft unit test | Editable draft | Passed | PASS |
| T02 | Existing-rule cloning unit test | Metadata omitted, no mutation | Passed | PASS |
| T03 | Parent template unit test | Target retained | Passed | PASS |
| T04 | Read-only QLDP type mapping | Four active project types | Task/Bug/EPIC/Sub-task | PASS |
| T05 | Browser reproduction and 401/403/404/500/timeout/invalid JSON | Distinct states | No browser session available | NOT RUN |
| T06 | Condition field/operator/project/reload component scenarios A–D | Correct values/reset | Code inspected only | NOT RUN |
| T07 | Every trigger, operator, action across two projects | Project isolation, correct execution | Isolated test suite not run; local DB must not be altered | NOT RUN |
| T08 | Duplicate delivery, loop guard, create checkpoint, stale references | Once-only effects and logged failures | Existing tests identified, not executed | NOT RUN |
| T09 | Type/state resource endpoint across two configurations | Scoped and complete | QLDP DB query only; no authenticated endpoint call | NOT RUN |

Executed: `tsx --test apps/web/components/automation/rule-form.test.ts` (3 tests passed). Existing candidate tests for the next phase: `apps/api/plane/tests/unit/services/test_automation_{definition,runtime,extended,family}.py`, `apps/api/plane/tests/contract/app/test_automation_{rules,events,extended,worker_integration}_api.py`. Use the isolated test database; never the local user database. Add UI tests for each dynamic selector and errors, API tests with two distinct projects/states/types, execution tests for eight triggers and seven actions, invalid operators/resources, stale/deleted IDs, and cross-project writes. E2E should include create/edit/reload, project switch, state transition, duplicate delivery, and failed-resource recovery.

## I. Prioritized implementation plan

1. **P1: resource reliability.** In `project-rules.tsx` split resource request state from rules/templates, reset/key it by project, show loading/empty/error/invalid saved value, validate response shape. Add component tests for empty, 401/403/404/500/timeout/malformed response and project A→B. Acceptance: QLDP Type Value displays its four active types when resources succeeds; errors never masquerade as empty options.
2. **P1: snapshot completeness (after focused regression test).** In `automation_runtime.py` collect condition fields for before/after snapshots on every relevant update path. Add tests for updating one field with unchanged label/assignee/due-date conditions, and state-only updated-field trigger. Acceptance: matching uses actual current values without false matches.
3. **P2: edit/dependency correctness.** In `project-rules.tsx` retain compatible value on operator change, clear incompatible value on field change, preserve and label invalid saved IDs. In `automation.py`, support lookup/search for older work item targets. Add component/API tests. Acceptance: scenarios A–D pass across two projects.
4. **P2: action legality.** Restrict create action's initial state to the selected type's workflow start and validate on save in `automation_rules.py`; revalidate on run. Add API and runtime tests. Acceptance: invalid state/type combinations cannot be enabled, valid Bug creation succeeds once.
5. **Verification gate.** Run the existing isolated backend suites, frontend component tests and E2E flows; document exact command/results. Preserve saved definitions and history; migration only if a validated requirement demands schema changes. None is indicated by this audit.

## J. Implementation verification (2026-10-23)

The requested fixes were implemented without a database migration or modifications to local user data.

| Audit item | Verified outcome | Changed files |
|---|---|---|
| AUT-01 | Rules, templates and resources now load independently. Resources have loading, error, retry and empty states; malformed top-level resource arrays are rejected. Saving requires loaded resources. | `apps/web/components/automation/project-rules.tsx` |
| AUT-02 | Project-keyed builder remounts its draft, selections and resource state when workspace/project changes. Late responses target the retired instance. Backend rules and resources remain scoped by workspace/project and admin permission. | `project-rules.tsx`; existing `apps/api/plane/app/views/automation.py` permission/scope checks |
| AUT-03 | Compatible operator changes keep the value; no-value operators drop it; field changes reset it. | `project-rules.tsx`, `rule-form.ts` |
| AUT-04 | A saved ID missing from current options is displayed as an unavailable selection instead of silently becoming the placeholder; backend still rejects invalid references. | `project-rules.tsx` |
| AUT-06 | **Confirmed by failing test before fix.** Unchanged label condition was absent from title-update event snapshot. `capture_context` now includes candidate condition fields as well as edited fields. The same test passes afterward. | `apps/api/plane/services/automation_runtime.py`, `test_automation_runtime.py` |
| AUT-07 | Resources expose each type's workflow start state; create action state picker narrows to it. Save-time validation rejects mismatched type/state combinations, with runtime revalidation retained. | `apps/api/plane/app/views/automation.py`, `services/automation_rules.py`, `apps/web/services/automation.service.ts`, `project-rules.tsx` |
| AUT-08 | Backend resources query and isolated API test confirm project-scoped active types; QLDP read-only query found Task, Bug, EPIC and Sub-task. Browser-level reproduction remains unavailable, so this symptom is not claimed independently verified in the UI. | API resource test; AUT-01 fix |

Test evidence:

| Test | Result |
|---|---|
| Frontend `tsx --test apps/web/components/automation/rule-form.test.ts` | PASS: 4 tests |
| Isolated backend 8 Automation test modules (`pytest ... -q`) | PASS: 96 tests, 48 existing factory deprecation warnings |
| New snapshot regression before fix | FAIL as expected: priority stayed `none` |
| New snapshot regression after fix | PASS |
| New create-action workflow-state validation test | PASS |
| New two-project resources API test | PASS |
| Web TypeScript `tsc --noEmit` | PASS |
| API Ruff checks | PASS |
| Browser end-to-end WHEN→IF→THEN→SAVE→EXECUTE→LOG | NOT RUN: no accessible browser session for authenticated local app |

Manual UI checklist for an authorized project admin: open QLDP Automations; create an Updated/Any rule with Work Item Type Is and confirm four options; change Is to Is Not and confirm selection persists; switch to State and confirm type ID clears; switch projects and confirm options change; simulate a resources failure and use Retry; save/reopen the rule; make a test transition and inspect execution history. Keep the test rule disabled after checking unless intended for live use.

Remaining limitations and risks: old linked work items beyond the 200-item resource limit remain absent from the optional relation target dropdown (AUT-05); browser E2E and live authenticated network trace were unavailable; a workflow mapping change can invalidate an existing create action, now detected when validating/enabling; broader event snapshots add read cost. Existing worker integration timing output observed update p95 increase of 33.27% in its fixture, so performance should be monitored with realistic project rule counts before large-scale rollout.
