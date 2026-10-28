"""Validation shared by state deletion endpoints."""

from django.db.models import Count

from plane.db.models import Issue, WorkflowVersionState


def get_state_delete_blocker(state):
    if state.default:
        return {
            "code": "DEFAULT_STATE",
            "message": "The default state cannot be deleted.",
            "details": {},
        }

    work_item_count = Issue.objects.filter(state=state).count()
    if work_item_count:
        return {
            "code": "STATE_HAS_WORK_ITEMS",
            "message": "Move existing work items to another state before deleting this state.",
            "details": {"work_item_count": work_item_count},
        }

    workflows = list(
        WorkflowVersionState.objects.filter(state=state)
        .values(
            "workflow_version__workflow_id",
            "workflow_version__workflow__name",
        )
        .annotate(version_count=Count("workflow_version_id", distinct=True))
        .order_by("workflow_version__workflow__name")
    )
    if workflows:
        names = ", ".join(item["workflow_version__workflow__name"] for item in workflows)
        return {
            "code": "STATE_IN_WORKFLOW",
            "message": f"This state is used by workflow(s): {names}. Remove it from those workflows before deleting.",
            "details": {
                "workflows": [
                    {
                        "id": str(item["workflow_version__workflow_id"]),
                        "name": item["workflow_version__workflow__name"],
                        "version_count": item["version_count"],
                    }
                    for item in workflows
                ]
            },
        }

    return None
