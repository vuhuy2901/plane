import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

export type TIssueImportMetadata = {
  source: string;
  source_issue_id: string;
  source_issue_key: string;
  file_sha256: string;
  source_timezone: string;
  fields: { column_index: number; name: string; value: string }[];
};

export class IssueImportMetadataService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async retrieve(workspaceSlug: string, projectId: string, issueId: string): Promise<TIssueImportMetadata | null> {
    const response = await this.get(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/import-metadata/`
    );
    return response.data;
  }
}
