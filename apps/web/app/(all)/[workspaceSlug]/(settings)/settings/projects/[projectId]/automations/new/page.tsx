import type { Route } from "./+types/page";
import { AutomationRuleEditorPage } from "../editor-page";

export default function CreateAutomationRulePage({ params }: Route.ComponentProps) {
  return <AutomationRuleEditorPage workspaceSlug={params.workspaceSlug} projectId={params.projectId} />;
}
