"""Fail-closed direct Subtask → Task evaluation; never traverses ancestors."""

from django.db import transaction
from plane.db.models import Issue, ProjectIssueType


class FamilySkipped(Exception):
    pass


def type_name(issue):
    return issue.type.name.strip().lower().replace("-", "").replace(" ", "") if issue.type_id else ""


def lock_family_write(issue=None, parent_id=None):
    """Serializer writes and automation use parent-first locking to avoid sibling races."""
    from plane.services.automation_runtime import automation_origin

    if automation_origin.get():
        return  # Worker already owns its relevant parent lock; never lock an Epic ancestor.
    ids = {str(value) for value in (getattr(issue, "parent_id", None), parent_id) if value}
    if ids:
        list(Issue.all_objects.select_for_update().filter(pk__in=ids).order_by("id"))


def completed_parent(issue, event):
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Family evaluation requires a transaction.")
    parent_id = event.snapshot.get("parent_id")
    if not parent_id or str(issue.parent_id) != parent_id or type_name(issue) != "subtask":
        raise FamilySkipped("Missing/changed parent or source is not a Subtask.")
    parent = (
        Issue.objects.select_for_update(of=("self",))
        .select_related("type", "state", "project")
        .filter(pk=parent_id)
        .first()
    )
    if not parent or parent.project_id != issue.project_id or parent.id == issue.id:
        raise FamilySkipped("Parent is missing, invalid or belongs to another project.")
    if (
        type_name(parent) != "task"
        or not parent.type.is_active
        or parent.archived_at
        or not ProjectIssueType.objects.filter(project_id=parent.project_id, issue_type_id=parent.type_id).exists()
    ):
        raise FamilySkipped("Only an active Task parent is supported; Epic/Bug are excluded.")
    # No project filter or pagination: foreign-project children and incomplete data must fail closed.
    children = list(
        Issue.all_objects.filter(parent_id=parent.id, deleted_at__isnull=True).select_related("state", "type")
    )
    if not children:
        raise FamilySkipped("Parent has no direct Subtasks.")
    configured = set(
        ProjectIssueType.objects.filter(project_id=parent.project_id).values_list("issue_type_id", flat=True)
    )
    if any(
        child.project_id != parent.project_id
        or type_name(child) != "subtask"
        or not child.type.is_active
        or child.type_id not in configured
        or child.archived_at
        or not child.state_id
        or child.state.deleted_at
        or child.state.project_id != parent.project_id
        for child in children
    ):
        raise FamilySkipped("Cannot fully evaluate all direct Subtasks (project/type/state/archive mismatch).")
    if any(child.state.group != "completed" for child in children):
        raise FamilySkipped("Not all direct Subtasks are in the Completed group (possibly reopened).")
    return parent
