# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Hierarchical Estimation Service for Plane
Provides unified calculation logic for:
1. Recursive parent rollup (Epic -> Task -> Subtask, arbitrary depth)
2. Double-counting prevention across Parents and Descendants
3. Leaf-level scoping for Cycles, Modules, and Projects
4. Completion progress based on state groups
"""

from typing import Dict, Any, Optional, Set
from django.db.models import Sum, Case, When, Value, FloatField
from django.db.models.functions import Cast
from plane.db.models import Issue


class HierarchicalEstimateService:
    @staticmethod
    def _parse_estimate_value(estimate_point) -> Optional[float]:
        """Safely extract float point value from an EstimatePoint instance."""
        if not estimate_point or not estimate_point.value:
            return None
        try:
            val = float(estimate_point.value)
            return val
        except (ValueError, TypeError):
            return None

    @classmethod
    def calculate_issue_rollup(cls, issue: Issue, depth_limit: int = 15) -> Dict[str, Any]:
        """
        Calculates the effective, rolled-up estimate and progress metrics for an issue.
        Preserves existing manual estimate in DB while suppressing it from calculation when children exist.
        """
        issue_id = issue.id

        # Fast path if sub_issues_count is already annotated as 0
        sub_count = getattr(issue, "sub_issues_count", None)
        if sub_count == 0:
            manual_val = cls._parse_estimate_value(issue.estimate_point)
            is_unestimated = manual_val is None
            val = manual_val if manual_val is not None else 0.0

            state_group = None
            if hasattr(issue, "state") and issue.state:
                state_group = getattr(issue.state, "group", None)

            is_completed = state_group == "completed"
            is_cancelled = state_group == "cancelled"

            completed_val = val if is_completed else 0.0
            remaining_val = 0.0 if (is_completed or is_cancelled) else val
            progress = 100.0 if (val > 0 and is_completed) else 0.0

            return {
                "effective_estimate": round(val, 2),
                "rolled_up_estimate": None,
                "completed_estimate": round(completed_val, 2),
                "remaining_estimate": round(remaining_val, 2),
                "progress_percentage": round(progress, 1),
                "unestimated_children_count": 1 if is_unestimated else 0,
                "is_rolled_up": False,
                "is_leaf": True,
            }

        # Collect all active descendants level-by-level
        current_parent_ids = [issue_id]
        all_descendants = []
        parent_to_children_ids: Dict[Any, list] = {}
        depth = 0

        while current_parent_ids and depth < depth_limit:
            children = list(
                Issue.issue_objects.filter(
                    parent_id__in=current_parent_ids,
                    archived_at__isnull=True,
                    is_draft=False,
                ).select_related("estimate_point", "state")
            )
            if not children:
                break

            next_parent_ids = []
            for child in children:
                all_descendants.append(child)
                parent_to_children_ids.setdefault(child.parent_id, []).append(child.id)
                next_parent_ids.append(child.id)

            current_parent_ids = next_parent_ids
            depth += 1

        has_children = bool(parent_to_children_ids.get(issue_id))

        if not has_children:
            # Case 1: Leaf Work Item (no sub-work items)
            manual_val = cls._parse_estimate_value(issue.estimate_point)
            is_unestimated = manual_val is None
            val = manual_val if manual_val is not None else 0.0

            state_group = issue.state.group if issue.state else None
            is_completed = state_group == "completed"
            is_cancelled = state_group == "cancelled"

            completed_val = val if is_completed else 0.0
            remaining_val = 0.0 if (is_completed or is_cancelled) else val
            progress = 100.0 if (val > 0 and is_completed) else 0.0

            return {
                "effective_estimate": round(val, 2),
                "rolled_up_estimate": None,
                "completed_estimate": round(completed_val, 2),
                "remaining_estimate": round(remaining_val, 2),
                "progress_percentage": round(progress, 1),
                "unestimated_children_count": 1 if is_unestimated else 0,
                "is_rolled_up": False,
                "is_leaf": True,
            }

        # Case 2: Parent / Epic (has descendants)
        # Identify all leaf descendants in the subtree (descendants that are not parents themselves)
        all_descendant_ids = {d.id for d in all_descendants}
        leaf_descendants = [
            d for d in all_descendants if d.id not in parent_to_children_ids
        ]

        total_pts = 0.0
        completed_pts = 0.0
        remaining_pts = 0.0
        unestimated_count = 0

        for leaf in leaf_descendants:
            val = cls._parse_estimate_value(leaf.estimate_point)
            if val is None:
                unestimated_count += 1
            else:
                total_pts += val
                state_group = leaf.state.group if leaf.state else None
                if state_group == "completed":
                    completed_pts += val
                elif state_group != "cancelled":
                    remaining_pts += val

        progress = (completed_pts / total_pts * 100.0) if total_pts > 0 else 0.0

        return {
            "effective_estimate": round(total_pts, 2),
            "rolled_up_estimate": round(total_pts, 2),
            "completed_estimate": round(completed_pts, 2),
            "remaining_estimate": round(remaining_pts, 2),
            "progress_percentage": round(progress, 1),
            "unestimated_children_count": unestimated_count,
            "is_rolled_up": True,
            "is_leaf": False,
        }

    @classmethod
    def get_in_scope_leaves_queryset(cls, scope_issues_qs):
        """
        Returns only the in-scope leaf issues from a given issues queryset.
        Eliminates double-counting between parents and descendants in the scope.
        """
        in_scope_parent_ids = scope_issues_qs.filter(
            parent_id__isnull=False
        ).values_list("parent_id", flat=True)
        return scope_issues_qs.exclude(id__in=in_scope_parent_ids)

    @classmethod
    def calculate_scope_aggregates(cls, scope_issues_qs) -> Dict[str, Any]:
        """
        Calculates aggregate estimate metrics for any scope (Cycle, Module, Project)
        guaranteeing zero double-counting.
        """
        leaves_qs = cls.get_in_scope_leaves_queryset(scope_issues_qs)

        # Annotate and aggregate points
        aggregates = (
            leaves_qs.filter(estimate_point__estimate__type="points")
            .annotate(value_as_float=Cast("estimate_point__value", FloatField()))
            .aggregate(
                total_estimate_points=Sum("value_as_float", default=Value(0.0), output_field=FloatField()),
                completed_estimate_points=Sum(
                    Case(
                        When(state__group="completed", then="value_as_float"),
                        default=Value(0.0),
                        output_field=FloatField(),
                    )
                ),
                started_estimate_points=Sum(
                    Case(
                        When(state__group="started", then="value_as_float"),
                        default=Value(0.0),
                        output_field=FloatField(),
                    )
                ),
                unstarted_estimate_points=Sum(
                    Case(
                        When(state__group="unstarted", then="value_as_float"),
                        default=Value(0.0),
                        output_field=FloatField(),
                    )
                ),
                backlog_estimate_points=Sum(
                    Case(
                        When(state__group="backlog", then="value_as_float"),
                        default=Value(0.0),
                        output_field=FloatField(),
                    )
                ),
                cancelled_estimate_points=Sum(
                    Case(
                        When(state__group="cancelled", then="value_as_float"),
                        default=Value(0.0),
                        output_field=FloatField(),
                    )
                ),
            )
        )

        total_pts = aggregates.get("total_estimate_points") or 0.0
        completed_pts = aggregates.get("completed_estimate_points") or 0.0
        unestimated_leaves = leaves_qs.filter(estimate_point__isnull=True).count()

        # Provide aliases for backwards compatibility
        aggregates["backlog_estimate_point"] = aggregates.get("backlog_estimate_points") or 0.0
        aggregates["unstarted_estimate_point"] = aggregates.get("unstarted_estimate_points") or 0.0
        aggregates["started_estimate_point"] = aggregates.get("started_estimate_points") or 0.0
        aggregates["cancelled_estimate_point"] = aggregates.get("cancelled_estimate_points") or 0.0

        aggregates["unestimated_items_count"] = unestimated_leaves
        aggregates["progress_percentage"] = (
            round((completed_pts / total_pts * 100.0), 1) if total_pts > 0 else 0.0
        )

        return aggregates
