"""Validation helpers for canonical Work Item relations.

Blocking relations are stored as ``blocked issue -> blocker`` with the
``blocked_by`` relation type.  This module keeps that convention in one place
and validates the logical ``blocker -> blocked`` graph before writes.
"""

from collections import defaultdict, deque

from django.db.models import Q
from rest_framework.exceptions import ValidationError

from plane.db.models import IssueRelation


def validate_relation_candidates(relations, *, allow_existing=False):
    """Validate relation rows before inserting them.

    Returns only rows that still need inserting when ``allow_existing`` is
    enabled.  Automation uses that mode so retries are idempotent; interactive
    API calls reject duplicates with an actionable error.
    """

    candidates = list(relations)
    if not candidates:
        return []

    workspace_ids = {relation.workspace_id for relation in candidates}
    if len(workspace_ids) != 1:
        raise ValidationError("All related Work Items must belong to one workspace.")

    requested_pairs = set()
    for relation in candidates:
        if relation.issue_id == relation.related_issue_id:
            raise ValidationError("A Work Item cannot have a relation with itself.")
        pair = frozenset((relation.issue_id, relation.related_issue_id))
        if pair in requested_pairs:
            raise ValidationError("The same Work Item relation was selected more than once.")
        requested_pairs.add(pair)

    ids = {relation.issue_id for relation in candidates} | {
        relation.related_issue_id for relation in candidates
    }
    existing = list(
        IssueRelation.objects.filter(workspace_id=next(iter(workspace_ids))).filter(
            Q(issue_id__in=ids, related_issue_id__in=ids)
        )
    )
    existing_by_pair = {
        frozenset((relation.issue_id, relation.related_issue_id)): relation for relation in existing
    }

    pending = []
    for relation in candidates:
        current = existing_by_pair.get(frozenset((relation.issue_id, relation.related_issue_id)))
        if current is None:
            pending.append(relation)
            continue
        same = (
            current.issue_id == relation.issue_id
            and current.related_issue_id == relation.related_issue_id
            and current.relation_type == relation.relation_type
        )
        if allow_existing and same:
            continue
        if same:
            raise ValidationError("This Work Item relation already exists.")
        raise ValidationError("A different relation already exists between these Work Items.")

    blocking = [relation for relation in pending if relation.relation_type == "blocked_by"]
    if blocking:
        _validate_blocking_cycles(next(iter(workspace_ids)), blocking)
    return pending


def _validate_blocking_cycles(workspace_id, candidates):
    """Reject additions that would introduce a cycle in the blocking graph."""

    adjacency = defaultdict(set)
    for blocked_id, blocker_id in IssueRelation.objects.filter(
        workspace_id=workspace_id, relation_type="blocked_by"
    ).values_list("issue_id", "related_issue_id"):
        adjacency[blocker_id].add(blocked_id)

    for relation in candidates:
        blocker_id = relation.related_issue_id
        blocked_id = relation.issue_id
        if _has_path(adjacency, blocked_id, blocker_id):
            raise ValidationError(
                "This blocking dependency would create a circular dependency."
            )
        adjacency[blocker_id].add(blocked_id)


def _has_path(adjacency, start, target):
    queue = deque([start])
    visited = set()
    while queue:
        current = queue.popleft()
        if current == target:
            return True
        if current in visited:
            continue
        visited.add(current)
        queue.extend(adjacency.get(current, ()))
    return False
