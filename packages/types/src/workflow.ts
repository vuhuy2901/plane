export type TWorkflowStatus = "draft" | "published";

export type TWorkflowStateLayout = {
  position_x: number;
  position_y: number;
};

export type TWorkflowState = {
  id?: string;
  key: string;
  state_id: string | null;
  name: string;
  description: string;
  color: string;
  group: "backlog" | "unstarted" | "started" | "completed" | "cancelled" | "triage";
  is_start: boolean;
  is_end: boolean;
  layout: TWorkflowStateLayout;
};

export type TWorkflowTransition = {
  id?: string;
  source_key: string;
  target_key: string;
  target_state_id?: string | null;
  target_state?: {
    id: string;
    name: string;
    color: string;
    group: string;
    order?: number;
  } | null;
  direction?: "forward" | "backward";
  source_handle?: string | null;
  target_handle?: string | null;
  name: string;
  conditions: Record<string, unknown>[];
  permissions: { roles?: number[]; source_handle?: string | null; target_handle?: string | null };
  validators: Record<string, unknown>[];
  post_actions: Record<string, unknown>[];
};

export type TWorkflowVersion = {
  id: string;
  version: number;
  revision: number;
  status: TWorkflowStatus;
  published_at: string | null;
  published_by_id: string | null;
  states: TWorkflowState[];
  transitions: TWorkflowTransition[];
};

export type TWorkflowDraftToken = { draft_id: string; expected_revision: number };

export type TWorkflow = {
  id: string;
  name: string;
  description: string;
  active_version_id: string | null;
  draft_version_id: string | null;
  mapped_issue_type_ids: string[];
  created_at: string;
  updated_at: string;
};

export type TWorkflowValidation = {
  valid: boolean;
  errors: { code: string; message: string; state_id?: string; transition_id?: string }[];
  warnings: { code: string; message: string; state_id?: string; transition_id?: string }[];
};

export type TIssueWorkflowTransitions = {
  workflow_enabled: boolean;
  current_state?: {
    id: string;
    name: string;
    color: string;
    group: string;
    order?: number;
  } | null;
  transitions: TWorkflowTransition[];
};

export type TWorkItemWorkflowPreview = {
  current_state_id: string | null;
  workflow: {
    id: string;
    name: string;
    version: number;
    states: TWorkflowState[];
    transitions: Pick<
      TWorkflowTransition,
      "id" | "source_key" | "target_key" | "source_handle" | "target_handle" | "name"
    >[];
  } | null;
};

export type TWorkflowIssueType = {
  id: string;
  name: string;
  color: string;
  description: string;
  is_default: boolean;
  is_active: boolean;
  level: number;
};

export type TWorkflowMapping = { issue_type_id: string; workflow_id: string };

export type TWorkflowStateMigration = {
  issue_type_id: string;
  workflow_version_id: string;
  source_state_id: string | null;
  target_state_id: string;
  work_item_count: number;
};

export type TWorkflowMappingConflict = {
  issue_type_id: string;
  issue_type_name: string;
  workflow_id: string;
  workflow_name: string;
  workflow_version_id: string;
  source_state_id: string | null;
  source_state_name: string;
  source_state_group: string | null;
  work_item_count: number;
  target_states: { id: string; name: string; group: string }[];
  suggested_target_id: string | null;
};

export type TWorkflowMappingPreview = { conflicts: TWorkflowMappingConflict[]; work_item_count: number };
