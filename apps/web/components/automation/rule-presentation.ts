import type {
  AutomationAction,
  AutomationCondition,
  AutomationDefinition,
  AutomationEvaluationCheck,
  AutomationHistory,
  AutomationResources,
  AutomationTestResult,
} from "@/services/automation.service";

export const triggerNames: Record<string, string> = {
  created: "Work item created",
  updated: "Work item updated",
  state_changed: "State changed",
  assignee_changed: "Assignee changed",
  priority_changed: "Priority changed",
  comment_added: "Comment added",
  work_item_linked: "Work item linked",
  scheduled: "Scheduled",
  SUBTASK_COMPLETED: "Subtask completed",
};

export const fieldNames: Record<string, string> = {
  trigger: "Source event",
  event: "Source event",
  type_id: "Source work item type",
  work_item_type: "Source work item type",
  state: "State",
  from_state: "Previous state",
  to_state: "New state",
  state_group: "State group",
  from_group: "Previous state group",
  to_group: "New state group",
  priority: "Priority",
  from_priority: "Previous priority",
  to_priority: "New priority",
  assignee: "Assignee",
  previous_assignee: "Previous assignee",
  new_assignee: "New assignee",
  author_id: "Comment author",
  label: "Label",
  due_date: "Due date",
  ALL_SUBTASKS_COMPLETED: "All subtasks completed",
};

export const operatorLabels: Record<string, string> = {
  equals: "is",
  not_equals: "is not",
  contains: "contains",
  does_not_contain: "does not contain",
  is_empty: "is empty",
  is_not_empty: "is not empty",
  overdue: "is overdue",
  within_next_days: "is within the next days:",
  is_true: "is true",
  changed: "changed",
};

export function displayValue(field: string, value: unknown, resources: AutomationResources): string {
  if (value === undefined) return "Not recorded";
  if (value === null || value === "" || (Array.isArray(value) && value.length === 0)) return "Empty";
  if (Array.isArray(value)) return value.map((item) => displayValue(field, item, resources)).join(", ");
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return "Value unavailable";
  const id = String(value);
  if (["trigger", "event", "triggers"].includes(field)) return triggerNames[id] ?? id.replaceAll("_", " ");
  if (id.startsWith("group:")) return `${id.slice(6)} state group`;
  const options = ["work_item_type", "type_id"].includes(field)
    ? resources.types
    : ["state", "from_state", "to_state"].includes(field)
      ? resources.states
      : ["assignee", "previous_assignee", "new_assignee", "author_id", "member_id"].includes(field)
        ? resources.members
        : field === "label" || field === "label_id"
          ? resources.labels
          : field === "source_id" || field === "target_id"
            ? resources.work_items
            : [];
  return options.find((option) => option.id === id)?.name ?? id;
}

export function conditionSummary(condition: AutomationCondition, resources: AutomationResources): string {
  const label = `${fieldNames[condition.field] ?? condition.field.replaceAll("_", " ")} ${operatorLabels[condition.operator] ?? condition.operator.replaceAll("_", " ")}`;
  return ["is_empty", "is_not_empty", "overdue", "is_true"].includes(condition.operator)
    ? label
    : `${label} ${condition.value ? displayValue(condition.field, condition.value, resources) : "(select a value)"}`;
}

export function actionSummary(action: AutomationAction, resources: AutomationResources): string {
  switch (action.type) {
    case "":
      return "(select an action)";
    case "create_work_item":
      return `Create ${action.type_id ? displayValue("type_id", action.type_id, resources) : "a work item (select type)"}: ${action.title || "(enter title)"} · ${action.parent_mode === "source" ? "Child of source work item (nested)" : "Top-level work item"}`;
    case "assign_user":
      return `Assign source work item to ${action.mode === "project_lead" ? "project lead" : action.mode === "creator" ? "its creator" : action.member_id ? displayValue("member_id", action.member_id, resources) : "(select member)"}${action.only_if_unassigned !== false ? ", only if unassigned" : ""}`;
    case "change_state":
    case "CHANGE_PARENT_STATE":
      return `Change ${action.target === "parent" || action.type === "CHANGE_PARENT_STATE" ? "parent" : "source"} state to ${displayValue("state", action.state_id, resources)}`;
    case "change_priority":
      return `Change source priority to ${action.priority ?? "(select priority)"}`;
    case "manage_labels":
      return `${action.operation === "remove" ? "Remove" : "Add"} label ${displayValue("label", action.label_id, resources)} ${action.operation === "remove" ? "from" : "on"} source work item`;
    case "add_comment":
      return `Comment on source work item: ${action.text || "(enter comment)"}`;
    case "set_due_date":
      return `Set source due date to ${action.mode === "fixed" ? action.date || "(select date)" : `${action.days ?? 3} days after trigger`}`;
    default:
      return action.type.replaceAll("_", " ");
  }
}

export function triggerSummary(definition: AutomationDefinition, resources: AutomationResources): string {
  const options = definition.trigger_options ?? {};
  const event = definition.trigger
    ? (triggerNames[definition.trigger] ?? definition.trigger.replaceAll("_", " "))
    : "(select a source event)";
  const qualifiers = Object.entries(options)
    .filter(([key, value]) => value !== undefined && value !== "" && key !== "filters")
    .map(([key, value]) => `${fieldNames[key] ?? key.replaceAll("_", " ")}: ${displayValue(key, value, resources)}`);
  const filters = (options.filters ?? []).map((condition) => conditionSummary(condition, resources));
  return [event, ...qualifiers, ...filters].join(" · ");
}

