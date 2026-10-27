from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import close_old_connections

from plane.db.models import (
    Issue,
    IssueType,
    Project,
    ProjectIssueType,
    State,
    Workflow,
    WorkflowIssueTypeMapping,
    WorkflowTransition,
    WorkflowTransitionAudit,
    WorkflowVersion,
    WorkflowVersionState,
)
from plane.services.workflow import (
    WorkflowRuleError,
    get_available_transitions,
    publish_workflow,
    transition_issue,
    validate_workflow_version,
)
from plane.tests.factories import ProjectFactory, ProjectMemberFactory, UserFactory, WorkspaceMemberFactory


def _configured_workflow(project, *, actor, required_role=None):
    issue_type = IssueType.objects.create(workspace=project.workspace, name=f"Task-{uuid4()}")
    ProjectIssueType.objects.create(project=project, issue_type=issue_type, is_default=True)
    todo = State.objects.create(project=project, name="Ready", color="#60646C", group="unstarted")
    done = State.objects.create(project=project, name="Released", color="#46A758", group="completed")
    blocked = State.objects.create(project=project, name="Blocked", color="#9AA4BC", group="cancelled")
    workflow = Workflow.objects.create(project=project, name=f"Delivery-{uuid4()}")
    version = WorkflowVersion.objects.create(
        project=project,
        workflow=workflow,
        version=1,
        status=WorkflowVersion.Status.PUBLISHED,
    )
    start = WorkflowVersionState.objects.create(
        project=project,
        workflow_version=version,
        state=todo,
        name=todo.name,
        color=todo.color,
        group=todo.group,
        is_start=True,
    )
    end = WorkflowVersionState.objects.create(
        project=project,
        workflow_version=version,
        state=done,
        name=done.name,
        color=done.color,
        group=done.group,
        is_end=True,
    )
    transition = WorkflowTransition.objects.create(
        project=project,
        workflow_version=version,
        source=start,
        target=end,
        name="Release",
        permissions={"roles": [required_role]} if required_role else {},
    )
    workflow.active_version = version
    workflow.save(update_fields=["active_version"])
    WorkflowIssueTypeMapping.objects.create(project=project, issue_type=issue_type, workflow=workflow)
    issue = Issue.objects.create(project=project, name="Ship it", state=todo, type=issue_type)
    ProjectMemberFactory(project=project, member=actor, role=20)
    WorkspaceMemberFactory(workspace=project.workspace, member=actor, role=20)
    return issue, transition, done, blocked


