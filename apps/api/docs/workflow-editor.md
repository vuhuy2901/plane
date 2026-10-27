# Directed workflow editor

## Graph and persistence

- Connections begin at a filled `out-*` port and end at an outlined `in-*` port. Strict React Flow connections cannot start at incoming ports. The original drag node is checked again in `onConnect`.
- Node keys, transition IDs, endpoints and node coordinates are persisted independently. Saving reconciles rows rather than deleting and recreating the graph. Deleting an edge does not delete a node; undo can restore the original IDs.
- Opposite directions are independent transitions with separate curved lanes. Duplicate ordered source–target pairs are rejected by both editor and API, even when ports differ.
- Layout changes only on drag or the explicit **Auto Layout** action. **Template** changes the draft only and asks before replacing a nonempty draft. It never automatically replaces a published graph.
- Legacy port names are converted to role-specific ports only in the editor. Stored source/target directions are never inferred from positions, groups or array order. The migration adds only a revision column; it does not rewrite existing graphs.
- Old duplicate directions are listed for explicit review by transition ID. Remove the unwanted draft edge before saving; published history is never automatically deduplicated. A read-only audit found 5 duplicate pairs in published Scrum Workflow versions in ECommerce, with no missing layouts or cross-version edges.

## Concurrent writes

`GET .../workflows/{id}/draft/` returns `id` and `revision`. The editor sends both when saving or publishing:

```json
{
  "draft_id": "<loaded draft UUID>",
  "expected_revision": 0,
  "states": [],
  "transitions": []
}
```

The API locks the workflow and draft; a mismatched token returns HTTP 409 without writing. Each successful save increments `revision`. The editor locks editing during save/publish and keeps unsaved changes on failure. Explicit reload asks before discarding unsaved edits.

Legacy API callers without revision tokens remain accepted for compatibility; they do not get optimistic-concurrency protection. New integrations should always send both tokens.

## Work item states

- Existing-item state options are fetched from published outgoing transitions each time the picker opens/searches. Newly created items start at the mapped workflow's start state.
- Web and API-token updates enforce transitions server-side. Changing type and state in one PATCH cannot bypass the current graph. The selected target must also belong to the destination type's workflow when changing types.
- Successful transitions are audited. There is no implicit admin override. Existing optimistic-update stores roll back rejected updates; the picker displays a failure message.
- Graph saves do not modify issues, hierarchy, assignments, estimates, dates, cycles, or mappings. States outside a newly selected workflow still require explicitly reviewed mapping/migration; they are not silently moved.

## Regression checks

```powershell
docker compose -f docker-compose-test.yml run --rm api-tests pytest plane/tests/contract/app/test_workflow_graph_api.py plane/tests/contract/app/test_workflow_designer_api.py plane/tests/contract/app/test_workflow_transition_bypass.py plane/tests/unit/services/test_workflow.py plane/tests/unit/services/test_workflow_mapping.py plane/tests/unit/services/test_workflow_graph.py -q
pnpm --filter @plane/i18n exec tsx --test ../../apps/web/components/workflows/workflow-graph.test.ts
pnpm --filter @plane/types build
pnpm --filter web exec tsc --noEmit --pretty false
```

Manual browser QA: connect in all four directions, add reciprocal edges, move nodes, save/reload, delete/undo, and check state choices before and after a transition. Automated graph tests do not replace this browser drag-and-drop check.
