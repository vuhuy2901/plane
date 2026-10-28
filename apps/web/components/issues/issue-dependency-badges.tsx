import { observer } from "mobx-react";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { BlockedIcon, BlockerIcon } from "@plane/blocks/icons";
import type { TIssue } from "@plane/types";
import { cn } from "@plane/utils";
import { useIssueDependencyStatus } from "@/components/issues/issue-detail/dependency-status-property";

type Props = {
  issue: TIssue;
  compact?: boolean;
  className?: string;
};

export const IssueDependencyBadges = observer(function IssueDependencyBadges(props: Props) {
  const { issue, compact = false, className } = props;
  const { activeBlockerIds, activeBlockedWorkItemIds } = useIssueDependencyStatus(issue.id);

  if (!activeBlockerIds.length && !activeBlockedWorkItemIds.length) return null;

  return (
    <span className={cn("inline-flex flex-shrink-0 items-center gap-1", className)}>
      {activeBlockerIds.length > 0 && (
        <Tooltip
          label={`Blocked by ${activeBlockerIds.length} active work item${activeBlockerIds.length === 1 ? "" : "s"}`}
          layout="stacked"
        >
          <span
            aria-label={`Blocked by ${activeBlockerIds.length} active work item${activeBlockerIds.length === 1 ? "" : "s"}`}
            className="inline-flex h-5 items-center gap-1 rounded-sm bg-danger-subtle px-1.5 text-11 font-medium text-danger-primary"
          >
            <BlockedIcon className="size-3" />
            {!compact && "Blocked"}
            <span>{activeBlockerIds.length}</span>
          </span>
        </Tooltip>
      )}
      {activeBlockedWorkItemIds.length > 0 && (
        <Tooltip
          label={`Blocking ${activeBlockedWorkItemIds.length} work item${activeBlockedWorkItemIds.length === 1 ? "" : "s"}`}
          layout="stacked"
        >
          <span
            aria-label={`Blocking ${activeBlockedWorkItemIds.length} work item${activeBlockedWorkItemIds.length === 1 ? "" : "s"}`}
            className="inline-flex h-5 items-center gap-1 rounded-sm bg-warning-subtle px-1.5 text-11 font-medium text-warning-primary"
          >
            <BlockerIcon className="size-3" />
            {!compact && "Blocking"}
            <span>{activeBlockedWorkItemIds.length}</span>
          </span>
        </Tooltip>
      )}
    </span>
  );
});
