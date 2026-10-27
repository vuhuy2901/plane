# The workflow endpoints deliberately share their implementation with the web
# app routes. This keeps API-token and MCP behavior identical to session clients.
from plane.app.urls.workflow import urlpatterns

__all__ = ["urlpatterns"]
