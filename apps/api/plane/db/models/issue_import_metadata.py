from django.db import models

from .project import ProjectBaseModel


class IssueImportMetadata(ProjectBaseModel):
    """Lossless source columns, including repeated headers and empty cells."""

    issue = models.OneToOneField("db.Issue", on_delete=models.CASCADE, related_name="import_metadata")
    source = models.CharField(max_length=50, default="jira_csv")
    source_issue_id = models.CharField(max_length=255)
    source_issue_key = models.CharField(max_length=255)
    file_sha256 = models.CharField(max_length=64)
    source_timezone = models.CharField(max_length=100)
    fields = models.JSONField(default=list)

    class Meta:
        db_table = "issue_import_metadata"
