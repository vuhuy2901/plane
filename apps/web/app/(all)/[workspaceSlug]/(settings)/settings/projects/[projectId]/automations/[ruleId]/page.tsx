import type { Route } from "./+types/page";
import { AutomationRuleEditorPage } from "../editor-page";

export default function EditAutomationRulePage({ params }: Route.ComponentProps) {
  return (
    <AutomationRuleEditorPage
      workspaceSlug={params.workspaceSlug}
      projectId={params.projectId}
      ruleId={params.ruleId}
    />
  );
}
