import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { Button } from "@makeplane/propel/components/button";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
import { useAppRouter } from "@/hooks/use-app-router";
import { useWorkflow } from "@/hooks/store/use-workflow";
import { WorkflowMapping } from "@/components/workflows/workflow-mapping";
import { getWorkflowErrorMessage } from "@/components/workflows/workflow-error";
import { useUserPermissions } from "@/hooks/store/user";
import type { Route } from "./+types/page";
import { WorkflowsProjectSettingsHeader } from "./header";

function WorkflowsSettingsPage({ params }: Route.ComponentProps) {
  const { workspaceSlug, projectId } = params;
  const router = useAppRouter();
  const { workflows, isLoading, fetchWorkflows, createWorkflow, updateWorkflow, deleteWorkflow } = useWorkflow();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const [isCreating, setIsCreating] = useState(false);
  const [name, setName] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const canAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT);

  useEffect(() => {
    if (canAdmin) void fetchWorkflows(workspaceSlug, projectId);
  }, [canAdmin, fetchWorkflows, projectId, workspaceSlug]);

  if (workspaceUserInfo && !canAdmin) return <NotAuthorizedView section="settings" isProjectView className="h-auto" />;

  const handleCreate = async () => {
    const trimmedName = name.trim();
    if (!trimmedName) return;
    try {
      setErrorMessage("");
      const workflow = await createWorkflow(workspaceSlug, projectId, trimmedName);
      router.push(`/${workspaceSlug}/settings/projects/${projectId}/workflows/${workflow.id}/`);
    } catch (error) {
      setErrorMessage(getWorkflowErrorMessage(error));
    }
  };

  const handleRename = async (workflowId: string) => {
    const trimmedName = editingName.trim();
    if (!trimmedName) return;
    setBusyId(workflowId);
    setErrorMessage("");
    try {
      await updateWorkflow(workspaceSlug, projectId, workflowId, trimmedName);
      setEditingId(null);
    } catch (error) {
      setErrorMessage(getWorkflowErrorMessage(error));
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (workflowId: string, workflowName: string) => {
    if (!window.confirm(`Delete workflow "${workflowName}"? This cannot be undone.`)) return;
    setBusyId(workflowId);
    setErrorMessage("");
    try {
      await deleteWorkflow(workspaceSlug, projectId, workflowId);
    } catch (error) {
      setErrorMessage(getWorkflowErrorMessage(error));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <SettingsContentWrapper header={<WorkflowsProjectSettingsHeader />}>
      <PageHead title="Workflows" />
      <SettingsHeading
        title="Workflows"
        description="Design and publish transition rules independently for this project. No workflow is created automatically."
        control={
          <Button
            variant="primary"
            size="md"
            stretch="auto"
            label="Create workflow"
            onClick={() => setIsCreating(true)}
          />
        }
      />
      {isCreating && (
        <div className="mt-6 flex items-center gap-2 rounded-lg border border-subtle bg-surface-1 p-4">
          <input
            className="text-sm focus:border-accent h-9 min-w-64 rounded-md border border-subtle bg-surface-2 px-3 outline-none"
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && void handleCreate()}
            placeholder="Workflow name"
          />
          <Button
            variant="primary"
            size="sm"
            stretch="auto"
            label="Create"
            disabled={!name.trim()}
            onClick={() => void handleCreate()}
          />
          <Button variant="secondary" size="sm" stretch="auto" label="Cancel" onClick={() => setIsCreating(false)} />
        </div>
      )}
      {errorMessage && (
        <p role="alert" className="text-sm text-red-500 mt-3">
          {errorMessage}
        </p>
      )}
      <div className="mt-6 grid gap-3">
        {isLoading && workflows.length === 0 && <div className="text-sm text-secondary">Loading workflows…</div>}
        {!isLoading && workflows.length === 0 && (
          <div className="rounded-lg border border-dashed border-subtle p-10 text-center">
            <div className="text-base font-medium">No custom workflow yet</div>
            <div className="text-sm mt-1 text-secondary">Create one to open an empty visual canvas.</div>
          </div>
        )}
        {workflows.map((workflow) => (
          <div
            key={workflow.id}
            className="flex w-full items-center justify-between gap-4 rounded-lg border border-subtle bg-surface-1 p-4"
          >
            {editingId === workflow.id ? (
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <input
                  aria-label="Workflow name"
                  className="text-sm h-9 min-w-0 flex-1 rounded-md border border-subtle bg-surface-2 px-3"
                  value={editingName}
                  onChange={(event) => setEditingName(event.target.value)}
                  onKeyDown={(event) => event.key === "Enter" && void handleRename(workflow.id)}
                />
                <Button
                  variant="primary"
                  size="sm"
                  stretch="auto"
                  label="Save"
                  disabled={!editingName.trim() || busyId === workflow.id}
                  onClick={() => void handleRename(workflow.id)}
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
              <button
                type="button"
                className="min-w-0 flex-1 text-left"
                onClick={() =>
                  router.push(`/${workspaceSlug}/settings/projects/${projectId}/workflows/${workflow.id}/`)
                }
              >
                <div className="font-medium">{workflow.name}</div>
                <div className="text-sm mt-1 text-secondary">{workflow.description || "No description"}</div>
              </button>
            )}
            <div className="flex shrink-0 items-center gap-2">
              <span className="text-xs rounded-full bg-surface-2 px-2.5 py-1 text-secondary">
                {workflow.active_version_id ? "Published" : "Draft only"}
              </span>
              {editingId !== workflow.id && (
                <>
                  <Button
                    variant="secondary"
                    size="sm"
                    stretch="auto"
                    label="Edit name"
                    onClick={() => {
                      setEditingId(workflow.id);
                      setEditingName(workflow.name);
                      setErrorMessage("");
                    }}
                  />
                  <Button
                    variant="secondary"
                    size="sm"
                    stretch="auto"
                    label="Delete"
                    disabled={busyId === workflow.id}
                    onClick={() => void handleDelete(workflow.id, workflow.name)}
                  />
                </>
              )}
            </div>
          </div>
        ))}
      </div>
      <WorkflowMapping workspaceSlug={workspaceSlug} projectId={projectId} />
    </SettingsContentWrapper>
  );
}

export default observer(WorkflowsSettingsPage);
