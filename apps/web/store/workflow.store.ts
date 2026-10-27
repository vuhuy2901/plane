/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { action, makeObservable, observable, runInAction } from "mobx";
import type {
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
import { WorkflowService } from "@/services/workflow.service";

export interface IWorkflowStore {
  workflows: TWorkflow[];
  draft: TWorkflowVersion | null;
  validation: TWorkflowValidation | null;
  isLoading: boolean;
  issueTypes: TWorkflowIssueType[];
  mappings: TWorkflowMapping[];
  versions: TWorkflowVersion[];
  fetchWorkflows: (workspaceSlug: string, projectId: string) => Promise<TWorkflow[]>;
  createWorkflow: (workspaceSlug: string, projectId: string, name: string, description?: string) => Promise<TWorkflow>;
  updateWorkflow: (workspaceSlug: string, projectId: string, workflowId: string, name: string) => Promise<TWorkflow>;
  deleteWorkflow: (workspaceSlug: string, projectId: string, workflowId: string) => Promise<void>;
  fetchDraft: (workspaceSlug: string, projectId: string, workflowId: string) => Promise<TWorkflowVersion>;
  saveDraft: (
    workspaceSlug: string,
    projectId: string,
    workflowId: string,
    states: TWorkflowState[],
    transitions: TWorkflowTransition[],
    token: TWorkflowDraftToken
  ) => Promise<TWorkflowVersion>;
  validateDraft: (workspaceSlug: string, projectId: string, workflowId: string) => Promise<TWorkflowValidation>;
  publishDraft: (
    workspaceSlug: string,
    projectId: string,
    workflowId: string,
    token: TWorkflowDraftToken
  ) => Promise<TWorkflowVersion>;
  fetchVersions: (workspaceSlug: string, projectId: string, workflowId: string) => Promise<TWorkflowVersion[]>;
  rollbackVersion: (
    workspaceSlug: string,
    projectId: string,
    workflowId: string,
    versionId: string
  ) => Promise<TWorkflowVersion>;
  fetchMappings: (workspaceSlug: string, projectId: string) => Promise<TWorkflowMapping[]>;
  createIssueType: (
    workspaceSlug: string,
    projectId: string,
    name: string,
    color?: string
  ) => Promise<TWorkflowIssueType>;
  updateIssueType: (
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    name: string,
    color?: string
  ) => Promise<TWorkflowIssueType>;
  deleteIssueType: (workspaceSlug: string, projectId: string, issueTypeId: string) => Promise<void>;
  saveMappings: (
    workspaceSlug: string,
    projectId: string,
    mappings: TWorkflowMapping[],
    migrations?: TWorkflowStateMigration[]
  ) => Promise<void>;
  previewMappings: (
    workspaceSlug: string,
    projectId: string,
    mappings: TWorkflowMapping[]
  ) => Promise<TWorkflowMappingPreview>;
  saveHierarchy: (workspaceSlug: string, projectId: string, levels: { id: string; level: number }[]) => Promise<void>;
}

export class WorkflowStore implements IWorkflowStore {
  workflows: TWorkflow[] = [];
  draft: TWorkflowVersion | null = null;
  validation: TWorkflowValidation | null = null;
  isLoading = false;
  issueTypes: TWorkflowIssueType[] = [];
  mappings: TWorkflowMapping[] = [];
  versions: TWorkflowVersion[] = [];
  private service = new WorkflowService();

  constructor() {
    makeObservable(this, {
      workflows: observable,
      draft: observable,
      validation: observable,
      isLoading: observable,
      issueTypes: observable,
      mappings: observable,
      versions: observable,
      fetchWorkflows: action,
      createWorkflow: action,
      updateWorkflow: action,
      deleteWorkflow: action,
      fetchDraft: action,
      saveDraft: action,
      validateDraft: action,
      publishDraft: action,
      fetchVersions: action,
      rollbackVersion: action,
      fetchMappings: action,
      createIssueType: action,
      updateIssueType: action,
      deleteIssueType: action,
      saveMappings: action,
      saveHierarchy: action,
    });
  }

  fetchWorkflows = async (workspaceSlug: string, projectId: string) => {
    this.isLoading = true;
    try {
      const workflows = await this.service.list(workspaceSlug, projectId);
      runInAction(() => (this.workflows = workflows));
      return workflows;
    } finally {
      runInAction(() => (this.isLoading = false));
    }
  };

  createWorkflow = async (workspaceSlug: string, projectId: string, name: string, description = "") => {
    const workflow = await this.service.create(workspaceSlug, projectId, { name, description });
    runInAction(() => this.workflows.push(workflow));
    return workflow;
  };

  updateWorkflow = async (workspaceSlug: string, projectId: string, workflowId: string, name: string) => {
    const workflow = await this.service.update(workspaceSlug, projectId, workflowId, name);
    runInAction(() => {
      this.workflows = this.workflows.map((item) => (item.id === workflowId ? workflow : item));
    });
    return workflow;
  };

  deleteWorkflow = async (workspaceSlug: string, projectId: string, workflowId: string) => {
    await this.service.deleteWorkflow(workspaceSlug, projectId, workflowId);
    runInAction(() => {
      this.workflows = this.workflows.filter((item) => item.id !== workflowId);
    });
  };

  fetchDraft = async (workspaceSlug: string, projectId: string, workflowId: string) => {
    this.isLoading = true;
    try {
      const draft = await this.service.getDraft(workspaceSlug, projectId, workflowId);
      runInAction(() => {
        this.draft = draft;
        this.validation = null;
      });
      return draft;
    } finally {
      runInAction(() => (this.isLoading = false));
    }
  };

  saveDraft = async (
    workspaceSlug: string,
    projectId: string,
    workflowId: string,
    states: TWorkflowState[],
    transitions: TWorkflowTransition[],
    token: TWorkflowDraftToken
  ) => {
    const draft = await this.service.saveDraft(workspaceSlug, projectId, workflowId, { states, transitions, ...token });
    runInAction(() => {
      this.draft = draft;
      this.validation = null;
    });
    return draft;
  };

  validateDraft = async (workspaceSlug: string, projectId: string, workflowId: string) => {
    const validation = await this.service.validate(workspaceSlug, projectId, workflowId);
    runInAction(() => (this.validation = validation));
    return validation;
  };

  publishDraft = async (workspaceSlug: string, projectId: string, workflowId: string, token: TWorkflowDraftToken) => {
    const result = await this.service.publish(workspaceSlug, projectId, workflowId, token);
    runInAction(() => {
      this.draft = null;
      this.validation = result.validation;
    });
    await this.fetchWorkflows(workspaceSlug, projectId);
    return result.version;
  };

  fetchVersions = async (workspaceSlug: string, projectId: string, workflowId: string) => {
    const versions = await this.service.listVersions(workspaceSlug, projectId, workflowId);
    runInAction(() => (this.versions = versions));
    return versions;
  };

  rollbackVersion = async (workspaceSlug: string, projectId: string, workflowId: string, versionId: string) => {
    const draft = await this.service.rollback(workspaceSlug, projectId, workflowId, versionId);
    runInAction(() => {
      this.draft = draft;
      this.validation = null;
    });
    return draft;
  };

  fetchMappings = async (workspaceSlug: string, projectId: string) => {
    const [issueTypes, mappings] = await Promise.all([
      this.service.listIssueTypes(workspaceSlug, projectId),
      this.service.listMappings(workspaceSlug, projectId),
    ]);
    runInAction(() => {
      this.issueTypes = issueTypes;
      this.mappings = mappings;
    });
    return mappings;
  };

  createIssueType = async (workspaceSlug: string, projectId: string, name: string, color?: string) => {
    const issueType = await this.service.createIssueType(workspaceSlug, projectId, name, color);
    runInAction(() => this.issueTypes.push(issueType));
    return issueType;
  };

  updateIssueType = async (
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    name: string,
    color?: string
  ) => {
    const issueType = await this.service.updateIssueType(workspaceSlug, projectId, issueTypeId, name, color);
    runInAction(() => {
      this.issueTypes = this.issueTypes.map((item) => (item.id === issueTypeId ? issueType : item));
    });
    return issueType;
  };

  deleteIssueType = async (workspaceSlug: string, projectId: string, issueTypeId: string) => {
    await this.service.deleteIssueType(workspaceSlug, projectId, issueTypeId);
    runInAction(() => {
      this.issueTypes = this.issueTypes.filter((item) => item.id !== issueTypeId);
      this.mappings = this.mappings.filter((item) => item.issue_type_id !== issueTypeId);
    });
  };

  previewMappings = (workspaceSlug: string, projectId: string, mappings: TWorkflowMapping[]) =>
    this.service.previewMappings(workspaceSlug, projectId, mappings);

  saveMappings = async (
    workspaceSlug: string,
    projectId: string,
    mappings: TWorkflowMapping[],
    migrations: TWorkflowStateMigration[] = []
  ) => {
    const saved = await this.service.saveMappings(workspaceSlug, projectId, mappings, migrations);
    runInAction(() => (this.mappings = saved));
  };

  saveHierarchy = async (workspaceSlug: string, projectId: string, levels: { id: string; level: number }[]) => {
    const saved = await this.service.saveHierarchy(workspaceSlug, projectId, levels);
    runInAction(() => {
      const byId = new Map(saved.map((item) => [item.id, item.level]));
      this.issueTypes = this.issueTypes.map((item) => ({ ...item, level: byId.get(item.id) ?? item.level }));
    });
  };
}
