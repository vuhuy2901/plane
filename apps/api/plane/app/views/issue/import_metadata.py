from django.shortcuts import get_object_or_404
from rest_framework.response import Response

from plane.app.permissions import ProjectEntityPermission
from plane.app.views.base import BaseAPIView
from plane.db.models import Issue, IssueImportMetadata


class IssueImportMetadataEndpoint(BaseAPIView):
    permission_classes = [ProjectEntityPermission]

    def get(self, request, slug, project_id, issue_id):
        issue = get_object_or_404(
            Issue.all_objects,
            pk=issue_id,
            project_id=project_id,
            workspace__slug=slug,
            deleted_at__isnull=True,
        )
        metadata = IssueImportMetadata.objects.filter(issue=issue).first()
        if metadata is None:
            return Response(None)
        return Response(
            {
                "source": metadata.source,
                "source_issue_id": metadata.source_issue_id,
                "source_issue_key": metadata.source_issue_key,
                "file_sha256": metadata.file_sha256,
                "source_timezone": metadata.source_timezone,
                "fields": metadata.fields,
            }
        )
