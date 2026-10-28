"""Transactional adapters for comments and real Work Item relations."""

from django.db import transaction
from django.db.models import Q

from plane.db.models import Issue, IssueRelation, ProjectAutomationEvent
from plane.services.automation_runtime import capture_context, schedule_event_delivery, snapshot


def comment_created(comment):
    context = capture_context(comment.project_id)
    if not context or comment.issue.project_id != comment.project_id:
        return
    event, created = ProjectAutomationEvent.objects.get_or_create(
        deduplication_key=f"comment:{comment.id}",
        defaults={
            "project": comment.project,
            "issue": comment.issue,
            "snapshot": snapshot(comment.issue),
            "triggers": ["comment_added"],
            "candidates": context["candidates"],
            "context": {
                "comment_id": str(comment.id),
                "author_id": str(comment.actor_id),
                "actor_id": str(comment.actor_id),
            },
        },
    )
    if created:
        schedule_event_delivery(event)


@transaction.atomic
def bulk_create_relations(relations, **kwargs):
    """Record only newly persisted rows, including when bulk insert ignores conflicts."""
    if not relations:
        return []
    ids = {item.issue_id for item in relations} | {item.related_issue_id for item in relations}
    list(Issue.objects.select_for_update().filter(pk__in=ids).order_by("id"))
    from plane.services.issue_relations import validate_relation_candidates

    relations = validate_relation_candidates(
        relations,
        allow_existing=bool(kwargs.get("ignore_conflicts")),
    )
    if not relations:
        return []
    query = IssueRelation.objects.filter(Q(issue_id__in=ids), related_issue_id__in=ids)
    existing = set(query.values_list("id", flat=True))
    result = IssueRelation.objects.bulk_create(relations, **kwargs)
    for relation in query.exclude(pk__in=existing).select_related("issue__project", "related_issue__project"):
        relation_created(relation)
    return result


def relation_created(relation):
    from plane.db.models.issue import IssueRelationChoices

    # Keep stored direction in history; expose a canonical source -> target view.
    source, target = relation.issue, relation.related_issue
    kind = relation.relation_type
    aliases = [kind]
    reverse = dict(IssueRelationChoices._RELATION_PAIRS).get(kind)
    if reverse and reverse != kind:
        aliases.append(reverse)
    if kind == "blocked_by":
        source, target = target, source
    context = capture_context(target.project_id)
    if not context:
        return
    metadata = {
        "relation_id": str(relation.id),
        "relation_types": aliases,
        "source_id": str(source.id),
        "target_id": str(target.id),
        "stored_issue_id": str(relation.issue_id),
        "stored_related_issue_id": str(relation.related_issue_id),
        "stored_relation_type": kind,
        "actor_id": str(relation.created_by_id) if relation.created_by_id else None,
    }
    foreign = source.project_id != target.project_id
    if foreign:
        metadata["skip_reason"] = "Cross-project relationships are not supported by Automation."
    event, created = ProjectAutomationEvent.objects.get_or_create(
        deduplication_key=f"relation:{relation.id}",
        defaults={
            "project": target.project,
            "issue": target,
            "snapshot": snapshot(target),
            "triggers": ["work_item_linked"],
            "candidates": context["candidates"],
            "context": metadata,
        },
    )
    if created:
        schedule_event_delivery(event)
