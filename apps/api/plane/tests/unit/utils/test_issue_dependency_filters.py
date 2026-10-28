import pytest

from plane.db.models import Issue, IssueRelation, State
from plane.tests.unit.services.test_automation_runtime import runtime as runtime_fixture
from plane.utils.filters.filterset import IssueFilterSet

pytestmark = [pytest.mark.unit, pytest.mark.django_db]
runtime = runtime_fixture


def filtered(data, project):
    return set(
        IssueFilterSet(data=data, queryset=Issue.objects.filter(project=project)).qs.values_list("id", flat=True)
    )


def test_blocked_not_blocked_and_blocking_filters_follow_blocker_completion(runtime):
    project, _, blocked = runtime
    blocker = Issue.objects.create(project=project, name="Blocker", state=blocked.state)
    unrelated = Issue.objects.create(project=project, name="Unrelated", state=blocked.state)
    IssueRelation.objects.create(
        project=project,
        workspace=project.workspace,
        issue=blocked,
        related_issue=blocker,
        relation_type="blocked_by",
    )

    assert filtered({"is_blocked__exact": True}, project) == {blocked.id}
    assert blocked.id not in filtered({"is_blocked__exact": False}, project)
    assert filtered({"is_blocking__exact": True}, project) == {blocker.id}

    completed = State.objects.create(project=project, name="Done", group="completed", color="#123456")
    blocker.state = completed
    blocker.save()
    assert filtered({"is_blocked__exact": True}, project) == set()
    assert {blocked.id, blocker.id, unrelated.id}.issubset(filtered({"is_blocked__exact": False}, project))
