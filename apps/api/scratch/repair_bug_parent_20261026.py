"""Repair the confirmed automation-created Bug and enable source-child placement."""

from copy import deepcopy
import json
import os

from django.db import transaction
from django.utils import timezone

from plane.app.serializers.issue import IssueCreateSerializer
from plane.db.models import Issue, ProjectAutomationRule, ProjectAutomationExecution
from plane.services.automation_rules import validate_definition
from plane.services.automation_runtime import automation_origin


with transaction.atomic():
    rule = ProjectAutomationRule.objects.select_for_update().select_related("project", "execution_actor").get(
        pk="4c8a5ab8-74d8-4b3c-8483-abe6681244d5", project_id="46fdbf9a-9260-4a15-a64a-a2cefe169142"
    )
    execution = ProjectAutomationExecution.objects.get(
        pk="ba0ded18-fc65-4be3-b509-120363535edb", project=rule.project, rule_key=rule.id, status="success"
    )
    bug_id = "0c55e184-8efa-4c96-8be0-f409f2b10252"
    assert any(
        step.get("created_issue_id") == bug_id
        for step in execution.snapshot["steps"][str(rule.id)].values()
    ), "Bug must be proven to originate from this execution."
    source = Issue.objects.select_for_update().get(pk=execution.snapshot["work_item"]["id"], project=rule.project)
    bug = Issue.objects.select_for_update().get(pk=bug_id, project=rule.project)
    source_parent = source.parent_id
    if bug.parent_id not in (None, source.id):
        raise RuntimeError("Bug has been assigned to another parent; inspect before changing it.")
    original = {"definition": deepcopy(rule.definition), "revision": rule.revision, "bug_parent_id": bug.parent_id}
    definition = deepcopy(rule.definition)
    creates = [action for action in definition["actions"] if action["type"] == "create_work_item" and str(action["type_id"]) == str(bug.type_id)]
    assert len(creates) == 1, "Expected exactly one Bug creation action."
    creates[0]["parent_mode"] = "source"
    definition = validate_definition(rule.project, definition)
    serializer = IssueCreateSerializer(bug, data={"parent_id": str(source.id)}, partial=True, context={
        "project_id": str(rule.project_id), "workspace_id": str(rule.workspace_id), "actor": rule.execution_actor,
    })
    serializer.is_valid(raise_exception=True)
    apply = os.environ.get("APPLY_BUG_PARENT_REPAIR") == "1"
    if apply:
        if rule.definition != definition:
            if rule.revision != 4:
                raise RuntimeError("The rule changed since diagnosis. Inspect its current revision.")
            rule.definition = definition
            rule.revision += 1
            rule.enabled = True
            rule.enabled_at = timezone.now()
            rule.schedule_cursor = {}
            rule.save(update_fields=["definition", "revision", "enabled", "enabled_at", "schedule_cursor", "updated_at"])
        if bug.parent_id != source.id:
            token = automation_origin.set(True)
            try:
                serializer.save(updated_by=rule.execution_actor)
            finally:
                automation_origin.reset(token)
        source.refresh_from_db()
        bug.refresh_from_db()
        assert source.parent_id == source_parent, "Source Task's parent must not change."
        assert bug.parent_id == source.id, "Created Bug must be a child of its source Task."
        from django.urls import resolve
        from rest_framework.test import APIRequestFactory, force_authenticate

        path = f"/api/workspaces/{rule.project.workspace.slug}/projects/{rule.project_id}/issues/{source.id}/sub-issues/"
        request = APIRequestFactory().get(path)
        force_authenticate(request, user=rule.execution_actor)
        match = resolve(path)
        response = match.func(request, **match.kwargs)
        assert response.status_code == 200, response.data
        assert str(bug.id) in {str(child["id"]) for child in response.data["sub_issues"]}, response.data
    print(json.dumps({
        "applied": apply, "original": original, "definition": definition,
        "rule_revision": rule.revision,
        "bug_id": str(bug.id), "bug_number": bug.sequence_id,
        "source_id": str(source.id), "source_number": source.sequence_id,
        "source_parent_id": str(source_parent),
        "bug_parent_id": str(bug.parent_id) if bug.parent_id else None,
        "proposed_bug_parent_id": str(source.id),
    }, default=str))
