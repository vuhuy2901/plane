# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from plane.api.serializers import WorkspaceLiteSerializer
from plane.api.views.base import BaseAPIView
from plane.db.models import Workspace


class WorkspaceListAPIEndpoint(BaseAPIView):
    """List workspaces accessible to the authenticated API token owner."""

    serializer_class = WorkspaceLiteSerializer
    model = Workspace
    use_read_replica = True

    def get(self, request):
        workspaces = (
            Workspace.objects.filter(
                workspace_member__member=request.user,
                workspace_member__is_active=True,
            )
            .order_by("name")
            .distinct()
        )
        return self.paginate(
            request=request,
            queryset=workspaces,
            on_results=lambda items: WorkspaceLiteSerializer(items, many=True).data,
        )
