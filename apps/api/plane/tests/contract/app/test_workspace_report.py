# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Contract coverage for permission-scoped workspace reporting."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from plane.db.models import (
    Issue,
    IssueAssignee,
    IssueType,
    Project,
    ProjectMember,
    State,
    User,
    WorkspaceMember,
)


@pytest.mark.contract
@pytest.mark.django_db
def test_workspace_report_counts_only_accessible_projects(workspace, create_user):
    member = User.objects.create(email=f"report-{uuid4().hex}@plane.so", username=f"report-{uuid4().hex[:8]}")
    WorkspaceMember.objects.create(workspace=workspace, member=member, role=15)
    own = Project.objects.create(name="Own", identifier="OWN", workspace=workspace)
    hidden = Project.objects.create(name="Hidden", identifier="HID", workspace=workspace)
    ProjectMember.objects.create(project=own, member=member, workspace=workspace, role=15)
    ProjectMember.objects.create(project=hidden, member=create_user, workspace=workspace, role=20)
    own_state = State.objects.create(name="Todo", project=own, workspace=workspace, group="unstarted", default=True)
    hidden_state = State.objects.create(
        name="Todo", project=hidden, workspace=workspace, group="unstarted", default=True
    )
    bug_type = IssueType.objects.create(name="Bug", workspace=workspace)
    Issue.objects.create(name="Visible bug", project=own, workspace=workspace, state=own_state, type=bug_type)
    Issue.objects.create(name="Hidden bug", project=hidden, workspace=workspace, state=hidden_state, type=bug_type)

    client = APIClient()
    client.force_authenticate(user=member)
    response = client.get(
        f"/api/workspaces/{workspace.slug}/analytics-report/", {"project_ids": f"{own.id},{hidden.id}"}
    )

    assert response.status_code == 200, response.data
    assert response.data["totals"]["total"] == 1
    assert response.data["bugs"]["total"] == 1
    assert [project["name"] for project in response.data["projects"]] == ["Own"]
    assert sum(row["count"] for row in response.data["states"]) == 1
    assert (
        client.get(f"/api/workspaces/{workspace.slug}/analytics-report/", {"project_ids": "bad-id"}).status_code == 400
    )


@pytest.mark.contract
@pytest.mark.django_db
def test_workspace_report_kpis_filters_and_parent_count_modes(workspace, create_user):
    project = Project.objects.create(name="Analytics", identifier="ANA", workspace=workspace)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    todo = State.objects.create(name="Todo", project=project, workspace=workspace, group="unstarted", default=True)
    done = State.objects.create(name="Done", project=project, workspace=workspace, group="completed")
    task_type = IssueType.objects.create(name="Task", workspace=workspace)
    bug_type = IssueType.objects.create(name="Bug", workspace=workspace)
    parent = Issue.objects.create(
        name="Overdue task",
        project=project,
        workspace=workspace,
        state=todo,
        type=task_type,
        priority="high",
        target_date=timezone.localdate() - timedelta(days=1),
    )
    bug = Issue.objects.create(
        name="Resolved child bug",
        project=project,
        workspace=workspace,
        state=done,
        type=bug_type,
        priority="urgent",
        parent=parent,
    )
    IssueAssignee.objects.create(issue=parent, assignee=create_user, project=project, workspace=workspace)
    IssueAssignee.objects.create(issue=bug, assignee=create_user, project=project, workspace=workspace)

    client = APIClient()
    client.force_authenticate(user=create_user)
    url = f"/api/workspaces/{workspace.slug}/analytics-report/"
    response = client.get(url, {"date_filter": "last_30_days"})

    assert response.status_code == 200, response.data
    assert response.data["totals"] == {
        **response.data["totals"],
        "total": 2,
        "completed": 1,
        "overdue": 1,
        "subtasks": 1,
        "total_bugs": 1,
        "open_bugs": 0,
        "completed_bugs": 1,
        "completion_rate": 50.0,
    }
    assert response.data["parenting"]["completed_subtasks"] == 1
    assert response.data["members"][0]["assigned"] == 2
    assert response.data["projects"][0]["progress"] == 50.0
    assert response.data["meta"]["date_basis"] == "work_item_created_at"

    top_level = client.get(url, {"date_filter": "last_30_days", "count_mode": "top_level"})
    assert top_level.status_code == 200, top_level.data
    assert top_level.data["totals"]["total"] == 1
    assert top_level.data["totals"]["subtasks"] == 0
    assert top_level.data["totals"]["total_bugs"] == 0

    high_priority = client.get(url, {"date_filter": "last_30_days", "priorities": "high"})
    assert high_priority.status_code == 200, high_priority.data
    assert high_priority.data["totals"]["total"] == 1
    assert high_priority.data["priorities"] == [{"priority": "high", "count": 1}]


@pytest.mark.contract
@pytest.mark.django_db
def test_workspace_report_excludes_soft_deleted_project_membership(workspace, create_user):
    project = Project.objects.create(name="Removed", identifier="REM", workspace=workspace)
    membership = ProjectMember.objects.create(
        project=project, member=create_user, workspace=workspace, role=20, is_active=True
    )
    state = State.objects.create(name="Todo", project=project, workspace=workspace, group="unstarted", default=True)
    Issue.objects.create(name="Must stay hidden", project=project, workspace=workspace, state=state)
    membership.deleted_at = timezone.now()
    membership.save(update_fields=["deleted_at"])

    client = APIClient()
    client.force_authenticate(user=create_user)
    response = client.get(f"/api/workspaces/{workspace.slug}/analytics-report/")

    assert response.status_code == 200, response.data
    assert response.data["totals"]["total"] == 0
    assert response.data["projects"] == []


@pytest.mark.contract
@pytest.mark.django_db
@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"count_mode": "nested_only"}, "Invalid count_mode"),
        ({"date_filter": "forever"}, "Invalid date_filter"),
        ({"date_from": "2026-02-01"}, "Invalid date range"),
        ({"date_from": "2026-02-02", "date_to": "2026-02-01"}, "Invalid date range"),
        ({"priorities": "critical"}, "Invalid priorities"),
    ],
)
def test_workspace_report_rejects_invalid_filters(session_client, workspace, params, message):
    response = session_client.get(f"/api/workspaces/{workspace.slug}/analytics-report/", params)

    assert response.status_code == 400
    assert response.data["message"] == message
