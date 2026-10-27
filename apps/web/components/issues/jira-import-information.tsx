import { useState } from "react";
import useSWR from "swr";
import { IssueImportMetadataService } from "@/services/issue-import-metadata.service";

const service = new IssueImportMetadataService();

type Props = { workspaceSlug: string; projectId: string; issueId: string };

export function JiraImportInformation({ workspaceSlug, projectId, issueId }: Props) {
  const [showEmpty, setShowEmpty] = useState(false);
  const { data, error, mutate } = useSWR(["issue-import-metadata", workspaceSlug, projectId, issueId], () =>
    service.retrieve(workspaceSlug, projectId, issueId)
  );
  if (error) {
    return (
      <div className="text-sm my-4 text-secondary" role="alert">
        Không tải được thông tin nhập từ Jira.{" "}
        <button type="button" className="underline" onClick={() => void mutate()}>
          Thử lại
        </button>
      </div>
    );
  }
  if (!data) return null;
  const counts = new Map<string, number>();
  data.fields.forEach((field) => counts.set(field.name, (counts.get(field.name) ?? 0) + 1));
  const occurrences = new Map<string, number>();
  const fields = data.fields.map((field) => {
    const occurrence = (occurrences.get(field.name) ?? 0) + 1;
    occurrences.set(field.name, occurrence);
    return { ...field, label: (counts.get(field.name) ?? 0) > 1 ? `${field.name} (${occurrence})` : field.name };
  });
  return (
    <details className="my-5 rounded-lg border border-subtle bg-surface-1">
      <summary className="text-sm cursor-pointer px-4 py-3 font-medium">
        Thông tin Jira · {data.source_issue_key}
      </summary>
      <div className="border-t border-subtle px-4 pb-4">
        <div className="text-xs flex flex-wrap items-center justify-between gap-3 py-3 text-secondary">
          <span>
            Dữ liệu gốc chỉ đọc · {data.fields.length} cột · Múi giờ {data.source_timezone}
          </span>
          <label className="flex cursor-pointer items-center gap-2">
            <input type="checkbox" checked={showEmpty} onChange={(event) => setShowEmpty(event.target.checked)} />
            Hiện cả trường trống
          </label>
        </div>
        <dl className="divide-y divide-subtle">
          {fields
            .filter((field) => showEmpty || field.value !== "")
            .map((field) => (
              <div
                key={field.column_index}
                className="grid gap-1 py-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] sm:gap-4"
              >
                <dt className="text-xs break-words text-secondary">{field.label}</dt>
                <dd className="text-sm min-w-0 break-words whitespace-pre-wrap">
                  {field.value === "" ? <span className="text-tertiary">Trống</span> : field.value}
                </dd>
              </div>
            ))}
        </dl>
      </div>
    </details>
  );
}
