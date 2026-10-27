import { useEffect, useState } from "react";
import { mutate } from "swr";
import { observer } from "mobx-react";
import { Button } from "@makeplane/propel/components/button";
import type { TWorkflowMapping, TWorkflowMappingConflict, TWorkflowStateMigration } from "@plane/types";
import { useWorkflow } from "@/hooks/store/use-workflow";
import { getWorkflowErrorMessage } from "./workflow-error";
import { workItemTypesKey } from "@/hooks/use-work-item-types";
import { WORK_TYPE_COLORS, workTypeColors } from "@/components/dropdowns/work-item-type/work-item-type-color";

type Props = { workspaceSlug: string; projectId: string };
const conflictKey = (item: TWorkflowMappingConflict) => `${item.issue_type_id}:${item.source_state_id ?? "none"}`;

export const WorkflowMapping = observer(function WorkflowMapping({ workspaceSlug, projectId }: Props) {
  const {
    workflows,
    issueTypes,
    fetchMappings,
    createIssueType,
    updateIssueType,
    deleteIssueType,
    saveMappings,
    saveHierarchy,
    previewMappings,
  } = useWorkflow();
  const [draftMappings, setDraftMappings] = useState<TWorkflowMapping[]>([]);
  const [draftLevels, setDraftLevels] = useState<Record<string, number>>({});
  const [newTypeName, setNewTypeName] = useState("");
  const [newTypeColor, setNewTypeColor] = useState(WORK_TYPE_COLORS[0]);
  const [message, setMessage] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [editingColor, setEditingColor] = useState(WORK_TYPE_COLORS[0]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [conflicts, setConflicts] = useState<TWorkflowMappingConflict[]>([]);
  const [stateChoices, setStateChoices] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setNewTypeColor(WORK_TYPE_COLORS[issueTypes.length % WORK_TYPE_COLORS.length]);
  }, [issueTypes.length]);

  useEffect(() => {
    setConflicts([]);
    setStateChoices({});
    void fetchMappings(workspaceSlug, projectId)
      .then(setDraftMappings)
      .catch((error: unknown) => {
        setErrorMessage(getWorkflowErrorMessage(error));
      });
  }, [fetchMappings, projectId, workspaceSlug]);

  useEffect(() => {
    setDraftLevels(Object.fromEntries(issueTypes.map((item) => [item.id, item.level])));
  }, [issueTypes]);

  const setMapping = (issueTypeId: string, workflowId: string) => {
    setConflicts([]);
    setStateChoices({});
    setMessage("");
    setDraftMappings((current) => {
      const withoutType = current.filter((item) => item.issue_type_id !== issueTypeId);
      return workflowId ? [...withoutType, { issue_type_id: issueTypeId, workflow_id: workflowId }] : withoutType;
    });
  };

  const addType = async () => {
    const name = newTypeName.trim();
    if (!name) return;
    setErrorMessage("");
    try {
      await createIssueType(workspaceSlug, projectId, name, newTypeColor);
      void mutate(workItemTypesKey(workspaceSlug, projectId));
      setNewTypeName("");
    } catch (error) {
      setErrorMessage(getWorkflowErrorMessage(error));
    }
  };

  const renameType = async (issueTypeId: string) => {
    const name = editingName.trim();
    if (!name) return;
    setBusyId(issueTypeId);
    setErrorMessage("");
    try {
      await updateIssueType(workspaceSlug, projectId, issueTypeId, name, editingColor);
      void mutate((key) => Array.isArray(key) && key[0] === "work-item-types" && key[1] === workspaceSlug);
      setEditingId(null);
    } catch (error) {
      setErrorMessage(getWorkflowErrorMessage(error));
    } finally {
      setBusyId(null);
    }
  };

  const removeType = async (issueTypeId: string, name: string) => {
    if (!window.confirm(`Delete work item type "${name}" from this project? This cannot be undone.`)) return;
    setBusyId(issueTypeId);
    setErrorMessage("");
    try {
      await deleteIssueType(workspaceSlug, projectId, issueTypeId);
      setDraftMappings((current) => current.filter((item) => item.issue_type_id !== issueTypeId));
    } catch (error) {
      setErrorMessage(getWorkflowErrorMessage(error));
    } finally {
      setBusyId(null);
    }
  };

  const showMigrationReview = (items: TWorkflowMappingConflict[]) => {
    setConflicts(items);
    setStateChoices(Object.fromEntries(items.map((item) => [conflictKey(item), item.suggested_target_id ?? ""])));
  };

  const persistMappings = async (confirmed = false) => {
    setErrorMessage("");
    setMessage("");
    setIsSaving(true);
    try {
      let migrations: TWorkflowStateMigration[] = [];
      if (!confirmed) {
        const preview = await previewMappings(workspaceSlug, projectId, draftMappings);
        if (preview.conflicts.length) {
          showMigrationReview(preview.conflicts);
          return;
        }
      } else {
        migrations = conflicts.map((item) => ({
          issue_type_id: item.issue_type_id,
          workflow_version_id: item.workflow_version_id,
          source_state_id: item.source_state_id,
          target_state_id: stateChoices[conflictKey(item)],
          work_item_count: item.work_item_count,
        }));
      }
      await saveMappings(workspaceSlug, projectId, draftMappings, migrations);
      setConflicts([]);
      setStateChoices({});
      setMessage("Mappings saved and workflows applied.");
    } catch (error) {
      setErrorMessage(getWorkflowErrorMessage(error));
      try {
        const preview = await previewMappings(workspaceSlug, projectId, draftMappings);
        showMigrationReview(preview.conflicts);
      } catch {
        // Keep the original request error visible if the preview is also unavailable.
      }
    } finally {
      setIsSaving(false);
    }
  };

  const persistHierarchy = async () => {
    setErrorMessage("");
    setMessage("");
    try {
      await saveHierarchy(
        workspaceSlug,
        projectId,
        issueTypes.map(({ id }) => ({ id, level: draftLevels[id] ?? 0 }))
      );
      setMessage("Hierarchy saved");
    } catch (error) {
      setErrorMessage(getWorkflowErrorMessage(error));
    }
  };

  return (
    <section className="mt-10 border-t border-subtle pt-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-medium">Work item type → Workflow</h3>
          <p className="text-sm mt-1 text-secondary">
            A workflow becomes effective only after it is published and explicitly mapped here.
          </p>
          <p className="text-xs mt-1 text-tertiary">
            Type names and colors are shared across the workspace; workflow mappings are specific to this project.
          </p>
        </div>
        <Button
          variant="primary"
          size="sm"
          stretch="auto"
          label={conflicts.length ? "Migrate states and save mappings" : "Save mappings"}
          disabled={isSaving || conflicts.some((item) => !stateChoices[conflictKey(item)])}
          onClick={() => void persistMappings(conflicts.length > 0)}
        />
      </div>
      <div className="mt-4 flex gap-2">
        <input
          type="color"
          aria-label="New work type color"
          title="Work type color"
          className="h-9 w-10 cursor-pointer rounded border border-subtle"
          value={newTypeColor}
          onChange={(event) => setNewTypeColor(event.target.value)}
        />
        <input
          className="text-sm h-9 min-w-56 rounded-md border border-subtle bg-surface-1 px-3"
          value={newTypeName}
          onChange={(event) => setNewTypeName(event.target.value)}
          placeholder="New type, e.g. Bug"
        />
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label="Add work item type"
          onClick={() => void addType()}
        />
        {message && <span className="text-xs self-center text-secondary">{message}</span>}
      </div>
      {errorMessage && (
        <p role="alert" className="text-sm text-red-500 mt-3">
          {errorMessage}
        </p>
      )}
      {conflicts.length > 0 && (
        <div
          role="region"
          aria-label="Review state mappings before applying workflows"
          className="mt-5 rounded-lg border border-subtle bg-surface-2 p-4"
        >
          <h4 className="text-sm font-medium">Choose states for existing work items</h4>
          <p className="text-sm mt-1 text-secondary">
            {conflicts.reduce((total, item) => total + item.work_item_count, 0)} work items use states outside the
            selected workflows. Choose a target state for each row below. These changes will be recorded in work item
            history.
          </p>
          <div className="mt-3 divide-y divide-subtle">
            {conflicts.map((item) => (
              <div key={conflictKey(item)} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="text-sm">
                  <div className="font-medium">
                    {item.issue_type_name} · {item.source_state_name} ({item.work_item_count} item)
                  </div>
                  <div className="text-xs mt-1 text-secondary">
                    {item.source_state_group ?? "No group"} → {item.workflow_name}
                  </div>
                </div>
                <select
                  aria-label={`Target state for ${item.issue_type_name}: ${item.source_state_name}`}
                  className="text-sm h-9 min-w-64 rounded-md border border-subtle bg-surface-1 px-2"
                  value={stateChoices[conflictKey(item)] ?? ""}
                  disabled={isSaving}
                  onChange={(event) =>
                    setStateChoices((current) => ({ ...current, [conflictKey(item)]: event.target.value }))
                  }
                >
                  <option value="">Choose a workflow state…</option>
                  {item.target_states.map((state) => (
                    <option key={state.id} value={state.id}>
                      {state.name} ({state.group})
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <Button
              variant="primary"
              size="sm"
              stretch="auto"
              label="Migrate states and save mappings"
              disabled={isSaving || conflicts.some((item) => !stateChoices[conflictKey(item)])}
              onClick={() => void persistMappings(true)}
            />
            <Button
              variant="secondary"
              size="sm"
              stretch="auto"
              label="Cancel"
              disabled={isSaving}
              onClick={() => {
                setConflicts([]);
                setStateChoices({});
              }}
            />
          </div>
        </div>
      )}
      <div className="mt-4 overflow-hidden rounded-lg border border-subtle">
        {issueTypes.length === 0 && <div className="text-sm p-5 text-secondary">No project work item types yet.</div>}
        {issueTypes.map((issueType) => {
          const selected = draftMappings.find((item) => item.issue_type_id === issueType.id)?.workflow_id ?? "";
          return (
            <div
              key={issueType.id}
              className="flex flex-wrap items-center justify-between gap-2 border-b border-subtle p-3 last:border-b-0"
            >
              {editingId === issueType.id ? (
                <div className="flex min-w-0 flex-1 items-center gap-2">
                  <input
                    type="color"
                    aria-label="Work type color"
                    className="h-9 w-10 shrink-0 cursor-pointer rounded border border-subtle"
                    value={editingColor}
                    onChange={(event) => setEditingColor(event.target.value)}
                  />
                  <input
                    aria-label="Work item type name"
                    className="text-sm h-9 min-w-0 rounded-md border border-subtle bg-surface-1 px-3"
                    value={editingName}
                    onChange={(event) => setEditingName(event.target.value)}
                    onKeyDown={(event) => event.key === "Enter" && void renameType(issueType.id)}
                  />
                  <Button
                    variant="primary"
                    size="sm"
                    stretch="auto"
                    label="Save"
                    disabled={!editingName.trim() || busyId === issueType.id}
                    onClick={() => void renameType(issueType.id)}
                  />
                  <Button
                    variant="secondary"
                    size="sm"
                    stretch="auto"
                    label="Cancel"
                    onClick={() => setEditingId(null)}
                  />
                </div>
              ) : (
                <div className="min-w-0 flex-1">
                  <span
                    className="text-xs inline-block rounded px-2 py-1 font-medium"
                    style={workTypeColors(issueType.color)}
                  >
                    {issueType.name}
                  </span>
                  <div className="text-xs text-tertiary">Project-scoped mapping</div>
                </div>
              )}
              <div className="flex shrink-0 items-center gap-2">
                <select
                  aria-label={`Workflow for ${issueType.name}`}
                  className="text-sm h-9 min-w-64 rounded-md border border-subtle bg-surface-1 px-2"
                  value={selected}
                  disabled={isSaving}
                  onChange={(event) => setMapping(issueType.id, event.target.value)}
                >
                  <option value="">Legacy state behavior</option>
                  {workflows
                    .filter((workflow) => workflow.active_version_id)
                    .map((workflow) => (
                      <option key={workflow.id} value={workflow.id}>
                        {workflow.name}
                      </option>
                    ))}
                </select>
                {editingId !== issueType.id && (
                  <>
                    <Button
                      variant="secondary"
                      size="sm"
                      stretch="auto"
                      label="Edit type"
                      onClick={() => {
                        setEditingId(issueType.id);
                        setEditingName(issueType.name);
                        setEditingColor(issueType.color ?? WORK_TYPE_COLORS[0]);
                        setErrorMessage("");
                      }}
                    />
                    <Button
                      variant="secondary"
                      size="sm"
                      stretch="auto"
                      label="Delete"
                      disabled={busyId === issueType.id || issueType.is_default}
                      onClick={() => void removeType(issueType.id, issueType.name)}
                    />
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-8 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-medium">Work item hierarchy</h3>
          <p className="text-sm mt-1 text-secondary">
            Assign each type to a parent-child level. Level 0 is the top level; higher levels are children.
          </p>
        </div>
        <Button
          variant="primary"
          size="sm"
          stretch="auto"
          label="Save hierarchy"
          onClick={() => void persistHierarchy()}
        />
      </div>
      <div className="mt-4 overflow-hidden rounded-lg border border-subtle">
        {issueTypes.map((issueType) => (
          <div
            key={issueType.id}
            className="flex items-center justify-between border-b border-subtle p-3 last:border-b-0"
          >
            <span className="text-sm font-medium">{issueType.name}</span>
            <select
              aria-label={`Hierarchy level for ${issueType.name}`}
              className="text-sm h-9 min-w-48 rounded-md border border-subtle bg-surface-1 px-2"
              value={draftLevels[issueType.id] ?? issueType.level}
              onChange={(event) => {
                const level = Number(event.target.value);
                setDraftLevels((current) => ({ ...current, [issueType.id]: level }));
              }}
            >
              {[0, 1, 2, 3, 4].map((level) => (
                <option key={level} value={level}>
                  Level {level}
                  {level === 0 ? " · Top-level" : " · Child"}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>
    </section>
  );
});
