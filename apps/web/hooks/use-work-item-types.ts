import useSWR from "swr";
import { WorkflowService } from "@/services/workflow.service";

const service = new WorkflowService();
export const workItemTypesKey = (workspaceSlug: string, projectId: string) => [
  "work-item-types",
  workspaceSlug,
  projectId,
];

export function useWorkItemTypes(workspaceSlug: string | undefined, projectId: string | null | undefined) {
  return useSWR(workspaceSlug && projectId ? workItemTypesKey(workspaceSlug, projectId) : null, () =>
    service.listIssueTypes(workspaceSlug!, projectId!)
  );
}
