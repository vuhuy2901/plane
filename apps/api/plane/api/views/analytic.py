"""PAT-authenticated access to the shared permission-scoped analytics report."""

from plane.api.views.base import BaseAPIView
from plane.app.views.analytic.report import WorkspaceReportEndpoint


class WorkspaceAnalyticsAPIEndpoint(BaseAPIView):
    """Use API-key authentication/throttling and the web report's workspace/project permissions."""

    get = WorkspaceReportEndpoint.get
