import type {
  AutomationCondition,
  AutomationDefinition,
  AutomationRule,
  AutomationResources,
  AutomationService,
  AutomationTemplate,
} from "@/services/automation.service";

const noValueOperators = new Set(["is_empty", "is_not_empty", "overdue", "is_true"]);

export function changeConditionOperator(condition: AutomationCondition, operator: string): AutomationCondition {
  return noValueOperators.has(operator)
    ? { field: condition.field, operator }
    : { field: condition.field, operator, ...(condition.value ? { value: condition.value } : {}) };
}

export function changeConditionField(field: string, operators: Record<string, string[]>): AutomationCondition {
  return { field, operator: operators[field][0] };
}

const clean = (value?: string) => (value?.startsWith("$") ? "" : value);

export function templateDraft(template: AutomationTemplate): AutomationDefinition {
  return {
    name: template.name,
    trigger: template.trigger,
    trigger_options: template.trigger_options
      ? Object.fromEntries(
          Object.entries(template.trigger_options).map(([key, value]) => [
            key,
            typeof value === "string" ? clean(value) : structuredClone(value),
          ])
        )
      : undefined,
    conditions: template.conditions.map((condition) => ({
      ...condition,
      ...(condition.value ? { value: clean(condition.value) } : {}),
    })),
    actions: template.actions.map((action) => ({
      ...action,
      member_id: clean(action.member_id),
      state_id: clean(action.state_id),
      label_id: clean(action.label_id),
      type_id: clean(action.type_id),
      days: action.type === "set_due_date" ? 3 : action.days,
    })),
  };
}

export function editableRule(rule: AutomationRule): AutomationDefinition {
  return structuredClone({
    name: rule.name,
    trigger: rule.trigger,
    trigger_options: rule.trigger_options,
    conditions: rule.conditions,
    actions: rule.actions,
    schema_version: rule.schema_version,
  });
}

export function prepareRuleDefinition(
  draft: AutomationDefinition,
  resources: AutomationResources
): AutomationDefinition {
  if (!draft.name.trim()) throw new Error("Enter a rule name before saving.");
  if (!draft.trigger) throw new Error("Select a trigger in When.");
  if (!draft.actions.length) throw new Error("Add at least one action in Then.");
  const validateConditions = (conditions: AutomationCondition[], section: string) => {
    for (const [index, condition] of conditions.entries()) {
      if (!noValueOperators.has(condition.operator) && !condition.value?.trim())
        throw new Error(`${section}, condition ${index + 1}: select or enter a value.`);
    }
  };
  validateConditions(draft.conditions, "If");
  validateConditions(draft.trigger_options?.filters ?? [], "When filters");
  for (const [index, action] of draft.actions.entries()) {
    const fail = (message: string) => {
      throw new Error(`Then, action ${index + 1}: ${message}`);
    };
    if (!action.type) fail("select an action.");
    if (action.type === "assign_user" && action.mode === "specific_member" && !action.member_id)
      fail("select a member.");
    if (["change_state", "CHANGE_PARENT_STATE"].includes(action.type) && !action.state_id)
      fail("select a destination state.");
    if (action.type === "change_priority" && !action.priority) fail("select a priority.");
    if (action.type === "manage_labels" && !action.label_id) fail("select a label.");
    if (action.type === "add_comment" && !action.text?.trim()) fail("enter a comment.");
    if (action.type === "set_due_date") {
      if (action.mode === "fixed" && !action.date) fail("select a due date.");
      if (
        action.mode !== "fixed" &&
        (action.days === undefined || !Number.isInteger(action.days) || action.days < 0 || action.days > 3650)
      )
        fail("enter a whole number of days from 0 to 3650.");
    }
    if (action.type === "create_work_item") {
      if (!action.type_id || !resources.types.some((type) => type.id === action.type_id))
        fail("select an available type for the new work item.");
      if (!action.title?.trim()) fail("enter a title for the new work item.");
    }
    if (["add_dependency", "remove_dependency"].includes(action.type)) {
      if (!action.relation_type) fail("select a dependency type.");
      if (!action.source_mode || !action.target_mode) fail("select both dependency endpoints.");
      if (action.source_mode === "specific" && !action.source_id) fail("select the source work item.");
      if (action.target_mode === "specific" && !action.target_id) fail("select the target work item.");
    }
  }
  return {
    ...structuredClone(draft),
    name: draft.name.trim(),
    actions: draft.actions.map(
      (action) => Object.fromEntries(Object.entries(action).filter(([, value]) => value !== "")) as typeof action
    ),
  };
}

export async function persistRuleDraft({
  draft,
  resources,
  service,
  workspace,
  project,
  rule,
  enable,
}: {
  draft: AutomationDefinition;
  resources: AutomationResources;
  service: Pick<AutomationService, "save" | "setEnabled">;
  workspace: string;
  project: string;
  rule?: AutomationRule;
  enable: boolean;
}): Promise<{ rule: AutomationRule; enableError?: unknown }> {
  const payload = prepareRuleDefinition(draft, resources);
  const saved = await service.save(workspace, project, payload, rule);
  if (!enable) return { rule: saved };
  try {
    return { rule: await service.setEnabled(workspace, project, saved.id, true) };
  } catch (enableError) {
    return { rule: saved, enableError };
  }
}