export function checkExplanation(check: AutomationEvaluationCheck, resources: AutomationResources): string {
  const condition = conditionSummary({ field: check.field, operator: check.operator, value: undefined }, resources);
  const unary = ["is_empty", "is_not_empty", "overdue", "is_true"].includes(check.operator);
  const expectation = unary
    ? condition
    : `${fieldNames[check.field] ?? check.field.replaceAll("_", " ")} ${operatorLabels[check.operator] ?? check.operator.replaceAll("_", " ")} ${displayValue(check.field, check.expected, resources)}`;
  const detail = check.reason
    ? check.reason
    : `${expectation}. Actual: ${displayValue(check.field, check.actual, resources)}.`;
  return `${check.matched ? "Matched" : "Not matched"}: ${detail}${check.matched ? "" : " Review this filter or the source work item."}`;
}

// Older executions did not record evaluation. Infer only what the event proves.
export function historyTriggerMismatch(row: AutomationHistory): string | undefined {
  if (row.snapshot.evaluation) return undefined;
  const { triggers, definition } = row.snapshot;
  if (!triggers || triggers.includes(definition.trigger)) return undefined;
  return `Source event did not match: this rule waits for ${triggerNames[definition.trigger] ?? definition.trigger}, but recorded ${triggers.map((trigger) => triggerNames[trigger] ?? trigger).join(", ") || "no source event"}. Choose the source event you intend in When. No actions ran.`;
}

export function historyCreatedWorkItemIds(row: AutomationHistory): string[] {
  if (!row.rule_id) return [];
  return [
    ...new Set(
      Object.values(row.snapshot.steps?.[row.rule_id] ?? {}).flatMap((step) =>
        step.created_issue_id ? [step.created_issue_id] : []
      )
    ),
  ];
}

export function dryRunSummary(result: AutomationTestResult): string {
  if (result.writes !== 0)
    return "The server did not confirm zero writes. Preview safety could not be verified. Check execution history before retrying.";
  if (!result.valid)
    return "Dry-run could not validate this rule. Review the configuration before enabling it. No data was modified.";
  if (result.evaluation?.matched === false || result.trigger_match === false || !result.conditions_match)
    return "Dry-run: this source work item does not match the rule. No data was modified.";
  return `Dry-run: source filters match. ${result.action_count ?? 0} actions prepared; none executed. No data was modified.`;
}

const errorMessages = (value: unknown, path = ""): string[] => {
  if (Array.isArray(value))
    return value.flatMap((item, index) => errorMessages(item, `${path}${path ? " " : ""}${index + 1}`));
  if (value && typeof value === "object")
    return Object.entries(value).flatMap(([key, item]) =>
      errorMessages(item, [path, key.replaceAll("_", " ")].filter(Boolean).join(" "))
    );
  return typeof value === "string" && value.trim() ? [`${path && path !== "detail" ? `${path}: ` : ""}${value}`] : [];
};

export function automationError(error: unknown): string {
  const response = (error as { response?: { status?: number; data?: unknown } } | null)?.response;
  if (response?.status === 409)
    return "This rule changed since you opened it. Your draft is still here. Cancel the draft and reopen the latest saved rule before saving again.";
  return (
    errorMessages(response?.data).join("; ") ||
    (error instanceof Error ? error.message : "Request failed. Please try again.")
  );
}

export function createBugDraft(resources: AutomationResources): AutomationDefinition {
  const bug = resources.types.find((type) => type.name.trim().toLowerCase() === "bug");
  const task = resources.types.find((type) => type.name.trim().toLowerCase() === "task");
  const testing = resources.states.find((state) => state.name.replaceAll(/\s+/g, "").toLowerCase() === "intesting");
  const progress = resources.states.find((state) => state.name.replaceAll(/\s+/g, "").toLowerCase() === "inprogress");
  return {
    name: "Create Bug",
    trigger: "state_changed",
    trigger_options: { from_state: testing?.id, to_state: progress?.id },
    conditions: [{ field: "work_item_type", operator: "equals", value: task?.id }],
    actions: [
      {
        type: "create_work_item",
        type_id: bug?.id,
        parent_mode: "source",
        title: "Bug: {work_item_title}",
        priority: "none",
      },
    ],
  };
}

export function sourceTransitionHint(
  definition: AutomationDefinition,
  resources: AutomationResources
): string | undefined {
  if (definition.trigger !== "state_changed") return undefined;
  const options = definition.trigger_options ?? {};
  const from = resources.states.find((state) => state.id === options.from_state);
  const to = resources.states.find((state) => state.id === options.to_state);
  if (!from?.group || !to?.group || from.id === to.id || from.group !== to.group) return undefined;
  return options.enter_group_only
    ? `${from.name} and ${to.name} are both in the ${from.group} state group. This rule also requires entering a different group, so this transition will be skipped. Allow transitions within this group or review the group filters.`
    : `${from.name} and ${to.name} are both in the ${from.group} state group. This rule matches the specific state change, including changes within that group.`;
}
