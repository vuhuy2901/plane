# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from collections import deque

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from plane.db.models import (
    Issue,
    ProjectMember,
    State,
    StateGroup,
    WorkflowIssueTypeMapping,
    WorkflowTransition,
    WorkflowTransitionAudit,
    WorkflowVersion,
)


class WorkflowRuleError(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def as_dict(self):
        return {"code": self.code, "message": self.message, "details": self.details}


def get_effective_workflow_version(issue, issue_type_id=None):
    """Return the active version mapped to this issue type, or None for legacy behavior."""
    resolved_type_id = issue_type_id if issue_type_id is not None else issue.type_id
    if not resolved_type_id:
        return None
    mapping = (
        WorkflowIssueTypeMapping.objects.filter(
            project_id=issue.project_id,
            issue_type_id=resolved_type_id,
            workflow__active_version__isnull=False,
        )
        .select_related("workflow__active_version")
        .first()
    )
    return mapping.workflow.active_version if mapping else None


def _actor_role(issue, actor):
    if not actor or actor.is_anonymous:
        return None
    return (
        ProjectMember.objects.filter(
            project_id=issue.project_id,
            member_id=actor.id,
            is_active=True,
        )
        .values_list("role", flat=True)
        .first()
    )


def _condition_matches(issue, condition, proposed_values):
    field = condition.get("field")
    operator = condition.get("operator")
    expected = condition.get("value")
    allowed_fields = {"priority", "assignee_ids", "estimate_point", "start_date", "target_date"}
    if field not in allowed_fields:
        return False
    actual = proposed_values.get(field, getattr(issue, field, None))
    if hasattr(actual, "pk"):
        actual = actual.pk
    if operator == "equals":
        return str(actual) == str(expected)
    if operator == "not_equals":
        return str(actual) != str(expected)
    if operator == "is_set":
        return actual not in (None, "", [])
    if operator == "is_not_set":
        return actual in (None, "", [])
    if operator == "contains":
        return isinstance(actual, (list, tuple, set)) and str(expected) in {str(value) for value in actual}
    return False


def _check_transition_rules(issue, transition, actor, proposed_values):
    roles = transition.permissions.get("roles", []) if isinstance(transition.permissions, dict) else []
    if roles and _actor_role(issue, actor) not in roles:
        raise WorkflowRuleError(
            "WORKFLOW_PERMISSION_DENIED",
            "You do not have permission to perform this transition.",
            {"transition_id": str(transition.id)},
        )

    failed_conditions = [
        condition for condition in transition.conditions if not _condition_matches(issue, condition, proposed_values)
    ]
    if failed_conditions:
        raise WorkflowRuleError(
            "WORKFLOW_CONDITION_FAILED",
            "The transition conditions are not satisfied.",
            {"transition_id": str(transition.id), "conditions": failed_conditions},
        )

    missing_fields = []
    for validator in transition.validators:
        if validator.get("type") != "required_fields":
            continue
        for field in validator.get("fields", []):
            value = proposed_values.get(field, getattr(issue, field, None))
            if value in (None, "", []):
                missing_fields.append(field)
    if missing_fields:
        raise WorkflowRuleError(
            "WORKFLOW_VALIDATION_FAILED",
            "Required fields are missing for this transition.",
            {"transition_id": str(transition.id), "fields": sorted(set(missing_fields))},
        )


def order_workflow_transitions(version, source_node, transitions):
    """Sort available outgoing transitions according to the directed workflow graph.

    Forward transitions (progressing towards end states) come first in topological/distance
    order. Backward/reopen transitions follow. Deterministic tie-breaking is applied.
    Annotates each transition with a ``direction`` attribute ("forward" | "backward").
    """
    if not transitions:
        return []

    def layout_coordinate(node, coordinate):
        layout = getattr(node, "layout", None)
        return layout.get(coordinate, 0) if isinstance(layout, dict) else getattr(layout, coordinate, 0)

    states = list(version.states.select_related("layout"))
    all_edges = list(version.transitions.all())

    adj = {s.id: [] for s in states}
    rev_adj = {s.id: [] for s in states}
    for edge in all_edges:
        if edge.source_id in adj and edge.target_id in adj:
            adj[edge.source_id].append(edge.target_id)
            rev_adj[edge.target_id].append(edge.source_id)

    start_nodes = [s for s in states if s.is_start]
    if not start_nodes:
        start_nodes = [s for s in states if not rev_adj.get(s.id)]
    if not start_nodes and states:
        start_nodes = [min(states, key=lambda s: layout_coordinate(s, "position_x"))]

    depth = {}
    queue = []
    for sn in start_nodes:
        depth[sn.id] = 0
        queue.append(sn.id)

    head = 0
    while head < len(queue):
        curr_id = queue[head]
        head += 1
        curr_depth = depth[curr_id]
        for neighbor_id in adj.get(curr_id, []):
            if neighbor_id not in depth:
                depth[neighbor_id] = curr_depth + 1
                queue.append(neighbor_id)

    end_nodes = [s for s in states if s.is_end]
    if not end_nodes:
        end_nodes = [s for s in states if not adj.get(s.id)]

    dist_to_end = {}
    r_queue = []
    for en in end_nodes:
        dist_to_end[en.id] = 0
        r_queue.append(en.id)

    r_head = 0
    while r_head < len(r_queue):
        curr_id = r_queue[r_head]
        r_head += 1
        curr_dist = dist_to_end[curr_id]
        for neighbor_id in rev_adj.get(curr_id, []):
            if neighbor_id not in dist_to_end:
                dist_to_end[neighbor_id] = curr_dist + 1
                r_queue.append(neighbor_id)

    source_depth = depth.get(source_node.id, 0)
    source_dist_end = dist_to_end.get(source_node.id, 9999)
    source_x = layout_coordinate(source_node, "position_x")

    group_rank = {
        "backlog": 0,
        "unstarted": 1,
        "started": 2,
        "completed": 3,
        "cancelled": 3,
        "triage": 0,
    }

    for t in transitions:
        target_node = t.target
        target_depth = depth.get(target_node.id, 9999)
        target_dist_end = dist_to_end.get(target_node.id, 9999)
        target_x = layout_coordinate(target_node, "position_x")

        if target_depth > source_depth:
            direction = "forward"
        elif target_depth < source_depth:
            direction = "backward"
        else:
            if target_dist_end < source_dist_end:
                direction = "forward"
            elif target_dist_end > source_dist_end:
                direction = "backward"
            else:
                if target_x > source_x:
                    direction = "forward"
                elif target_x < source_x:
                    direction = "backward"
                else:
                    target_g = group_rank.get(target_node.group, 1)
                    source_g = group_rank.get(source_node.group, 1)
                    direction = "forward" if target_g >= source_g else "backward"

        t.direction = direction

    def sort_key(t):
        is_forward = t.direction == "forward"
        target_node = t.target
        target_depth = depth.get(target_node.id, 9999)
        target_dist_end = dist_to_end.get(target_node.id, 9999)
        target_y = layout_coordinate(target_node, "position_y")

        if is_forward:
            return (0, target_depth, target_dist_end, target_y, target_node.name, str(t.id))
        else:
            return (1, -target_depth, target_node.name, str(t.id))

    return sorted(transitions, key=sort_key)


def get_available_transitions(issue, actor, proposed_values=None):
    version = get_effective_workflow_version(issue)
    if version is None:
        return None
    source = version.states.select_related("layout").filter(state_id=issue.state_id).first()
    if source is None:
        return []
    available = []
    transitions = source.outgoing_transitions.select_related("target", "target__state", "target__layout")
    for workflow_transition in transitions:
        try:
            _check_transition_rules(issue, workflow_transition, actor, proposed_values or {})
        except WorkflowRuleError:
            continue
        available.append(workflow_transition)
    return order_workflow_transitions(version, source, available)


def transition_issue(
    *,
    issue_id,
    project_id,
    target_state_id=None,
    transition_id=None,
    actor,
    proposed_values=None,
    metadata=None,
):
    """Apply a state change under a row lock and audit it in the same transaction.

    Returns ``(issue, transition)``. A None transition means the project/type is
    intentionally still using Plane's legacy unrestricted state behavior.
    """
    with transaction.atomic():
        issue = Issue.objects.select_for_update().get(pk=issue_id, project_id=project_id)
        proposed_values = proposed_values or {}
        proposed_type = proposed_values.get("type")
        proposed_type_id = getattr(proposed_type, "id", proposed_type)
        current_version = get_effective_workflow_version(issue)
        target_version = get_effective_workflow_version(issue, issue_type_id=proposed_type_id)
        # Changing type and state in one PATCH must not bypass the current graph.
        version = current_version or target_version
        if (
            proposed_type_id
            and str(proposed_type_id) != str(issue.type_id)
            and target_version
            and target_state_id
            and not target_version.states.filter(state_id=target_state_id).exists()
        ):
            raise WorkflowRuleError(
                "STATE_MIGRATION_REQUIRED", "The target state is outside the selected type's workflow."
            )
        if target_state_id and str(issue.state_id) == str(target_state_id):
            return issue, None
        if version is None:
            if target_state_id is None:
                return issue, None
            target = State.objects.filter(pk=target_state_id, project_id=project_id).first()
            if target is None:
                raise WorkflowRuleError("INVALID_STATE", "The target state does not belong to this project.")
            issue.state = target
            issue.save(update_fields=["state", "completed_at", "updated_at"])
            return issue, None

        if transition_id:
            workflow_transition = (
                WorkflowTransition.objects.select_related(
                    "source__state", "target__state", "workflow_version__workflow"
                )
                .filter(
                    workflow_version=version,
                    pk=transition_id,
                    source__state_id=issue.state_id,
                )
                .first()
            )
            if workflow_transition is None:
                raise WorkflowRuleError(
                    "WORKFLOW_TRANSITION_NOT_ALLOWED",
                    "No published workflow transition allows this state change.",
                    {"transition_id": str(transition_id), "from_state_id": str(issue.state_id)},
                )
            if target_state_id and str(workflow_transition.target.state_id) != str(target_state_id):
                raise WorkflowRuleError(
                    "WORKFLOW_TRANSITION_NOT_ALLOWED",
                    "The target state does not match the transition.",
                    {"transition_id": str(transition_id), "to_state_id": str(target_state_id)},
                )
            target_state_id = workflow_transition.target.state_id
        else:
            workflow_transition = (
                WorkflowTransition.objects.select_related(
                    "source__state", "target__state", "workflow_version__workflow"
                )
                .filter(
                    workflow_version=version,
                    source__state_id=issue.state_id,
                    target__state_id=target_state_id,
                )
                .first()
            )
            if workflow_transition is None:
                raise WorkflowRuleError(
                    "WORKFLOW_TRANSITION_NOT_ALLOWED",
                    "No published workflow transition allows this state change.",
                    {"from_state_id": str(issue.state_id), "to_state_id": str(target_state_id)},
                )

        if str(issue.state_id) == str(target_state_id):
            return issue, None

        _check_transition_rules(issue, workflow_transition, actor, proposed_values)

        source_state = issue.state
        issue.state = workflow_transition.target.state
        issue.save(update_fields=["state", "completed_at", "updated_at"])
        WorkflowTransitionAudit.objects.create(
            project=issue.project,
            issue=issue,
            workflow=version.workflow,
            workflow_version=version,
            transition=workflow_transition,
            source_state=source_state,
            target_state=workflow_transition.target.state,
            actor=actor if actor and actor.is_authenticated else None,
            metadata=metadata or {},
        )
        return issue, workflow_transition


def get_workflow_start_state(project_id, issue_type_id):
    if not issue_type_id:
        return None
    mapping = (
        WorkflowIssueTypeMapping.objects.filter(
            project_id=project_id,
            issue_type_id=issue_type_id,
            workflow__active_version__isnull=False,
        )
        .select_related("workflow__active_version")
        .first()
    )
    if mapping is None:
        return None
    node = mapping.workflow.active_version.states.select_related("state").filter(is_start=True).first()
    return node.state if node else None


def validate_state_for_issue_type(issue, issue_type_id):
    version = get_effective_workflow_version(issue, issue_type_id=issue_type_id)
    if version is None:
        return
    if not version.states.filter(state_id=issue.state_id).exists():
        raise WorkflowRuleError(
            "STATE_MIGRATION_REQUIRED",
            "The work item's current state is not present in the workflow mapped to the selected type.",
            {"state_id": str(issue.state_id), "issue_type_id": str(issue_type_id)},
        )


def validate_workflow_version(version):
    states = list(version.states.all())
    transitions = list(version.transitions.select_related("source", "target"))
    errors = []
    warnings = []
    if len(states) == 0:
        errors.append({"code": "EMPTY_WORKFLOW", "message": "Add at least one state."})
        return {"valid": False, "errors": errors, "warnings": warnings}
    starts = [state for state in states if state.is_start]
    if len(starts) != 1:
        errors.append({"code": "START_STATE_COUNT", "message": "A workflow must have exactly one start state."})

    state_ids = {state.id for state in states}
    for workflow_transition in transitions:
        if workflow_transition.source_id not in state_ids or workflow_transition.target_id not in state_ids:
            errors.append(
                {
                    "code": "DANGLING_TRANSITION",
                    "message": "A transition references a state outside this version.",
                    "transition_id": str(workflow_transition.id),
                }
            )
        if workflow_transition.source_id == workflow_transition.target_id:
            warnings.append(
                {
                    "code": "SELF_TRANSITION",
                    "message": "A transition points back to the same state.",
                    "transition_id": str(workflow_transition.id),
                }
            )
        roles = (
            workflow_transition.permissions.get("roles", [])
            if isinstance(workflow_transition.permissions, dict)
            else None
        )
        if roles is None or not isinstance(roles, list) or any(role not in {5, 15, 20} for role in roles):
            errors.append(
                {
                    "code": "INVALID_TRANSITION_PERMISSIONS",
                    "message": "Transition roles must contain only project Admin, Member, or Guest roles.",
                    "transition_id": str(workflow_transition.id),
                }
            )
        conditions = workflow_transition.conditions if isinstance(workflow_transition.conditions, list) else []
        if not isinstance(workflow_transition.conditions, list):
            errors.append(
                {
                    "code": "INVALID_TRANSITION_CONDITION",
                    "message": "Transition conditions must be an array.",
                    "transition_id": str(workflow_transition.id),
                }
            )
        for condition in conditions:
            if not isinstance(condition, dict):
                errors.append(
                    {
                        "code": "INVALID_TRANSITION_CONDITION",
                        "message": "Each transition condition must be an object.",
                        "transition_id": str(workflow_transition.id),
                    }
                )
                continue
            if condition.get("field") not in {
                "priority",
                "assignee_ids",
                "estimate_point",
                "start_date",
                "target_date",
            } or condition.get("operator") not in {
                "equals",
                "not_equals",
                "is_set",
                "is_not_set",
                "contains",
            }:
                errors.append(
                    {
                        "code": "INVALID_TRANSITION_CONDITION",
                        "message": "A transition condition uses an unsupported field or operator.",
                        "transition_id": str(workflow_transition.id),
                    }
                )
        validators = workflow_transition.validators if isinstance(workflow_transition.validators, list) else []
        if not isinstance(workflow_transition.validators, list) or any(
            not isinstance(validator, dict) or validator.get("type") != "required_fields" for validator in validators
        ):
            errors.append(
                {
                    "code": "INVALID_TRANSITION_VALIDATOR",
                    "message": "Only the required_fields validator is currently supported.",
                    "transition_id": str(workflow_transition.id),
                }
            )
        if workflow_transition.post_actions:
            errors.append(
                {
                    "code": "UNSUPPORTED_POST_ACTION",
                    "message": "Post actions are reserved but not enabled in this self-hosted release.",
                    "transition_id": str(workflow_transition.id),
                }
            )

    if len(starts) == 1:
        adjacency = {state.id: [] for state in states}
        for workflow_transition in transitions:
            adjacency.setdefault(workflow_transition.source_id, []).append(workflow_transition.target_id)
        reachable = set()
        queue = deque([starts[0].id])
        while queue:
            state_id = queue.popleft()
            if state_id in reachable:
                continue
            reachable.add(state_id)
            queue.extend(adjacency.get(state_id, []))
        for state in states:
            if state.id not in reachable:
                item = {
                    "code": "UNREACHABLE_STATE",
                    "message": f"State '{state.name}' cannot be reached from the start state.",
                    "state_id": str(state.id),
                }
                (errors if state.is_end else warnings).append(item)

    allowed_groups = {choice for choice, _ in StateGroup.choices}
    for state in states:
        if state.group not in allowed_groups:
            errors.append(
                {"code": "INVALID_STATE_GROUP", "message": f"State '{state.name}' has an invalid Plane group."}
            )
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def publish_workflow(version, actor):
    with transaction.atomic():
        version = (
            WorkflowVersion.objects.select_for_update()
            .select_related("workflow", "project")
            .get(pk=version.pk, project_id=version.project_id)
        )
        if version.status != WorkflowVersion.Status.DRAFT:
            raise WorkflowRuleError("NOT_A_DRAFT", "Only a draft workflow version can be published.")
        result = validate_workflow_version(version)
        if not result["valid"]:
            raise WorkflowRuleError("INVALID_WORKFLOW", "The workflow cannot be published.", result)

        # Do not publish a graph that strands existing work items. Migration is a separate,
        # explicit operation and is deliberately not guessed here.
        state_ids = set(version.states.exclude(state__isnull=True).values_list("state_id", flat=True))
        mapped_type_ids = list(version.workflow.issue_type_mappings.values_list("issue_type_id", flat=True))
        stranded = Issue.objects.filter(
            project_id=version.project_id,
            type_id__in=mapped_type_ids,
        ).exclude(state_id__in=state_ids)
        if version.workflow.active_version_id and stranded.exists():
            raise WorkflowRuleError(
                "STATE_MIGRATION_REQUIRED",
                "Existing work items use states that are not present in this draft.",
                {"work_item_count": stranded.count()},
            )

        for node in version.states.select_for_update():
            if node.state_id:
                if node.state.project_id != version.project_id:
                    raise WorkflowRuleError("CROSS_PROJECT_STATE", "A workflow state belongs to another project.")
                state = node.state
                existing_other = (
                    State.objects.filter(
                        project=version.project,
                        name__iexact=node.name,
                        deleted_at__isnull=True,
                    )
                    .exclude(pk=state.pk)
                    .first()
                )
                if existing_other is not None:
                    node.state = existing_other
                    node.save(update_fields=["state", "updated_at"])
                else:
                    state.name = node.name
                    state.description = node.description
                    state.color = node.color
                    state.group = node.group
                    state.save()
            else:
                existing_state = State.objects.filter(
                    project=version.project,
                    name__iexact=node.name,
                    deleted_at__isnull=True,
                ).first()
                if existing_state is not None:
                    node.state = existing_state
                    node.save(update_fields=["state", "updated_at"])
                else:
                    state = State.objects.create(
                        project=version.project,
                        name=node.name,
                        description=node.description,
                        color=node.color,
                        group=node.group,
                        default=False,
                    )
                    node.state = state
                    node.save(update_fields=["state", "updated_at"])

        version.status = WorkflowVersion.Status.PUBLISHED
        version.published_at = timezone.now()
        version.published_by = actor
        version.save(update_fields=["status", "published_at", "published_by", "updated_at"])
        workflow = version.workflow
        workflow.active_version = version
        workflow.save(update_fields=["active_version", "updated_at"])
        return version, result


def next_workflow_version(workflow):
    current = workflow.versions.aggregate(value=Max("version"))["value"] or 0
    return current + 1
