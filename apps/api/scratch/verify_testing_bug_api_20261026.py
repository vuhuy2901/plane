"""Read-only verification of the saved automation preview through its API view."""

import json

from rest_framework.test import APIRequestFactory, force_authenticate

from plane.app.views.automation import AutomationRuleOperationAPIView
from plane.db.models import ProjectAutomationRule


rule = ProjectAutomationRule.objects.select_related("project__workspace", "execution_actor").get(
    pk="4c8a5ab8-74d8-4b3c-8483-abe6681244d5"
)
path = (
    f"/api/workspaces/{rule.project.workspace.slug}/projects/{rule.project_id}/automations/"
    f"rules/{rule.id}/test/"
)
request = APIRequestFactory().post(path, {"issue_id": "f006acaf-4b3f-4b6a-ac6a-b4f70d519694"}, format="json")
force_authenticate(request, user=rule.execution_actor)
response = AutomationRuleOperationAPIView.as_view()(
    request,
    slug=rule.project.workspace.slug,
    project_id=str(rule.project_id),
    rule_id=str(rule.id),
    operation="test",
)
assert response.status_code == 200, response.data
assert response.data["valid"] and response.data["evaluation"]["matched"], response.data
assert response.data["action_count"] == 1 and response.data["writes"] == 0, response.data
print(json.dumps({"status_code": response.status_code, **response.data}, default=str))
