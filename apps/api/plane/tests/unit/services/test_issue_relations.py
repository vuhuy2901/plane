import pytest
from rest_framework.exceptions import ValidationError

from plane.db.models import Issue, IssueRelation, State
from plane.app.serializers.issue import IssueCreateSerializer
from plane.services.issue_relations import validate_relation_candidates
from plane.tests.unit.services.test_automation_runtime import runtime as runtime_fixture

pytestmark = [pytest.mark.unit, pytest.mark.django_db]
runtime = runtime_fixture


def relation(project, blocked, blocker):
    return IssueRelation(
        project=project,
        workspace=project.workspace,
        issue=blocked,
        related_issue=blocker,
        relation_type="blocked_by",
    )


def test_rejects_self_dependency(runtime):
    project, _, issue = runtime
    with pytest.raises(ValidationError, match="itself"):
        validate_relation_candidates([relation(project, issue, issue)])


def test_rejects_duplicate_but_allows_idempotent_automation_retry(runtime):
    project, _, blocked = runtime
    blocker = Issue.objects.create(project=project, name="Blocker", state=blocked.state)
    IssueRelation.objects.create(
        project=project,
        workspace=project.workspace,
        issue=blocked,
        related_issue=blocker,
        relation_type="blocked_by",
    )

    with pytest.raises(ValidationError, match="already exists"):
        validate_relation_candidates([relation(project, blocked, blocker)])
    assert validate_relation_candidates([relation(project, blocked, blocker)], allow_existing=True) == []


def test_rejects_indirect_blocking_cycle(runtime):
    project, _, first = runtime
    second = Issue.objects.create(project=project, name="Second", state=first.state)
    third = Issue.objects.create(project=project, name="Third", state=first.state)
    # first blocks second; second blocks third.
    IssueRelation.objects.create(
        project=project,
        workspace=project.workspace,
        issue=second,
        related_issue=first,
        relation_type="blocked_by",
    )
    IssueRelation.objects.create(
        project=project,
        workspace=project.workspace,
        issue=third,
        related_issue=second,
        relation_type="blocked_by",
    )

    # third blocking first would close the cycle.
    with pytest.raises(ValidationError, match="circular"):
        validate_relation_candidates([relation(project, first, third)])


def test_completion_guard_is_opt_in_and_uses_active_blockers(runtime):
    project, actor, blocked = runtime
    blocker = Issue.objects.create(project=project, name="Blocker", state=blocked.state)
    IssueRelation.objects.create(
        project=project,
        workspace=project.workspace,
        issue=blocked,
        related_issue=blocker,
        relation_type="blocked_by",
    )
    completed = State.objects.create(project=project, name="Done", group="completed", color="#123456")
    project.prevent_blocked_issue_completion = True
    project.save(update_fields=["prevent_blocked_issue_completion"])
    serializer = IssueCreateSerializer(
        blocked,
        data={"state_id": str(completed.id)},
        partial=True,
        context={
            "project_id": str(project.id),
            "workspace_id": str(project.workspace_id),
            "actor": actor,
        },
    )
    serializer.is_valid(raise_exception=True)

    with pytest.raises(ValidationError, match="active blocking"):
        serializer.save()
