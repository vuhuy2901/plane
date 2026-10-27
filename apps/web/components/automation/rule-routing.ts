import type { AutomationResources, AutomationService } from "@/services/automation.service";
import { editableRule, templateDraft } from "./rule-form";
import { createBugDraft } from "./rule-presentation";

export function automationRulePaths(workspace: string, project: string) {
  const list = `/${encodeURIComponent(workspace)}/settings/projects/${encodeURIComponent(project)}/automations`;
  return {
    list,
    create: `${list}/new`,
    bug: `${list}/new?preset=bug`,
    template: (id: string) => `${list}/new?template=${encodeURIComponent(id)}`,
    edit: (id: string) => `${list}/${encodeURIComponent(id)}`,
  };
}

export type AutomationEditorOptions = { ruleId?: string; preset?: string; templateId?: string };

export async function loadAutomationEditor(
  options: AutomationEditorOptions,
  resources: AutomationResources,
  service: Pick<AutomationService, "rule" | "templates">,
  workspace: string,
  project: string
) {
  if (options.ruleId) {
    const rule = await service.rule(workspace, project, options.ruleId);
    return { draft: editableRule(rule), rule };
  }
  if (options.templateId) {
    const template = (await service.templates(workspace, project)).find((item) => item.id === options.templateId);
    if (!template) throw new Error("This automation template is unavailable. Return to Automations to choose another.");
    const draft = templateDraft(template);
    if (draft.trigger === "scheduled")
      draft.trigger_options = { ...draft.trigger_options, timezone: resources.timezone ?? "UTC" };
    return { draft, rule: undefined };
  }
  if (options.preset === "bug") return { draft: createBugDraft(resources), rule: undefined };
  return {
    draft: { name: "", trigger: "", trigger_options: {}, conditions: [], actions: [{ type: "" }] },
    rule: undefined,
  };
}
