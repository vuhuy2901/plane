import type { TIssue } from "@plane/types";

const ROLLUP_FIELDS: ReadonlySet<keyof TIssue> = new Set(["estimate_point", "state_id", "parent_id", "archived_at"]);

export const affectsHierarchicalEstimate = (data: Partial<TIssue>): boolean =>
  Object.keys(data).some((key) => ROLLUP_FIELDS.has(key as keyof TIssue));

export const usesHierarchicalEstimate = (issue: TIssue | undefined): boolean =>
  Boolean(issue?.is_rolled_up || (issue?.sub_issues_count && issue.sub_issues_count > 0));

export const displayedEstimate = (issue: TIssue | undefined): number | null => {
  if (!usesHierarchicalEstimate(issue)) return null;
  return issue?.effective_estimate ?? issue?.rolled_up_estimate ?? 0;
};

type RefreshEstimateChainOptions = {
  issueId: string;
  previousParentId?: string | null;
  fetchIssue: (issueId: string) => Promise<TIssue>;
  applyIssue: (issue: TIssue) => void;
  depthLimit?: number;
};

export const refreshHierarchicalEstimateChain = async ({
  issueId,
  previousParentId,
  fetchIssue,
  applyIssue,
  depthLimit = 15,
}: RefreshEstimateChainOptions): Promise<void> => {
  const visitedIds = new Set<string>();

  const refreshIssueAndParent = async (currentId: string | null | undefined): Promise<void> => {
    if (!currentId || visitedIds.has(currentId) || visitedIds.size >= depthLimit) return;
    visitedIds.add(currentId);

    try {
      const issue = await fetchIssue(currentId);
      applyIssue(issue);
      await refreshIssueAndParent(issue.parent_id);
    } catch {
      // The work item update has already succeeded. A refresh failure should not
      // revert the optimistic edit; the next normal fetch will reconcile it.
    }
  };

  await refreshIssueAndParent(issueId);
  await refreshIssueAndParent(previousParentId);
};
