# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")

from django.core.asgi import get_asgi_application  # noqa: E402

# Initialize Django before importing the MCP integration, which imports API
# authentication and therefore ORM models.
django_asgi_app = get_asgi_application()

from plane.mcp import create_mcp_http_app, create_personal_mcp_http_app, mcp_server, set_plane_api_application  # noqa: E402

set_plane_api_application(django_asgi_app)
mcp_http_app = create_mcp_http_app()
personal_mcp_http_app = create_personal_mcp_http_app(mcp_http_app)


class PlaneASGIApplication:
    """Route MCP HTTP traffic and manage its session manager lifecycle."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return

        if scope["type"] == "http":
            path = scope.get("path", "")
            if path.rstrip("/") == "/mcp":
                await mcp_http_app(scope, receive, send)
                return
            if path.startswith("/mcp/c/"):
                await personal_mcp_http_app(scope, receive, send)
                return

        await django_asgi_app(scope, receive, send)

    @staticmethod
    async def _lifespan(receive, send):
        async with mcp_server.session_manager.run():
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return


application = PlaneASGIApplication()
