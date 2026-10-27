/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { Workflow as WorkflowIcon } from "lucide-react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// plane imports
import { StateSelect as StateSelectBlock, sortWorkflowTransitions } from "@plane/blocks/property-select";
import { useSelectContext } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import type { StateOption } from "@plane/blocks/property-select";
import type { SelectPaginationParams, SelectTooltip, SelectTooltipOverride, SelectVariant } from "@plane/blocks/select";
import { useTranslation } from "@plane/i18n";
import type { IState, TPaginatedResponse, TStateGroups } from "@plane/types";
// hooks
import { useProjectState } from "@/hooks/store/use-project-state";
import { WorkflowService } from "@/services/workflow.service";

const WorkflowViewer = lazy(() =>
  import("@/components/workflows/workflow-viewer").then((module) => ({ default: module.WorkflowViewer }))
);

function ViewWorkflowAction({ onView }: { onView: () => void }) {
  const { close } = useSelectContext();
  return (
    <button
      type="button"
      className="text-sm flex w-full items-center gap-2 rounded px-3 py-2 text-secondary hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-offset-2"
      onClick={() => {
        close();
        onView();
      }}
    >
      <WorkflowIcon className="size-4 shrink-0" />
      View workflow
    </button>
  );
}

type StateSelectWebProps = {
  /** Project whose states are offered. */
  projectId: string | undefined;
  /** Existing work item whose published workflow should constrain the options. */
  issueId?: string;
  /** Work item type used to constrain the initial state while creating a work item. */
  issueTypeId?: string | null;
  /** Current state id (`null` / `undefined` when none). */
  value: string | null | undefined;
  /** Emits the next state id and optional transition id. */
  onChange: (stateId: string, transitionId?: string) => unknown;
  variant: SelectVariant;
  disabled?: boolean;
  placeholder?: string;
  onClose?: () => void;
  className?: string;
  tooltip?: SelectTooltip;
  appendElement?: ReactNode;
  /** Forwarded to the block's trigger — see `StateSelectProps["testId"]` doc comment. */
  testId?: string;
  /** Tab order of the trigger, for forms that sequence focus explicitly (`ETabIndices`). */
  tabIndex?: number;
};

const toOption = (state: IState): StateOption => ({
  id: state.id,
  name: state.name,
  color: state.color,
  group: state.group,
  order: state.order,
});

/**
 * Web binding for the presentational `StateSelect` block. Resolves the project's states from the
 * project-state store or published workflow transitions, orders them based on the workflow graph,
 * and passes the selected id and transition id.
 *
 * Existing items use published outgoing transitions; creation uses the type's start state.
 */
