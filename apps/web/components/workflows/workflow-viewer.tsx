import { useMemo } from "react";
import useSWR from "swr";
import { Background, ConnectionMode, Controls, ReactFlow } from "@xyflow/react";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogCloseGroup,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { CloseOutline } from "@makeplane/propel/icons";
import { WorkflowService } from "@/services/workflow.service";
import { workflowEdgeTypes, workflowNodeTypes } from "./workflow-designer";
import { workflowPreviewGraph } from "./workflow-graph";
import type { WorkflowEdge, WorkflowNode } from "./workflow-graph";

const workflowService = new WorkflowService();

type Props = { workspaceSlug: string; projectId: string; issueId: string; onClose: () => void };

export function WorkflowViewer({ workspaceSlug, projectId, issueId, onClose }: Props) {
  const { data, error, mutate } = useSWR(["work-item-workflow", workspaceSlug, projectId, issueId], () =>
    workflowService.getIssueWorkflow(workspaceSlug, projectId, issueId)
  );
  const graph = useMemo(() => (data ? workflowPreviewGraph(data) : null), [data]);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent size="xl">
        <DialogCloseGroup>
          <IconButton
            variant="ghost"
            size="xs"
            aria-label="Close workflow"
            icon={<CloseOutline />}
            render={<DialogClose />}
          />
        </DialogCloseGroup>
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>{data?.workflow?.name ?? "View workflow"}</DialogTitle>
              <DialogDescription>
                {data?.workflow
                  ? `Published version ${data.workflow.version}. The highlighted state is this work item's current state.`
                  : "View the workflow applied to this work item."}
              </DialogDescription>
            </DialogHeading>
          </DialogHeader>
          <DialogBody>
            {error ? (
              <div role="alert" className="text-sm py-8 text-secondary">
                Unable to load this workflow.{" "}
                <button type="button" className="underline" onClick={() => void mutate()}>
                  Try again
                </button>
              </div>
            ) : !data ? (
              <div role="status" className="text-sm py-8 text-secondary">
                Loading workflow…
              </div>
            ) : !graph ? (
              <p className="text-sm py-8 text-secondary">
                This work item uses project states without a custom workflow. No published workflow is assigned to its
                work item type.
              </p>
            ) : (
              <>
                <p className="text-xs mb-3 text-secondary">
                  Ctrl + scroll to zoom (Mac: Cmd + scroll). Scroll or drag the background to pan. This view is
                  read-only.
                </p>
                <div className="h-[55vh] min-h-80 overflow-hidden rounded-lg border border-subtle">
                  <ReactFlow<WorkflowNode, WorkflowEdge>
                    key={`${issueId}:${data.workflow?.id}:${data.workflow?.version}`}
                    nodes={graph.nodes}
                    edges={graph.edges}
                    nodeTypes={workflowNodeTypes}
                    edgeTypes={workflowEdgeTypes}
                    connectionMode={ConnectionMode.Loose}
                    nodesDraggable={false}
                    nodesConnectable={false}
                    nodesFocusable={false}
                    edgesReconnectable={false}
                    edgesFocusable={false}
                    elementsSelectable={false}
                    deleteKeyCode={null}
                    zoomActivationKeyCode={["Control", "Meta"]}
                    zoomOnScroll={false}
                    zoomOnPinch
                    panOnScroll
                    minZoom={0.2}
                    maxZoom={3}
                    fitView
                    fitViewOptions={{ padding: 0.2 }}
                  >
                    <Background />
                    <Controls showInteractive={false} />
                  </ReactFlow>
                </div>
              </>
            )}
          </DialogBody>
        </DialogMain>
      </DialogContent>
    </Dialog>
  );
}
