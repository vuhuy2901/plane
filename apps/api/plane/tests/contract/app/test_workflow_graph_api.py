from copy import deepcopy
from uuid import uuid4

import pytest

from plane.db.models import (
    Cycle,
    CycleIssue,
    Issue,
    IssueAssignee,
    IssueType,
    ProjectIssueType,
    State,
    Workflow,
    WorkflowStateLayout,
    WorkflowTransition,
    WorkflowVersion,
    WorkflowVersionState,
)
from plane.tests.factories import ProjectFactory, ProjectMemberFactory


@pytest.fixture
def graph_api(session_client, workspace, create_user):
    project = ProjectFactory(workspace=workspace, identifier="GR")
    ProjectMemberFactory(project=project, member=create_user, role=20)
    base = f"/api/workspaces/{workspace.slug}/projects/{project.id}/workflows/"
    created = session_client.post(base, {"name": "Directed graph"}, format="json")
    assert created.status_code == 201, created.data
    url = f"{base}{created.data['id']}/draft/"
    draft = session_client.get(url).json()
    keys = [str(uuid4()), str(uuid4())]
    payload = {
        "draft_id": draft["id"],
        "expected_revision": draft["revision"],
        "states": [
            {
                "key": key,
                "name": name,
                "group": "started",
                "is_start": index == 0,
                "layout": {"position_x": 600 if index == 0 else -120, "position_y": index * 250},
            }
            for index, (key, name) in enumerate(zip(keys, ["In Progress", "Ready for Acceptance"]))
        ],
        "transitions": [
            {
                "id": str(uuid4()),
                "source_key": keys[0],
                "target_key": keys[1],
                "name": "Accept",
                "source_handle": "out-left",
                "target_handle": "in-right",
            }
        ],
    }
    return session_client, project, url, payload


def put(client, url, payload):
    response = client.put(url, payload, format="json")
    assert response.status_code == 200, response.data
    return response.json()


def next_payload(saved):
    return deepcopy(
        {
            "draft_id": saved["id"],
            "expected_revision": saved["revision"],
            "states": saved["states"],
            "transitions": saved["transitions"],
        }
    )


