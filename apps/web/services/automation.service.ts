import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

export type AutomationCondition = { field: string; operator: string; value?: string };
export type AutomationAction = {
  target?: "current" | "parent";
  type: string;
  mode?: string;
  member_id?: string;
  only_if_unassigned?: boolean;
  replace_assignees?: boolean;
  state_id?: string;
  label_id?: string;
  priority?: string;
  text?: string;
  days?: number;
  operation?: "add" | "remove";
  date?: string;
  timezone?: string;
  type_id?: string;
  parent_mode?: "none" | "source";
  title?: string;
  description?: string;
  relation?: string;
  relation_type?: string;
  source_mode?: "triggering" | "created" | "specific";
  source_id?: string;
  target_mode?: "triggering" | "created" | "specific";
  target_id?: string;
};
export type TriggerOptions = {
  type_id?: string;
  field?: string;
  from_state?: string;
  to_state?: string;
  from_group?: string;
  to_group?: string;
  enter_group_only?: boolean;
  subtask_only?: boolean;
  from_priority?: string;
  to_priority?: string;
  previous_assignee?: string;
  new_assignee?: string;
  author_id?: string;
  relation_type?: string;
  source_id?: string;
  target_id?: string;
  frequency?: string;
  time?: string;
  timezone?: string;
  weekday?: number;
  filters?: AutomationCondition[];
};
export type AutomationDefinition = {
  name: string;
  trigger: string;
  trigger_options?: TriggerOptions;
  conditions: AutomationCondition[];
  actions: AutomationAction[];
  schema_version?: number;
};
export type AutomationRule = AutomationDefinition & {
  id: string;
  enabled: boolean;
  revision: number;
  execution_count?: number;
};
export type AutomationTemplate = AutomationDefinition & {
  id: string;
  category: string;
  requires: string[];
  description?: string;
};
export type AutomationResource = { id: string; name: string };
export type AutomationTypeResource = AutomationResource & { start_state_id?: string | null };
export type AutomationStateResource = AutomationResource & { group?: string };
export type AutomationResources = {
  work_items: AutomationResource[];
  members: AutomationResource[];
  types: AutomationTypeResource[];
  states: AutomationStateResource[];
  labels: AutomationResource[];
  timezone?: string;
  catalog?: {
    triggers: string[];
    actions: string[];
    operators: Record<string, string[]>;
    relations: string[];
    update_fields: string[];
  };
  limits?: { enabled_rules: number; conditions: number; actions: number };
};
export type AutomationEvaluationCheck = {
  field: string;
  operator: string;
  expected?: unknown;
  actual?: unknown;
  matched: boolean;
  reason?: string;
};
export type AutomationEvaluation = {
  matched: boolean;
  trigger: {
    matched: boolean;
    expected?: string;
    actual?: string[];
    checks: AutomationEvaluationCheck[];
  };
  conditions: AutomationEvaluationCheck[];
};
export type AutomationTestResult = {
  valid: boolean;
  conditions_match: boolean;
  trigger_match?: boolean;
  action_count?: number;
  reason?: string;
  writes: number;
  dry_run?: boolean;
  evaluation?: AutomationEvaluation;
  preview_mode?: "recorded_event" | "simulated_created" | "current_snapshot";
  event_id?: string | null;
};
export type AutomationHistory = {
  id: string;
  rule_id?: string | null;
  status: string;
  detail: string;
  created_at: string;
  snapshot: {
    definition: AutomationDefinition;
    work_item: { id: string; name: string; sequence_id: number };
    parent_id?: string | null;
    before?: Record<string, unknown>;
    trigger_details?: Record<string, unknown>;
    triggers?: string[];
    evaluation?: AutomationEvaluation;
    steps?: Record<
      string,
      Record<
        string,
        {
          created_issue_id?: string;
          source_issue_id?: string;
          target_issue_id?: string;
          relation_type?: string;
          done?: boolean;
          changed?: boolean;
        }
      >
    >;
  };
};

export class AutomationService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }
  private base(workspace: string, project: string) {
    return `/api/workspaces/${workspace}/projects/${project}/automations`;
  }
  async rules(w: string, p: string): Promise<AutomationRule[]> {
    return this.get(`${this.base(w, p)}/rules/`).then((r) => r.data);
  }
  async rule(w: string, p: string, id: string): Promise<AutomationRule> {
    return this.get(`${this.base(w, p)}/rules/${id}/`).then((r) => r.data);
  }
  async templates(w: string, p: string): Promise<AutomationTemplate[]> {
    return this.get(`${this.base(w, p)}/templates/`).then((r) => r.data);
  }
  async resources(w: string, p: string): Promise<AutomationResources> {
    return this.get(`${this.base(w, p)}/resources/`).then((r) => r.data);
  }
  async save(w: string, p: string, definition: AutomationDefinition, rule?: AutomationRule): Promise<AutomationRule> {
    if (rule)
      return this.put(`${this.base(w, p)}/rules/${rule.id}/`, { ...definition, expected_revision: rule.revision }).then(
        (r) => r.data
      );
    return this.post(`${this.base(w, p)}/rules/`, definition).then((r) => r.data);
  }
  async operation(
    w: string,
    p: string,
    id: string,
    operation: string,
    data: Record<string, unknown> = {}
  ): Promise<unknown> {
    return this.post(`${this.base(w, p)}/rules/${id}/${operation}/`, data).then((r) => r.data);
  }
  async test(w: string, p: string, id: string, issueId: string, eventId?: string): Promise<AutomationTestResult> {
    return this.post(`${this.base(w, p)}/rules/${id}/test/`, {
      issue_id: issueId,
      ...(eventId ? { event_id: eventId } : {}),
    }).then((r) => r.data);
  }
  async setEnabled(w: string, p: string, id: string, enabled: boolean): Promise<AutomationRule> {
    return this.post(`${this.base(w, p)}/rules/${id}/status/`, { enabled }).then((r) => r.data);
  }
  async duplicate(w: string, p: string, id: string): Promise<AutomationRule> {
    return this.post(`${this.base(w, p)}/rules/${id}/duplicate/`, {}).then((r) => r.data);
  }
  async remove(w: string, p: string, id: string): Promise<void> {
    await this.delete(`${this.base(w, p)}/rules/${id}/`);
  }
  async history(
    w: string,
    p: string,
    page: number,
    status: string
  ): Promise<{ results: AutomationHistory[]; has_more: boolean }> {
    return this.get(`${this.base(w, p)}/history/`, { params: { page, ...(status ? { status } : {}) } }).then(
      (r) => r.data
    );
  }
}
