import { observer } from "mobx-react";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { WorkflowDesigner } from "@/components/workflows/workflow-designer";
import type { Route } from "./+types/page";
import { WorkflowsProjectSettingsHeader } from "../header";

function WorkflowDesignerPage({ params }: Route.ComponentProps) {
  const { workspaceSlug, projectId, workflowId } = params;
  return (
    <SettingsContentWrapper header={<WorkflowsProjectSettingsHeader />}>
      <PageHead title="Workflow designer" />
      <WorkflowDesigner workspaceSlug={workspaceSlug} projectId={projectId} workflowId={workflowId} />
    </SettingsContentWrapper>
  );
}

export default observer(WorkflowDesignerPage);