@pytest.mark.unit
@pytest.mark.django_db
class TestWorkflowEngine:
    def test_only_a_declared_transition_is_available_and_audited(self):
        actor = UserFactory()
        project = ProjectFactory(workspace__owner=actor)
        issue, transition, done, blocked = _configured_workflow(project, actor=actor)

        assert [item.id for item in get_available_transitions(issue, actor)] == [transition.id]
        transitioned, used_transition = transition_issue(
            issue_id=issue.id,
            project_id=project.id,
            target_state_id=done.id,
            actor=actor,
        )

        assert transitioned.state_id == done.id
        assert used_transition.id == transition.id
        audit = WorkflowTransitionAudit.objects.get(issue=issue)
        assert (audit.source_state_id, audit.target_state_id, audit.actor_id) == (
            issue.state_id,
            done.id,
            actor.id,
        )

        # Reset directly only to exercise the negative engine path in this unit test.
        Issue.objects.filter(pk=issue.id).update(state_id=issue.state_id)
        with pytest.raises(WorkflowRuleError) as exc:
            transition_issue(
                issue_id=issue.id,
                project_id=project.id,
                target_state_id=blocked.id,
                actor=actor,
            )
        assert exc.value.code == "WORKFLOW_TRANSITION_NOT_ALLOWED"

    def test_transition_permission_uses_project_role(self):
        actor = UserFactory()
        project = ProjectFactory(workspace__owner=actor)
        issue, _, done, _ = _configured_workflow(project, actor=actor, required_role=15)

        with pytest.raises(WorkflowRuleError) as exc:
            transition_issue(
                issue_id=issue.id,
                project_id=project.id,
                target_state_id=done.id,
                actor=actor,
            )
        assert exc.value.code == "WORKFLOW_PERMISSION_DENIED"

    def test_workflow_mapping_never_leaks_between_projects(self):
        actor = UserFactory()
        project_a = ProjectFactory(workspace__owner=actor)
        issue, _, _, _ = _configured_workflow(project_a, actor=actor)
        project_b = Project.objects.create(
            workspace=project_a.workspace,
            name=f"Isolated-{uuid4()}",
            identifier=f"I{uuid4().hex[:5]}",
        )
        foreign_issue = Issue.objects.create(project=project_b, name="Legacy", state=None, type=issue.type)

        assert foreign_issue.project_id != issue.project_id
        assert get_available_transitions(foreign_issue, actor) is None

    def test_validation_rejects_multiple_start_states_and_unreachable_end(self):
        project = ProjectFactory()
        workflow = Workflow.objects.create(project=project, name="Invalid")
        draft = WorkflowVersion.objects.create(project=project, workflow=workflow, version=1)
        WorkflowVersionState.objects.create(
            project=project,
            workflow_version=draft,
            name="Start A",
            color="#000000",
            group="unstarted",
            is_start=True,
        )
        # The database constraint protects the common race; temporarily making the
        # first state non-start lets graph validation exercise the zero-start case.
        draft.states.update(is_start=False)
        WorkflowVersionState.objects.create(
            project=project,
            workflow_version=draft,
            name="End",
            color="#ffffff",
            group="completed",
            is_end=True,
        )

        result = validate_workflow_version(draft)
        assert result["valid"] is False
        assert {error["code"] for error in result["errors"]} == {"START_STATE_COUNT"}

    def test_publish_does_not_create_a_template_and_materializes_only_user_nodes(self):
        actor = UserFactory()
        project = ProjectFactory(workspace__owner=actor)
        workflow = Workflow.objects.create(project=project, name="User designed")
        draft = WorkflowVersion.objects.create(project=project, workflow=workflow, version=1)
        start = WorkflowVersionState.objects.create(
            project=project,
            workflow_version=draft,
            name="Inbox zero",
            color="#123456",
            group="backlog",
            is_start=True,
            is_end=True,
        )

        published, _ = publish_workflow(draft, actor)

        start.refresh_from_db()
        assert published.status == WorkflowVersion.Status.PUBLISHED
        assert list(State.objects.filter(project=project).values_list("name", flat=True)) == ["Inbox zero"]
        assert start.state_id is not None


@pytest.mark.unit
@pytest.mark.django_db(transaction=True)
def test_concurrent_transitions_serialize_on_the_work_item_row():
    actor = UserFactory()
    project = ProjectFactory(workspace__owner=actor)
    issue, first_transition, done, blocked = _configured_workflow(project, actor=actor)
    blocked_node = WorkflowVersionState.objects.create(
        project=project,
        workflow_version=first_transition.workflow_version,
        state=blocked,
        name=blocked.name,
        color=blocked.color,
        group=blocked.group,
        is_end=True,
    )
    WorkflowTransition.objects.create(
        project=project,
        workflow_version=first_transition.workflow_version,
        source=first_transition.source,
        target=blocked_node,
        name="Cancel",
    )

    def run(target_state_id):
        close_old_connections()
        try:
            transition_issue(
                issue_id=issue.id,
                project_id=project.id,
                target_state_id=target_state_id,
                actor=actor,
            )
            return "ok"
        except WorkflowRuleError as exc:
            return exc.code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, [done.id, blocked.id]))

    assert sorted(results) == ["WORKFLOW_TRANSITION_NOT_ALLOWED", "ok"]
    issue.refresh_from_db()
    assert issue.state_id in {done.id, blocked.id}
