/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type {
  TIssueWorkflowTransitions,
  TWorkItemWorkflowPreview,
  TWorkflow,
  TWorkflowIssueType,
  TWorkflowMapping,
  TWorkflowMappingPreview,
  TWorkflowStateMigration,
  TWorkflowState,
  TWorkflowTransition,
  TWorkflowValidation,
  TWorkflowVersion,
  TWorkflowDraftToken,
} from "@plane/types";
import { APIService } from "@/services/api.service";

export class WorkflowService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private base(workspaceSlug: string, projectId: string) {
    return `/api/workspaces/${workspaceSlug}/projects/${projectId}`;
  }

  async list(workspaceSlug: string, projectId: string): Promise<TWorkflow[]> {
    return this.get(`${this.base(workspaceSlug, projectId)}/workflows/`).then((response) => response.data);
  }

  async create(workspaceSlug: string, projectId: string, data: Pick<TWorkflow, "name" | "description">) {
    return this.post(`${this.base(workspaceSlug, projectId)}/workflows/`, data).then(
      (response) => response.data as TWorkflow
    );
  }

  async update(workspaceSlug: string, projectId: string, workflowId: string, name: string): Promise<TWorkflow> {
    return this.patch(`${this.base(workspaceSlug, projectId)}/workflows/${workflowId}/`, { name }).then(
      (response) => response.data
    );
  }

  async deleteWorkflow(workspaceSlug: string, projectId: string, workflowId: string): Promise<void> {
    await this.delete(`${this.base(workspaceSlug, projectId)}/workflows/${workflowId}/`);
  }

  async getDraft(workspaceSlug: string, projectId: string, workflowId: string): Promise<TWorkflowVersion> {
    return this.get(`${this.base(workspaceSlug, projectId)}/workflows/${workflowId}/draft/`).then(
      (response) => response.data
    );
  }

  async saveDraft(
    workspaceSlug: string,
    projectId: string,
    workflowId: string,
    data: { states: TWorkflowState[]; transitions: TWorkflowTransition[] } & TWorkflowDraftToken
  ): Promise<TWorkflowVersion> {
    return this.put(`${this.base(workspaceSlug, projectId)}/workflows/${workflowId}/draft/`, data).then(
      (response) => response.data
    );
  }

  async validate(workspaceSlug: string, projectId: string, workflowId: string): Promise<TWorkflowValidation> {
    return this.post(`${this.base(workspaceSlug, projectId)}/workflows/${workflowId}/validate/`, {}).then(
      (response) => response.data
    );
  }

  async publish(workspaceSlug: string, projectId: string, workflowId: string, token: TWorkflowDraftToken) {
    return this.post(`${this.base(workspaceSlug, projectId)}/workflows/${workflowId}/publish/`, token).then(
      (response) => response.data as { version: TWorkflowVersion; validation: TWorkflowValidation }
    );
  }

  async listVersions(workspaceSlug: string, projectId: string, workflowId: string): Promise<TWorkflowVersion[]> {
    return this.get(`${this.base(workspaceSlug, projectId)}/workflows/${workflowId}/versions/`).then(
      (response) => response.data
    );
  }

  async rollback(
    workspaceSlug: string,
    projectId: string,
    workflowId: string,
    versionId: string
  ): Promise<TWorkflowVersion> {
    return this.post(`${this.base(workspaceSlug, projectId)}/workflows/${workflowId}/versions/${versionId}/rollback/`, {
      replace_draft: true,
    }).then((response) => response.data);
  }

  async getIssueTransitions(
    workspaceSlug: string,
    projectId: string,
    issueId: string
  ): Promise<TIssueWorkflowTransitions> {
    return this.get(`${this.base(workspaceSlug, projectId)}/work-items/${issueId}/workflow-transitions/`).then(
      (response) => response.data
    );
  }

  async getIssueWorkflow(workspaceSlug: string, projectId: string, issueId: string): Promise<TWorkItemWorkflowPreview> {
    return this.get(`${this.base(workspaceSlug, projectId)}/work-items/${issueId}/workflow/`).then(
      (response) => response.data
    );
  }

  async getIssueTypeWorkflowStates(workspaceSlug: string, projectId: string, issueTypeId: string) {
    return this.get(`${this.base(workspaceSlug, projectId)}/work-item-types/${issueTypeId}/workflow-states/`).then(
      (response) => response.data as { workflow_enabled: boolean; state_ids: string[]; start_state_id: string | null }
    );
  }

  async listIssueTypes(workspaceSlug: string, projectId: string): Promise<TWorkflowIssueType[]> {
    return this.get(`${this.base(workspaceSlug, projectId)}/workflow-issue-types/`).then((response) => response.data);
  }

  async createIssueType(
    workspaceSlug: string,
    projectId: string,
    name: string,
    color = "#3E63DD"
  ): Promise<TWorkflowIssueType> {
    return this.post(`${this.base(workspaceSlug, projectId)}/workflow-issue-types/`, { name, color }).then(
      (response) => response.data
    );
  }

  async updateIssueType(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    name: string,
    color?: string
  ): Promise<TWorkflowIssueType> {
    return this.patch(`${this.base(workspaceSlug, projectId)}/workflow-issue-types/${issueTypeId}/`, {
      name,
      color,
    }).then((response) => response.data);
  }

  async deleteIssueType(workspaceSlug: string, projectId: string, issueTypeId: string): Promise<void> {
    await this.delete(`${this.base(workspaceSlug, projectId)}/workflow-issue-types/${issueTypeId}/`);
  }

  async saveHierarchy(workspaceSlug: string, projectId: string, levels: { id: string; level: number }[]) {
    return this.put(`${this.base(workspaceSlug, projectId)}/work-item-hierarchy/`, { levels }).then(
      (response) => response.data as { id: string; level: number }[]
    );
  }

  async listMappings(workspaceSlug: string, projectId: string): Promise<TWorkflowMapping[]> {
    return this.get(`${this.base(workspaceSlug, projectId)}/workflows/mappings/`).then((response) => response.data);
  }

  async saveMappings(
    workspaceSlug: string,
    projectId: string,
    mappings: TWorkflowMapping[],
    stateMigrations: TWorkflowStateMigration[] = []
  ): Promise<TWorkflowMapping[]> {
    return this.put(`${this.base(workspaceSlug, projectId)}/workflows/mappings/`, {
      mappings,
      state_migrations: stateMigrations,
    }).then((response) => response.data);
  }

  async previewMappings(
    workspaceSlug: string,
    projectId: string,
    mappings: TWorkflowMapping[]
  ): Promise<TWorkflowMappingPreview> {
    return this.post(`${this.base(workspaceSlug, projectId)}/workflows/mappings/`, { mappings }).then(
      (response) => response.data
    );
  }
}