export const StateSelect = observer(function StateSelect(props: StateSelectWebProps) {
  const {
    projectId,
    issueId,
    issueTypeId,
    value,
    onChange,
    variant,
    disabled,
    placeholder,
    onClose,
    className,
    tooltip,
    appendElement,
    testId,
    tabIndex,
  } = props;
  // router params
  const { workspaceSlug } = useParams();
  // store hooks
  const { getProjectStateIds, getStateById, fetchProjectStates } = useProjectState();
  const [allowedStateIds, setAllowedStateIds] = useState<Set<string> | null>(null);
  const [workflowStartStateId, setWorkflowStartStateId] = useState<string | null>(null);
  const [isWorkflowMode, setIsWorkflowMode] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [showWorkflow, setShowWorkflow] = useState(false);
  const workflowService = useMemo(() => new WorkflowService(), []);

  useEffect(() => {
    setAllowedStateIds(null);
    setWorkflowStartStateId(null);
    setIsWorkflowMode(false);
  }, [issueId, issueTypeId, projectId, workspaceSlug]);

  useEffect(() => {
    if (issueId) setAllowedStateIds(null);
  }, [issueId, value]);

  useEffect(() => {
    if (issueId || !issueTypeId || !projectId || !workspaceSlug) return;
    let cancelled = false;
    void workflowService
      .getIssueTypeWorkflowStates(workspaceSlug.toString(), projectId, issueTypeId)
      .then((response) => {
        if (cancelled) return;
        if (response.workflow_enabled) {
          setAllowedStateIds(new Set(response.start_state_id ? [response.start_state_id] : []));
          setWorkflowStartStateId(response.start_state_id);
        }
        return undefined;
      })
      .catch(() => {
        if (!cancelled) {
          setAllowedStateIds(new Set());
          setWorkflowStartStateId(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [issueId, issueTypeId, projectId, workspaceSlug, workflowService]);

  useEffect(() => {
    if (!issueId && issueTypeId && workflowStartStateId && value !== workflowStartStateId) {
      onChange(workflowStartStateId);
    }
  }, [issueId, issueTypeId, workflowStartStateId, value, onChange]);

  // translation
  const { t } = useTranslation();
  const resolvedTooltip = useMemo<SelectTooltipOverride | undefined>(() => {
    if (!tooltip) return undefined;
    const override = typeof tooltip === "object" ? tooltip : undefined;
    return {
      heading: override?.heading ?? t("common.state"),
      emptyContent: override?.emptyContent ?? t("common.none"),
    };
  }, [tooltip, t]);

  const getValues = useCallback(
    async ({ search }: SelectPaginationParams): Promise<TPaginatedResponse<StateOption[]>> => {
      if (!workspaceSlug || !projectId) return { results: [] };

      // Make sure project states are loaded in the store
      let stateIds = getProjectStateIds(projectId);
      if (!stateIds) {
        await fetchProjectStates(workspaceSlug.toString(), projectId);
        stateIds = getProjectStateIds(projectId);
      }

      const query = search?.trim().toLowerCase();

      // Existing work item: fetch valid workflow transitions
      if (issueId) {
        try {
          const response = await workflowService.getIssueTransitions(workspaceSlug.toString(), projectId, issueId);
          if (response.workflow_enabled) {
            setIsWorkflowMode(true);
            setAllowedStateIds(null);

            // Sort transitions according to the directed workflow graph
            const sortedTransitions = sortWorkflowTransitions(response.transitions, {
              currentStateId: value ?? undefined,
            });

            // Map each transition to a StateOption
            const transitionOptions: StateOption[] = [];
            for (const transition of sortedTransitions) {
              const targetState =
                transition.target_state ??
                (transition.target_state_id ? getStateById(transition.target_state_id) : undefined);

              const targetId = transition.target_state_id ?? targetState?.id;
              if (!targetId) continue;

              const option: StateOption = {
                id: transition.id ?? `${transition.source_key}-${transition.target_key}`,
                transitionId: transition.id,
                targetStateId: targetId,
                name: targetState?.name ?? transition.name,
                transitionName: transition.name,
                color: targetState?.color ?? "#3E63DD",
                group: (targetState?.group ?? "unstarted") as TStateGroups,
                order: targetState?.order ?? 0,
                direction: transition.direction ?? "forward",
              };

              // Filter by search matching either target state name or transition name
              if (
                !query ||
                option.name.toLowerCase().includes(query) ||
                (option.transitionName && option.transitionName.toLowerCase().includes(query))
              ) {
                transitionOptions.push(option);
              }
            }

            return { results: transitionOptions, next_page_results: false };
          }
        } catch (error) {
          console.error("Unable to load workflow transitions", error);
        }
      }

      // Fallback for work items without custom workflows or when creating a new item
      setIsWorkflowMode(false);
      let allowedIds = allowedStateIds;
      if (!issueId && issueTypeId) {
        const response = await workflowService.getIssueTypeWorkflowStates(
          workspaceSlug.toString(),
          projectId,
          issueTypeId
        );
        allowedIds = response.workflow_enabled
          ? new Set(response.start_state_id ? [response.start_state_id] : [])
          : null;
        setAllowedStateIds(allowedIds);
        setWorkflowStartStateId(response.workflow_enabled ? response.start_state_id : null);
      }

      const results = (stateIds ?? [])
        .map((stateId) => getStateById(stateId))
        .filter((state): state is IState => !!state)
        .filter((state) => allowedIds === null || allowedIds.has(state.id))
        .filter((state) => !query || state.name.toLowerCase().includes(query))
        .map(toOption);

      return { results, next_page_results: false };
    },
    [
      workspaceSlug,
      projectId,
      issueId,
      issueTypeId,
      value,
      allowedStateIds,
      workflowService,
      getProjectStateIds,
      fetchProjectStates,
      getStateById,
    ]
  );

  // Resolved in the observer render so MobX re-renders when the state loads.
  const selectedState = value ? getStateById(value) : undefined;
  const selected = selectedState ? toOption(selectedState) : null;
  const workflowStartState = workflowStartStateId ? getStateById(workflowStartStateId) : undefined;

  const handleChange = async (stateId: string, transitionId?: string) => {
    if (isUpdating) return;
    setIsUpdating(true);
    try {
      await onChange(stateId, transitionId);
    } catch (error: unknown) {
      // Existing issue stores roll optimistic updates back when the request rejects.
      console.error("Unable to update work item state", error);
      setToast({
        type: "error",
        title: "Unable to change state",
        message:
          "Your changes were not saved. Check the workflow transition, permissions and conditions, then try again.",
      });
    } finally {
      if (issueId) setAllowedStateIds(null);
      setIsUpdating(false);
    }
  };

  return (
    <>
      <StateSelectBlock
        getValues={getValues}
        value={workflowStartState ? toOption(workflowStartState) : selected}
        onChange={(stateId, transitionId) => void handleChange(stateId, transitionId)}
        variant={variant}
        disabled={disabled || isUpdating}
        placeholder={placeholder ?? t("state")}
        onClose={onClose}
        className={className}
        tooltip={resolvedTooltip}
        appendElement={appendElement}
        testId={testId}
        tabIndex={tabIndex}
        allowedStateIds={allowedStateIds}
        isWorkflowMode={isWorkflowMode}
        footer={
          issueId && projectId && workspaceSlug ? (
            <ViewWorkflowAction onView={() => setShowWorkflow(true)} />
          ) : undefined
        }
      />
      {showWorkflow && issueId && projectId && workspaceSlug && (
        <Suspense fallback={<span role="status">Loading workflow…</span>}>
          <WorkflowViewer
            key={`${workspaceSlug}:${projectId}:${issueId}`}
            workspaceSlug={workspaceSlug.toString()}
            projectId={projectId}
            issueId={issueId}
            onClose={() => setShowWorkflow(false)}
          />
        </Suspense>
      )}
    </>
  );
});
