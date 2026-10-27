from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections, transaction

from plane.db.models import Workflow, WorkflowTransition, WorkflowVersion
from plane.services.workflow_graph import DraftConflict, save_workflow_graph
from plane.tests.factories import ProjectFactory, UserFactory


@pytest.mark.unit
@pytest.mark.django_db(transaction=True)
def test_concurrent_draft_saves_only_accept_one_revision():
    actor = UserFactory()
    project = ProjectFactory(workspace__owner=actor)
    workflow = Workflow.objects.create(project=project, name="Race-safe draft")
    draft = WorkflowVersion.objects.create(project=project, workflow=workflow, version=1)
    a, b = str(uuid4()), str(uuid4())
    barrier = Barrier(2)

    def save(reverse):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            with transaction.atomic():
                locked = WorkflowVersion.objects.select_for_update().get(pk=draft.id)
                save_workflow_graph(
                    locked,
                    {
                        "draft_id": str(draft.id),
                        "expected_revision": 0,
                        "states": [{"key": a, "name": "A"}, {"key": b, "name": "B"}],
                        "transitions": [
                            {"id": str(uuid4()), "source_key": b if reverse else a, "target_key": a if reverse else b}
                        ],
                    },
                    actor,
                )
            return "saved"
        except DraftConflict:
            return "conflict"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(save, [False, True]))
    assert sorted(outcomes) == ["conflict", "saved"]
    draft.refresh_from_db()
    assert draft.revision == 1
    assert WorkflowTransition.objects.filter(workflow_version=draft).count() == 1
