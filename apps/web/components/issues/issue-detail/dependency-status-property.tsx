/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { observer } from "mobx-react";
import useSWR from "swr";
import { BlockedIcon, BlockerIcon } from "@plane/blocks/icons";
import { SidebarPropertyListItem } from "@/components/common/layout/sidebar/property-list-item";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useProjectState } from "@/hooks/store/use-project-state";

export type TIssueDependencyStatus = {
  activeBlockerIds: string[];
  activeBlockedWorkItemIds: string[];
  relationsLoaded: boolean;
};

/**
 * Dependencies are persisted as relations. A dependency remains after its related
 * work item completes, so the visible status must derive from the related state
 * rather than from relation existence alone.
 */
export const useIssueDependencyStatus = (issueId: string): TIssueDependencyStatus => {
  const {
    issue: { getIssueById },
    relation: { getRelationByIssueIdRelationType, getRelationsByIssueId },
  } = useIssueDetail();
  const { getStateById } = useProjectState();

  const activeRelationIds = (relationType: "blocked_by" | "blocking") =>
    (getRelationByIssueIdRelationType(issueId, relationType) ?? []).filter((relatedIssueId) => {
      const relatedIssue = getIssueById(relatedIssueId);
      const relatedState = getStateById(relatedIssue?.state_id);

      // Treat an unavailable state as active until the relation fetch completes;
      // this avoids incorrectly showing an unblocked work item while loading.
      return relatedState?.group !== "completed";
    });

  return {
    activeBlockerIds: activeRelationIds("blocked_by"),
    activeBlockedWorkItemIds: activeRelationIds("blocking"),
    relationsLoaded: getRelationsByIssueId(issueId) !== undefined,
  };
};

type DependencyStatusValueProps = {
  activeCount: number;
  type: "blocked" | "blocking";
  loading: boolean;
  onOpenRelations: () => void;
};

function DependencyStatusValue(props: DependencyStatusValueProps) {
  const { activeCount, type, loading, onOpenRelations } = props;
  const isBlocked = type === "blocked";
  const label = isBlocked ? "Blocked" : "Blocking";
  const Icon = isBlocked ? BlockedIcon : BlockerIcon;

  if (loading) {
    return <span className="px-2 text-body-xs-regular text-secondary">Loading...</span>;
  }

  if (activeCount === 0) {
    return (
      <span className="inline-flex h-7.5 items-center gap-1.5 px-2 text-body-xs-regular text-secondary">
        <Icon className="size-3.5" />
        No
      </span>
    );
  }

  return (
    <button
      type="button"
      className={
        isBlocked
          ? "focus-visible:outline-danger-primary inline-flex h-7.5 items-center gap-1.5 rounded-sm bg-danger-subtle px-2 text-body-xs-medium text-danger-primary hover:bg-danger-subtle-hover focus-visible:outline-2 focus-visible:outline-offset-2"
          : "focus-visible:outline-warning-primary inline-flex h-7.5 items-center gap-1.5 rounded-sm bg-warning-subtle px-2 text-body-xs-medium text-warning-primary hover:opacity-80 focus-visible:outline-2 focus-visible:outline-offset-2"
      }
      onClick={onOpenRelations}
      aria-label={`View ${activeCount} active ${label.toLowerCase()} work item${activeCount === 1 ? "" : "s"}`}
    >
      <Icon className="size-3.5" />
      Yes
      <span className="tabular-nums">({activeCount})</span>
    </button>
  );
}

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
};

export const IssueDependencyStatusProperties = observer(function IssueDependencyStatusProperties(props: Props) {
  const { workspaceSlug, projectId, issueId } = props;
  const {
    openWidgets,
    toggleOpenWidget,
    relation: { fetchRelations },
  } = useIssueDetail();
  const { activeBlockerIds, activeBlockedWorkItemIds, relationsLoaded } = useIssueDependencyStatus(issueId);

  // The relation endpoint returns the related work items as well as their current
  // states. Revalidating only while the detail is open keeps automation-originated
  // dependency and state changes in sync without introducing a derived backend field.
  useSWR(
    workspaceSlug && projectId && issueId ? ["work-item-dependency-status", workspaceSlug, projectId, issueId] : null,
    () => fetchRelations(workspaceSlug, projectId, issueId),
    { refreshInterval: 5000, revalidateOnFocus: true }
  );

  const openRelations = () => {
    if (!openWidgets.includes("relations")) toggleOpenWidget("relations");
  };

  return (
    <>
      <SidebarPropertyListItem icon={BlockedIcon} label="Blocked">
        <DependencyStatusValue
          activeCount={activeBlockerIds.length}
          type="blocked"
          loading={!relationsLoaded}
          onOpenRelations={openRelations}
        />
      </SidebarPropertyListItem>
      <SidebarPropertyListItem icon={BlockerIcon} label="Blocking">
        <DependencyStatusValue
          activeCount={activeBlockedWorkItemIds.length}
          type="blocking"
          loading={!relationsLoaded}
          onOpenRelations={openRelations}
        />
      </SidebarPropertyListItem>
    </>
  );
});