@pytest.mark.contract
@pytest.mark.django_db
class TestDirectedGraphAPI:
    @pytest.mark.parametrize("reverse", [False, True])
    def test_direction_identity_positions_survive_save_reload_and_move(self, graph_api, reverse):
        client, _, url, payload = graph_api
        if reverse:
            edge = payload["transitions"][0]
            edge["source_key"], edge["target_key"] = edge["target_key"], edge["source_key"]
        first = put(client, url, payload)
        assert client.get(url).json() == first
        edge = first["transitions"][0]
        assert edge["id"] == payload["transitions"][0]["id"]
        for name in ["source_key", "target_key", "source_handle", "target_handle"]:
            assert edge[name] == payload["transitions"][0][name]
        moved = next_payload(first)
        moved["states"].reverse()  # Array order must not determine direction or identity.
        for node in moved["states"]:
            node["layout"] = {"position_x": -node["layout"]["position_x"], "position_y": -333.5}
        second = put(client, url, moved)
        assert second["transitions"] == first["transitions"]
        assert {node["key"]: node["id"] for node in first["states"]} == {
            node["key"]: node["id"] for node in second["states"]
        }
        assert {node["key"]: node["layout"] for node in second["states"]} == {
            node["key"]: node["layout"] for node in moved["states"]
        }
        assert WorkflowTransition.objects.count() == 1
        assert WorkflowVersionState.objects.count() == WorkflowStateLayout.objects.count() == 2

    def test_reciprocal_edges_are_independent_and_deleting_one_keeps_nodes(self, graph_api):
        client, _, url, payload = graph_api
        a, b = [node["key"] for node in payload["states"]]
        payload["transitions"].append({"id": str(uuid4()), "source_key": b, "target_key": a, "name": "Request changes"})
        saved = put(client, url, payload)
        assert len(saved["transitions"]) == 2
        assert {edge["id"] for edge in saved["transitions"]} == {edge["id"] for edge in payload["transitions"]}
        reduced = next_payload(saved)
        deleted = reduced["transitions"].pop(0)
        kept = put(client, url, reduced)
        assert len(kept["states"]) == 2
        assert kept["transitions"] == reduced["transitions"]
        restored = next_payload(kept)
        restored["transitions"].append(deleted)
        undone = put(client, url, restored)
        assert {edge["id"] for edge in undone["transitions"]} == {edge["id"] for edge in saved["transitions"]}

    def test_duplicate_direction_is_rejected_atomically_even_with_other_ports(self, graph_api):
        client, _, url, payload = graph_api
        initial = client.get(url).json()
        duplicate = {**payload["transitions"][0], "id": str(uuid4()), "source_handle": "out-top"}
        payload["transitions"].append(duplicate)
        response = client.put(url, payload, format="json")
        assert response.status_code == 400
        assert client.get(url).json() == initial

    def test_stale_and_wrong_draft_saves_cannot_overwrite_newer_edges(self, graph_api):
        client, _, url, payload = graph_api
        saved = put(client, url, payload)
        payload["transitions"] = []
        stale = client.put(url, payload, format="json")
        assert stale.status_code == 409
        assert client.get(url).json() == saved
        wrong = next_payload(saved)
        wrong["draft_id"] = str(uuid4())
        assert client.put(url, wrong, format="json").status_code == 409
        assert client.get(url).json() == saved

    def test_rapid_sequential_saves_keep_edge_ids_and_latest_draft(self, graph_api):
        client, _, url, payload = graph_api
        saved = put(client, url, payload)
        for index in range(6):
            current = next_payload(saved)
            current["transitions"][0]["name"] = f"Accept {index}"
            saved = put(client, url, current)
        assert saved["revision"] == 7
        assert saved["transitions"][0]["id"] == payload["transitions"][0]["id"]
        assert client.get(url).json()["transitions"][0]["name"] == "Accept 5"

    def test_transition_id_cannot_be_stolen_from_another_draft(self, graph_api):
        client, project, url, payload = graph_api
        saved = put(client, url, payload)
        other_workflow = Workflow.objects.create(project=project, name="Other")
        other = WorkflowVersion.objects.create(project=project, workflow=other_workflow, version=1)
        node = WorkflowVersionState.objects.create(project=project, workflow_version=other, name="Other")
        foreign = WorkflowTransition.objects.create(
            project=project, workflow_version=other, source=node, target=node, name="Other"
        )
        invalid = next_payload(saved)
        invalid["transitions"][0]["id"] = str(foreign.id)
        invalid["states"][0]["layout"]["position_x"] = 12345
        assert client.put(url, invalid, format="json").status_code == 400
        assert client.get(url).json() == saved  # Node updates also roll back.

    def test_swapping_start_and_restoring_deleted_node_preserves_identity(self, graph_api):
        client, _, url, payload = graph_api
        first = put(client, url, payload)
        changed = next_payload(first)
        for node in changed["states"]:
            node["is_start"] = not node["is_start"]
        second = put(client, url, changed)
        removed = next_payload(second)
        removed["states"].pop(0)
        removed["transitions"] = []
        third = put(client, url, removed)
        restored = next_payload(second)
        restored["expected_revision"] = third["revision"]
        fourth = put(client, url, restored)
        assert fourth["states"] == second["states"]

    def test_legacy_payload_keeps_direction_ports_layout_and_edge_identity(self, graph_api):
        client, _, url, payload = graph_api
        payload.pop("draft_id")
        payload.pop("expected_revision")
        edge = payload["transitions"][0]
        edge.pop("id")
        edge["permissions"] = {"source_handle": "left-1", "target_handle": "top-3"}
        edge.pop("source_handle")
        edge.pop("target_handle")
        saved = put(client, url, payload)
        again = put(client, url, payload)
        assert again["states"] == saved["states"]
        assert again["transitions"] == saved["transitions"]
        assert again["transitions"][0]["permissions"] == edge["permissions"]

    def test_graph_edit_does_not_mutate_any_work_item_or_cycle(self, graph_api, workspace, create_user):
        client, project, url, payload = graph_api
        state = State.objects.create(project=project, name="Live", color="#123456", group="started")
        parent = None
        cycle = Cycle.objects.create(project=project, name="Sprint", owned_by=create_user)
        for index, name in enumerate(["Epic", "Task", "Bug", "Subtask"]):
            kind = IssueType.objects.create(workspace=workspace, name=name)
            ProjectIssueType.objects.create(project=project, issue_type=kind, level=min(index, 2))
            item = Issue.objects.create(
                project=project,
                name=name,
                type=kind,
                parent=parent,
                state=state,
                start_date="2027-01-04",
                target_date="2027-02-10",
                priority="high",
            )
            IssueAssignee.objects.create(project=project, issue=item, assignee=create_user)
            CycleIssue.objects.create(project=project, cycle=cycle, issue=item)
            if index < 2:
                parent = item
        before = list(Issue.objects.order_by("id").values())
        cycles = list(CycleIssue.objects.order_by("id").values())
        assignees = list(IssueAssignee.objects.order_by("id").values())
        saved = put(client, url, payload)
        current = next_payload(saved)
        current["transitions"] = []
        put(client, url, current)
        assert list(Issue.objects.order_by("id").values()) == before
        assert list(CycleIssue.objects.order_by("id").values()) == cycles
        assert list(IssueAssignee.objects.order_by("id").values()) == assignees

    def test_stale_publish_is_rejected(self, graph_api):
        client, _, url, payload = graph_api
        put(client, url, payload)
        response = client.post(
            url.replace("draft/", "publish/"), {"draft_id": payload["draft_id"], "expected_revision": 0}, format="json"
        )
        assert response.status_code == 409
