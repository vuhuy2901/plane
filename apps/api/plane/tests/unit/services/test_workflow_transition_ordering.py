"""Canvas coordinates are optional; missing layouts must not stop execution."""

import pytest

from plane.db.models import (
    State,
    Workflow,
    WorkflowVersion,
    WorkflowVersionState,
    WorkflowTransition,
    WorkflowStateLayout,
)
from plane.services.workflow import order_workflow_transitions
from plane.tests.factories import ProjectFactory


@pytest.mark.unit
@pytest.mark.django_db
@pytest.mark.parametrize("with_layout", [False, True])
def test_cyclic_workflow_orders_transitions_with_optional_canvas_layout(with_layout):
    project = ProjectFactory()
    workflow = Workflow.objects.create(project=project, name="Review loop")
    version = WorkflowVersion.objects.create(project=project, workflow=workflow, version=1)
    a, b = [
        WorkflowVersionState.objects.create(
            project=project,
            workflow_version=version,
            state=State.objects.create(project=project, name=name, group="started", color="#123456"),
            name=name,
            group="started",
        )
        for name in ("Testing", "Progress")
    ]
    forward = WorkflowTransition.objects.create(
        project=project, workflow_version=version, source=a, target=b, name="Reject"
    )
    WorkflowTransition.objects.create(project=project, workflow_version=version, source=b, target=a, name="Retest")
    if with_layout:
        WorkflowStateLayout.objects.create(project=project, workflow_state=a, position_x=100)
        WorkflowStateLayout.objects.create(project=project, workflow_state=b, position_x=-100)
    a = WorkflowVersionState.objects.get(pk=a.pk)
    outgoing = list(a.outgoing_transitions.select_related("target"))
    ordered = order_workflow_transitions(version, a, outgoing)
    assert [transition.id for transition in ordered] == [forward.id]
    if with_layout:
        assert ordered[0].direction == "backward"
