# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Comprehensive Automated Test Suite for Hierarchical Estimates
Covers Phase 10 Test Cases 1 through 9.
"""

import sys
import unittest
from django.test import TestCase
from plane.db.models import (
    Workspace,
    Project,
    Issue,
    IssueType,
    State,
    Estimate,
    EstimatePoint,
    Cycle,
    CycleIssue,
    User,
)
from plane.services.estimate_service import HierarchicalEstimateService


class HierarchicalEstimatesTestCase(TestCase):
    def setUp(self):
        # 1. Setup workspace & user
        self.user, _ = User.objects.get_or_create(
            email="test_estimates@plane.so",
            defaults={"username": "test_estimates", "first_name": "Test", "last_name": "User"},
        )
        self.workspace, _ = Workspace.objects.get_or_create(
            slug="test-estimate-ws",
            defaults={"name": "Test Estimate Workspace", "owner": self.user},
        )

        # 2. Setup project A with points estimate system
        self.project, _ = Project.objects.get_or_create(
            workspace=self.workspace,
            name="Project Estimates A",
            defaults={"created_by": self.user, "identifier": "PEA"},
        )
        self.estimate, _ = Estimate.objects.get_or_create(
            project=self.project,
            name="Fibonacci Points",
            type="points",
            defaults={"workspace": self.workspace, "created_by": self.user},
        )
        self.project.estimate = self.estimate
        self.project.save()

        # Setup standard estimate points: 1, 2, 3, 5, 8
        self.pt_1, _ = EstimatePoint.objects.get_or_create(
            estimate=self.estimate, key=1, value="1",
            defaults={"project": self.project, "workspace": self.workspace, "created_by": self.user}
        )
        self.pt_3, _ = EstimatePoint.objects.get_or_create(
            estimate=self.estimate, key=2, value="3",
            defaults={"project": self.project, "workspace": self.workspace, "created_by": self.user}
        )
        self.pt_5, _ = EstimatePoint.objects.get_or_create(
            estimate=self.estimate, key=3, value="5",
            defaults={"project": self.project, "workspace": self.workspace, "created_by": self.user}
        )
        self.pt_8, _ = EstimatePoint.objects.get_or_create(
            estimate=self.estimate, key=4, value="8",
            defaults={"project": self.project, "workspace": self.workspace, "created_by": self.user}
        )

        # Setup states
        self.state_todo, _ = State.objects.get_or_create(
            project=self.project, name="To Do", group="unstarted",
            defaults={"workspace": self.workspace, "created_by": self.user, "sequence": 1}
        )
        self.state_in_progress, _ = State.objects.get_or_create(
            project=self.project, name="In Progress", group="started",
            defaults={"workspace": self.workspace, "created_by": self.user, "sequence": 2}
        )
        self.state_done, _ = State.objects.get_or_create(
            project=self.project, name="Done", group="completed",
            defaults={"workspace": self.workspace, "created_by": self.user, "sequence": 3}
        )

        # Setup Issue Types
        self.type_epic, _ = IssueType.objects.get_or_create(
            workspace=self.workspace, name="Epic", is_epic=True,
            defaults={"created_by": self.user}
        )
        self.type_task, _ = IssueType.objects.get_or_create(
            workspace=self.workspace, name="Task", is_epic=False,
            defaults={"created_by": self.user}
        )
        self.type_subtask, _ = IssueType.objects.get_or_create(
            workspace=self.workspace, name="Subtask", is_epic=False,
            defaults={"created_by": self.user}
        )

    def test_case_1_leaf_task(self):
        """Case 1: Leaf Task A = 5 Points -> Effective = 5, Rolled Up = None"""
        task = Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            name="Task A",
            estimate_point=self.pt_5,
            state=self.state_todo,
            type=self.type_task,
            created_by=self.user,
        )
        rollup = HierarchicalEstimateService.calculate_issue_rollup(task)
        self.assertEqual(rollup["effective_estimate"], 5.0)
        self.assertFalse(rollup["is_rolled_up"])
        self.assertTrue(rollup["is_leaf"])
        self.assertIsNone(rollup["rolled_up_estimate"])
        self.assertEqual(rollup["unestimated_children_count"], 0)
        print("PASS: Case 1 - Leaf Task A = 5 Points")

    def test_case_2_task_with_subtasks(self):
        """Case 2: Task A with Subtask A1 = 3, Subtask A2 = 5 -> Effective = 8"""
        parent_task = Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            name="Parent Task A",
            state=self.state_todo,
            type=self.type_task,
            created_by=self.user,
        )
        Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=parent_task,
            name="Subtask A1",
            estimate_point=self.pt_3,
            state=self.state_todo,
            type=self.type_subtask,
            created_by=self.user,
        )
        Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=parent_task,
            name="Subtask A2",
            estimate_point=self.pt_5,
            state=self.state_todo,
            type=self.type_subtask,
            created_by=self.user,
        )
        rollup = HierarchicalEstimateService.calculate_issue_rollup(parent_task)
        self.assertEqual(rollup["effective_estimate"], 8.0)
        self.assertEqual(rollup["rolled_up_estimate"], 8.0)
        self.assertTrue(rollup["is_rolled_up"])
        self.assertFalse(rollup["is_leaf"])
        print("PASS: Case 2 - Task with Subtasks (3 + 5 = 8)")

    def test_case_3_epic_with_multiple_tasks(self):
        """Case 3: Epic A with Task A1 (Rollup 8) + Task A2 (Manual 3) -> Epic = 11"""
        epic = Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            name="Epic A",
            state=self.state_todo,
            type=self.type_epic,
            created_by=self.user,
        )
        task_1 = Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=epic,
            name="Task A1",
            state=self.state_todo,
            type=self.type_task,
            created_by=self.user,
        )
        # Subtasks under Task A1
        Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=task_1,
            name="Subtask A1.1",
            estimate_point=self.pt_3,
            state=self.state_todo,
            type=self.type_subtask,
            created_by=self.user,
        )
        Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=task_1,
            name="Subtask A1.2",
            estimate_point=self.pt_5,
            state=self.state_todo,
            type=self.type_subtask,
            created_by=self.user,
        )
        # Standalone Task A2 under Epic
        Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=epic,
            name="Task A2",
            estimate_point=self.pt_3,
            state=self.state_todo,
            type=self.type_task,
            created_by=self.user,
        )

        epic_rollup = HierarchicalEstimateService.calculate_issue_rollup(epic)
        self.assertEqual(epic_rollup["effective_estimate"], 11.0)
        self.assertEqual(epic_rollup["rolled_up_estimate"], 11.0)
        self.assertTrue(epic_rollup["is_rolled_up"])
        print("PASS: Case 3 - Epic with Multiple Tasks (8 + 3 = 11)")

    def test_case_4_parent_preserved_manual_estimate_no_double_count(self):
        """Case 4: Parent had manual estimate = 8. Subtasks 3 and 5 added. Must NOT be 16."""
        parent_task = Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            name="Task A with Old Estimate",
            estimate_point=self.pt_8, # Old manual estimate 8 preserved
            state=self.state_todo,
            type=self.type_task,
            created_by=self.user,
        )
        # Subtasks added
        Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=parent_task,
            name="Subtask A1",
            estimate_point=self.pt_3,
            state=self.state_todo,
            type=self.type_subtask,
            created_by=self.user,
        )
        Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=parent_task,
            name="Subtask A2",
            estimate_point=self.pt_5,
            state=self.state_todo,
            type=self.type_subtask,
            created_by=self.user,
        )

        # 1. Rollup must be 8, not 16
        rollup = HierarchicalEstimateService.calculate_issue_rollup(parent_task)
        self.assertEqual(rollup["effective_estimate"], 8.0)
        self.assertNotEqual(rollup["effective_estimate"], 16.0)

        # 2. Database manual estimate point must remain preserved
        parent_task.refresh_from_db()
        self.assertEqual(parent_task.estimate_point_id, self.pt_8.id)
        print("PASS: Case 4 - Double counting prevented (8 not 16) & manual preserved")

    def test_case_5_completion_progress(self):
        """Case 5: Subtask A1 = 3 (Done), Subtask A2 = 5 (In Progress) -> Progress = 37.5%"""
        parent_task = Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            name="Parent Task Progress",
            state=self.state_in_progress,
            type=self.type_task,
            created_by=self.user,
        )
        Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=parent_task,
            name="Subtask A1",
            estimate_point=self.pt_3,
            state=self.state_done, # Done
            type=self.type_subtask,
            created_by=self.user,
        )
        Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=parent_task,
            name="Subtask A2",
            estimate_point=self.pt_5,
            state=self.state_in_progress, # In Progress
            type=self.type_subtask,
            created_by=self.user,
        )
        rollup = HierarchicalEstimateService.calculate_issue_rollup(parent_task)
        self.assertEqual(rollup["effective_estimate"], 8.0)
        self.assertEqual(rollup["completed_estimate"], 3.0)
        self.assertEqual(rollup["remaining_estimate"], 5.0)
        self.assertEqual(rollup["progress_percentage"], 37.5)
        print("PASS: Case 5 - Completion Progress (3/8 = 37.5%)")

    def test_case_6_update_estimate_reactive_chain(self):
        """Case 6: Changing Subtask A2 from 5 to 8 updates Parent to 11 and Epic to 14"""
        epic = Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            name="Epic Reactive",
            state=self.state_todo,
            type=self.type_epic,
            created_by=self.user,
        )
        parent_task = Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=epic,
            name="Task Reactive",
            state=self.state_todo,
            type=self.type_task,
            created_by=self.user,
        )
        # Standalone sibling under Epic: 3 pts
        Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=epic,
            name="Sibling Task",
            estimate_point=self.pt_3,
            state=self.state_todo,
            type=self.type_task,
            created_by=self.user,
        )
        # Subtask 1: 3 pts
        Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=parent_task,
            name="Subtask 1",
            estimate_point=self.pt_3,
            state=self.state_todo,
            type=self.type_subtask,
            created_by=self.user,
        )
        # Subtask 2: starts at 5 pts
        subtask_2 = Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=parent_task,
            name="Subtask 2",
            estimate_point=self.pt_5,
            state=self.state_todo,
            type=self.type_subtask,
            created_by=self.user,
        )

        # Initial check
        task_rollup = HierarchicalEstimateService.calculate_issue_rollup(parent_task)
        self.assertEqual(task_rollup["effective_estimate"], 8.0)
        epic_rollup = HierarchicalEstimateService.calculate_issue_rollup(epic)
        self.assertEqual(epic_rollup["effective_estimate"], 11.0)

        # Update Subtask 2 to 8 points
        subtask_2.estimate_point = self.pt_8
        subtask_2.save()

        # Recalculate
        updated_task_rollup = HierarchicalEstimateService.calculate_issue_rollup(parent_task)
        self.assertEqual(updated_task_rollup["effective_estimate"], 11.0)
        updated_epic_rollup = HierarchicalEstimateService.calculate_issue_rollup(epic)
        self.assertEqual(updated_epic_rollup["effective_estimate"], 14.0)
        print("PASS: Case 6 - Update Estimate dynamically reflected (Parent 8->11, Epic 11->14)")

    def test_case_7_unestimated_children_warning(self):
        """Case 7: Subtask A1 = 3 Points, Subtask A2 = Unestimated -> Known = 3, Unestimated Count = 1"""
        parent_task = Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            name="Parent Unestimated",
            state=self.state_todo,
            type=self.type_task,
            created_by=self.user,
        )
        Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=parent_task,
            name="Estimated Subtask",
            estimate_point=self.pt_3,
            state=self.state_todo,
            type=self.type_subtask,
            created_by=self.user,
        )
        Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=parent_task,
            name="Unestimated Subtask",
            estimate_point=None, # Unestimated
            state=self.state_todo,
            type=self.type_subtask,
            created_by=self.user,
        )
        rollup = HierarchicalEstimateService.calculate_issue_rollup(parent_task)
        self.assertEqual(rollup["effective_estimate"], 3.0)
        self.assertEqual(rollup["unestimated_children_count"], 1)
        print("PASS: Case 7 - Unestimated Children Warning (Known = 3, Unestimated Count = 1)")

    def test_case_8_cross_cycle_isolation(self):
        """Case 8: Parent in Sprint A, Child in Sprint B. No cross-sprint duplication or cycle mutation."""
        cycle_a = Cycle.objects.create(
            workspace=self.workspace,
            project=self.project,
            name="Sprint A",
            created_by=self.user,
            owned_by=self.user,
        )
        cycle_b = Cycle.objects.create(
            workspace=self.workspace,
            project=self.project,
            name="Sprint B",
            created_by=self.user,
            owned_by=self.user,
        )

        parent_task = Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            name="Parent in Sprint A",
            estimate_point=self.pt_5, # Direct manual estimate for Sprint A
            state=self.state_todo,
            type=self.type_task,
            created_by=self.user,
        )
        CycleIssue.objects.create(
            workspace=self.workspace, project=self.project,
            cycle=cycle_a, issue=parent_task, created_by=self.user
        )

        child_task = Issue.objects.create(
            project=self.project,
            workspace=self.workspace,
            parent=parent_task,
            name="Child in Sprint B",
            estimate_point=self.pt_3, # Estimate in Sprint B
            state=self.state_todo,
            type=self.type_subtask,
            created_by=self.user,
        )
        CycleIssue.objects.create(
            workspace=self.workspace, project=self.project,
            cycle=cycle_b, issue=child_task, created_by=self.user
        )

        # Aggregate Sprint A
        cycle_a_issues = Issue.issue_objects.filter(issue_cycle__cycle=cycle_a, issue_cycle__deleted_at__isnull=True)
        agg_a = HierarchicalEstimateService.calculate_scope_aggregates(cycle_a_issues)
        self.assertEqual(agg_a["total_estimate_points"], 5.0)

        # Aggregate Sprint B
        cycle_b_issues = Issue.issue_objects.filter(issue_cycle__cycle=cycle_b, issue_cycle__deleted_at__isnull=True)
        agg_b = HierarchicalEstimateService.calculate_scope_aggregates(cycle_b_issues)
        self.assertEqual(agg_b["total_estimate_points"], 3.0)

        # Verify child is still in Sprint B and parent still in Sprint A
        self.assertTrue(CycleIssue.objects.filter(cycle=cycle_a, issue=parent_task).exists())
        self.assertTrue(CycleIssue.objects.filter(cycle=cycle_b, issue=child_task).exists())
        print("PASS: Case 8 - Cross-cycle isolation verified (Sprint A = 5, Sprint B = 3)")

    def test_case_9_multi_project_and_categories_safety(self):
        """Case 9: Projects with categorical estimate system handle estimates safely without fake arithmetic."""
        project_cat, _ = Project.objects.get_or_create(
            workspace=self.workspace,
            name="Project Categories B",
            defaults={"created_by": self.user, "identifier": "PCAT"},
        )
        cat_estimate, _ = Estimate.objects.get_or_create(
            project=project_cat,
            name="T-Shirt Sizes",
            type="categories", # T-shirt sizes
            defaults={"workspace": self.workspace, "created_by": self.user},
        )
        project_cat.estimate = cat_estimate
        project_cat.save()

        pt_m = EstimatePoint.objects.create(
            estimate=cat_estimate, key=1, value="M",
            project=project_cat, workspace=self.workspace, created_by=self.user
        )

        cat_task = Issue.objects.create(
            project=project_cat,
            workspace=self.workspace,
            name="T-Shirt Task",
            estimate_point=pt_m,
            state=self.state_todo,
            type=self.type_task,
            created_by=self.user,
        )

        # Rollup should safely parse non-numeric without error
        rollup = HierarchicalEstimateService.calculate_issue_rollup(cat_task)
        self.assertEqual(rollup["effective_estimate"], 0.0)
        self.assertFalse(rollup["is_rolled_up"])
        print("PASS: Case 9 - Multi-project & Categorical Estimate safety verified")


class RollbackException(Exception):
    pass


def run_standalone():
    """Run all 9 tests inside transaction.atomic() blocks that roll back cleanly."""
    from django.db import transaction

    test_case = HierarchicalEstimatesTestCase()
    test_methods = [
        "test_case_1_leaf_task",
        "test_case_2_task_with_subtasks",
        "test_case_3_epic_with_multiple_tasks",
        "test_case_4_parent_preserved_manual_estimate_no_double_count",
        "test_case_5_completion_progress",
        "test_case_6_update_estimate_reactive_chain",
        "test_case_7_unestimated_children_warning",
        "test_case_8_cross_cycle_isolation",
        "test_case_9_multi_project_and_categories_safety",
    ]

    all_passed = True
    print("\n" + "=" * 70)
    print("RUNNING HIERARCHICAL ESTIMATES VERIFICATION SUITE (CASES 1 - 9)")
    print("=" * 70 + "\n")

    for method_name in test_methods:
        try:
            with transaction.atomic():
                test_case.setUp()
                getattr(test_case, method_name)()
                raise RollbackException()
        except RollbackException:
            # Expected rollback to clean up test data
            pass
        except Exception as e:
            all_passed = False
            print(f"FAILED: {method_name} - {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    if all_passed:
        print("ALL 9 HIERARCHICAL ESTIMATE TEST CASES PASSED SUCCESSFULLY!")
    else:
        print("SOME TESTS FAILED - REVIEW OUTPUT ABOVE.")
    print("=" * 70 + "\n")
    return all_passed


if __name__ == "__main__":
    success = run_standalone()
    sys.exit(0 if success else 1)
