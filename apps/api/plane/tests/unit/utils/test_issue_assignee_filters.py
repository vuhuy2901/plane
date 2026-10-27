# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

import pytest
from django.utils import timezone

from plane.db.models import Issue, IssueAssignee, Project, ProjectMember, User
from plane.utils.filters.filterset import IssueFilterSet


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(
        name="Assignee Filter Project",
        identifier="AFP",
        workspace=workspace,
        created_by=create_user,
    )
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    return project


@pytest.fixture
def assignee_users(db, create_user):
    other = User.objects.create(
        username="assignee-other",
        email="assignee.other@plane.so",
        first_name="Other",
        last_name="User",
    )
    third = User.objects.create(
        username="assignee-third",
        email="assignee.third@plane.so",
        first_name="Third",
        last_name="User",
    )
    return create_user, other, third


def _issue(project, created_by, name, priority="medium"):
    return Issue.objects.create(
        name=name,
        priority=priority,
        project=project,
        workspace=project.workspace,
        created_by=created_by,
    )


def _filter(project, data):
    queryset = Issue.objects.filter(project=project)
    filterset = IssueFilterSet(data=data, queryset=queryset)
    assert filterset.is_valid(), filterset.errors
    return filterset.qs


@pytest.fixture
def assignee_issues(project, assignee_users):
    first, second, third = assignee_users
    first_issue = _issue(project, first, "First assignee", priority="high")
    second_issue = _issue(project, first, "Second assignee")
    both_issue = _issue(project, first, "Multiple assignees", priority="high")
    unassigned_issue = _issue(project, first, "Unassigned")
    deleted_assignment_issue = _issue(project, first, "Deleted assignment")

    IssueAssignee.objects.create(project=project, issue=first_issue, assignee=first)
    IssueAssignee.objects.create(project=project, issue=second_issue, assignee=second)
    IssueAssignee.objects.create(project=project, issue=both_issue, assignee=first)
    IssueAssignee.objects.create(project=project, issue=both_issue, assignee=second)
    IssueAssignee.objects.create(
        project=project,
        issue=deleted_assignment_issue,
        assignee=third,
        deleted_at=timezone.now(),
    )

    return {
        "first": first_issue,
        "second": second_issue,
        "both": both_issue,
        "unassigned": unassigned_issue,
        "deleted": deleted_assignment_issue,
    }


@pytest.mark.unit
class TestIssueAssigneeFilter:
    def test_omitted_filter_returns_all_issues(self, project, assignee_issues):
        assert _filter(project, {}).count() == 5

    def test_all_assignees_returns_all_issues(self, project, assignee_issues):
        assert _filter(project, {"assignee_id__in": "__all_assignees__"}).count() == 5

    def test_multiple_assignees_use_or_semantics(self, project, assignee_users, assignee_issues):
        first, second, _ = assignee_users
        queryset = _filter(project, {"assignee_id__in": f"{first.id},{second.id}"})

        assert set(queryset.values_list("name", flat=True)) == {
            "First assignee",
            "Second assignee",
            "Multiple assignees",
        }
        assert queryset.count() == 3

    def test_unassigned_includes_only_issues_without_active_assignee(self, project, assignee_issues):
        assert set(_filter(project, {"assignee_id__in": "__unassigned__"}).values_list("name", flat=True)) == {
            "Unassigned",
            "Deleted assignment",
        }

    def test_assignee_and_unassigned_are_or_combined(self, project, assignee_users, assignee_issues):
        first, _, _ = assignee_users
        assert set(
            _filter(project, {"assignee_id__in": f"{first.id},__unassigned__"}).values_list("name", flat=True)
        ) == {"First assignee", "Multiple assignees", "Unassigned", "Deleted assignment"}

    def test_assignee_filter_combines_with_other_filters_using_and(self, project, assignee_users, assignee_issues):
        first, second, _ = assignee_users
        queryset = _filter(
            project,
            {"assignee_id__in": f"{first.id},{second.id}", "priority": "high"},
        )

        assert set(queryset.values_list("name", flat=True)) == {"First assignee", "Multiple assignees"}

    def test_empty_collection_does_not_mean_omitted_filter(self, project, assignee_issues):
        assert _filter(project, {"assignee_id__in": ""}).count() == 0
