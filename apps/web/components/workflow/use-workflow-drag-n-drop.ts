/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useMemo, useState } from "react";
import { useParams } from "react-router";
import type { TIssueGroupByOptions } from "@plane/types";
import { WorkflowService } from "@/services/workflow.service";

export const useWorkFlowFDragNDrop = (groupBy: TIssueGroupByOptions | undefined, subGroupBy?: TIssueGroupByOptions) => {
  const { workspaceSlug, projectId } = useParams();
  const workflowService = useMemo(() => new WorkflowService(), []);
  const [isWorkflowDropDisabled, setIsWorkflowDropDisabled] = useState(false);
  const [workflowDisabledSource, setWorkflowDisabledSource] = useState<string | undefined>();

  const handleWorkFlowState = useCallback(
    async (
      sourceGroupId: string,
      destinationGroupId: string,
      sourceSubGroupId?: string,
      destinationSubGroupId?: string,
      issueId?: string
    ) => {
      const stateAxis = groupBy === "state" ? "group" : subGroupBy === "state" ? "subgroup" : null;
      if (!stateAxis || !workspaceSlug || !projectId || !issueId) {
        setIsWorkflowDropDisabled(false);
        setWorkflowDisabledSource(undefined);
        return;
      }
      const sourceStateId = stateAxis === "group" ? sourceGroupId : sourceSubGroupId;
      const targetStateId = stateAxis === "group" ? destinationGroupId : destinationSubGroupId;
      if (!sourceStateId || !targetStateId || sourceStateId === targetStateId) {
        setIsWorkflowDropDisabled(false);
        return;
      }
      const result = await workflowService.getIssueTransitions(workspaceSlug, projectId, issueId);
      const disabled =
        result.workflow_enabled &&
        !result.transitions.some((transition) => transition.target_state_id === targetStateId);
      setIsWorkflowDropDisabled(disabled);
      setWorkflowDisabledSource(disabled ? sourceStateId : undefined);
    },
    [groupBy, projectId, subGroupBy, workflowService, workspaceSlug]
  );

  return {
    workflowDisabledSource,
    isWorkflowDropDisabled,
    getIsWorkflowWorkItemCreationDisabled: (_groupId: string, _subGroupId?: string) => false,
    handleWorkFlowState,
  };
};
