from django.urls import path

from plane.app.views.automation import (
    AutomationRulesAPIView,
    AutomationRuleAPIView,
    AutomationRuleOperationAPIView,
    AutomationTemplatesAPIView,
    AutomationResourcesAPIView,
    AutomationHistoryAPIView,
)

base = "workspaces/<str:slug>/projects/<uuid:project_id>/automations/"
urlpatterns = [
    path(base + "rules/", AutomationRulesAPIView.as_view()),
    path(base + "rules/<uuid:rule_id>/", AutomationRuleAPIView.as_view()),
    path(base + "rules/<uuid:rule_id>/<str:operation>/", AutomationRuleOperationAPIView.as_view()),
    path(base + "templates/", AutomationTemplatesAPIView.as_view()),
    path(base + "resources/", AutomationResourcesAPIView.as_view()),
    path(base + "history/", AutomationHistoryAPIView.as_view()),
]
