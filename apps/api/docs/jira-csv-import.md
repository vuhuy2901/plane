# Jira CSV import

The importer creates one new project from a UTF-8 Jira CSV export. It preserves
repeated headers and empty cells in per-issue metadata. It does not update an
existing project with different source data.

Run inside the API environment, using an active workspace administrator as actor:

```sh
python manage.py import_jira_csv /path/to/Jira.csv --workspace WORKSPACE --actor USER_UUID
python manage.py import_jira_csv /path/to/Jira.csv --workspace WORKSPACE --actor USER_UUID --apply
python manage.py verify_jira_csv_import /path/to/Jira.csv --workspace WORKSPACE
```

The first command is read-only. `--apply` creates the project and related records
in one transaction. Repeating the same source file returns `already_imported`.
A conflicting project identifier, name, or source checksum is rejected.
Verification compares every source cell, native issue fields, parents, labels,
cycles, blocking relations, and the next issue number without writing data.

The default source timezone is `Asia/Bangkok` (UTC+7); override with `--timezone`.
Date strings use `15/Oct/26 12:26 AM`. Original strings always remain in metadata.
Issue keys are preserved, including numeric gaps. Existing shared work types are
reused by normalized name, with project-specific levels Epic 0, Task/Bug 1,
Subtask 2. Workflow transitions are not inferred from exported statuses.

Unmapped Jira users remain source identities in the metadata; Plane assignees
stay empty. Sprint dates are left empty when absent from the export. The import
actor is a project administrator and cycle owner, not the historical Jira author.

Project members can retrieve read-only metadata at:

```text
GET /api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/import-metadata/
```

The response is `null` for an ordinary, non-imported issue, otherwise it includes
`source`, `source_issue_id`, `source_issue_key`, `file_sha256`, `source_timezone`,
and `fields`. Each field has its zero-based `column_index`, original `name`, and
original string `value`. The web UI shows these in **Thông tin Jira** on issue
details and peek views, with a toggle to include empty fields.
