import { observer } from "mobx-react";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { BlockedIcon, BlockerIcon } from "@plane/blocks/icons";
import type { TIssue } from "@plane/types";
import { cn } from "@plane/utils";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useProjectState } from "@/hooks/store/use-project-state";

type Props = {
  issue: TIssue;
  compact?: boolean;
  className?: string;
};

export const IssueDependencyBadges = observer(function IssueDependencyBadges(props: Props) {
  const { issue, compact = false, className } = props;
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  const { getStateById } = useProjectState();

  const blockers = (issue.issue_relation ?? []).filter((relation) => {
    if (relation.relation_type !== "blocked_by") return false;
    const relatedIssue = getIssueById(relation.id);
    const state = getStateById(relatedIssue?.state_id ?? relation.state_id);
    return state?.group !== "completed";
  });
  const blockedItems = (issue.issue_related ?? []).filter((relation) => relation.relation_type === "blocked_by");

  if (!blockers.length && !blockedItems.length) return null;

  return (
    <span className={cn("inline-flex flex-shrink-0 items-center gap-1", className)}>
      {blockers.length > 0 && (
        <Tooltip
          label={`Blocked by ${blockers.length} active work item${blockers.length === 1 ? "" : "s"}`}
          layout="stacked"
        >
          <span
            aria-label={`Blocked by ${blockers.length} active work item${blockers.length === 1 ? "" : "s"}`}
            className="inline-flex h-5 items-center gap-1 rounded-sm bg-danger-subtle px-1.5 text-11 font-medium text-danger-primary"
          >
            <BlockedIcon className="size-3" />
            {!compact && "Blocked"}
            <span>{blockers.length}</span>
          </span>
        </Tooltip>
      )}
      {blockedItems.length > 0 && (
        <Tooltip
          label={`Blocking ${blockedItems.length} work item${blockedItems.length === 1 ? "" : "s"}`}
          layout="stacked"
        >
          <span
            aria-label={`Blocking ${blockedItems.length} work item${blockedItems.length === 1 ? "" : "s"}`}
            className="inline-flex h-5 items-center gap-1 rounded-sm bg-warning-subtle px-1.5 text-11 font-medium text-warning-primary"
          >
            <BlockerIcon className="size-3" />
            {!compact && "Blocking"}
            <span>{blockedItems.length}</span>
          </span>
        </Tooltip>
      )}
    </span>
  );
});
