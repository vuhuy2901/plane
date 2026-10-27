import React from "react";
import { observer } from "mobx-react";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { InfoOutline, AlertCircleOutline } from "@makeplane/propel/icons";
import type { TIssue } from "@plane/types";
import { EstimateSelect } from "@/components/dropdowns/estimate/estimate-select";

type Props = {
  issue: TIssue | undefined;
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  isEditable: boolean;
  issueOperations: {
    update: (workspaceSlug: string, projectId: string, issueId: string, data: Partial<TIssue>) => Promise<any>;
  };
};

export const HierarchicalEstimateProperty = observer(function HierarchicalEstimateProperty({
  issue,
  workspaceSlug,
  projectId,
  issueId,
  isEditable,
  issueOperations,
}: Props) {
  const isRolledUp = Boolean(issue?.is_rolled_up || (issue?.sub_issues_count && issue.sub_issues_count > 0));

  if (!isRolledUp) {
    // Leaf item: Allow direct manual estimation
    return (
      <EstimateSelect
        value={issue?.estimate_point ?? undefined}
        onChange={(val: string | null) =>
          issueOperations.update(workspaceSlug, projectId, issueId, { estimate_point: val })
        }
        projectId={projectId}
        disabled={!isEditable}
        variant="select-ghost-md"
        placeholder="None"
        tooltip
      />
    );
  }

  // Parent / Epic: Display auto-calculated rollup, progress, and warnings
  const totalPoints = issue?.effective_estimate ?? issue?.rolled_up_estimate ?? 0;
  const completedPoints = issue?.completed_estimate ?? 0;
  const unestimatedCount = issue?.unestimated_children_count ?? 0;
  const percentage = totalPoints > 0 ? Math.round((completedPoints / totalPoints) * 100) : 0;

  return (
    <div className="flex flex-col gap-1.5 w-full py-1">
      {/* Primary Rollup Badge */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="text-13 font-semibold text-primary">
            {totalPoints} {totalPoints === 1 ? "Point" : "Points"}
          </span>
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-custom-primary-100/20 text-custom-primary-100 border border-custom-primary-100/30">
            Auto-calculated
          </span>
        </div>

        <Tooltip
          label="Estimated points are automatically aggregated from all descendant sub-work items. Manual parent estimates are safely preserved."
        >
          <span className="text-tertiary hover:text-secondary cursor-pointer">
            <InfoOutline className="h-3.5 w-3.5" />
          </span>
        </Tooltip>
      </div>

      {/* Progress metrics and mini progress bar */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between text-[11px] text-tertiary">
          <span>
            Progress: {completedPoints}/{totalPoints} pts
          </span>
          <span className="font-medium text-secondary">{percentage}%</span>
        </div>

        {/* Progress Bar Track */}
        <div className="h-1.5 w-full bg-layer-2 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-300 rounded-full ${
              percentage === 100 ? "bg-emerald-500" : "bg-custom-primary-100"
            }`}
            style={{ width: `${Math.min(percentage, 100)}%` }}
          />
        </div>
      </div>

      {/* Unestimated Subtasks Warning */}
      {unestimatedCount > 0 && (
        <Tooltip
          label={`${unestimatedCount} sub-work item${
            unestimatedCount > 1 ? "s have" : " has"
          } not been estimated yet.`}
        >
          <div className="flex items-center gap-1 text-[11px] text-amber-500 mt-0.5">
            <AlertCircleOutline className="h-3 w-3 shrink-0" />
            <span className="truncate">
              {unestimatedCount} subtask{unestimatedCount > 1 ? "s" : ""} unestimated
            </span>
          </div>
        </Tooltip>
      )}
    </div>
  );
});
