# Plane Hierarchical Estimates — Calculation Rules & Mathematical Specification

**Document Version:** 1.0  
**Status:** Approved Specification  
**Scope:** Work Items (Epics, Tasks, Subtasks, Bugs, Custom Types), Cycles, Modules, and Analytics  

---

## 1. Core Principles

The Hierarchical Estimation system in Plane operates on three foundational principles:
1. **Leaf-level Estimation:** Only leaf work items (items with no sub-work items) accept direct manual estimates.
2. **Parent Rollup:** Work items with sub-work items automatically aggregate and display rolled-up estimates computed from all descendant leaf nodes.
3. **Double-Counting Prevention (The Golden Rule):** An effort point must be counted **exactly once** in any scope aggregation (Parent, Epic, Cycle, Module, or Project). Parents and descendants must never have their estimates summed together.

---

## 2. Definitions and Terminology

Let $\mathcal{W}$ be the set of all active (non-deleted, non-archived, non-draft) work items in the workspace.

For any work item $u \in \mathcal{W}$:
- $\text{Children}(u) = \{ v \in \mathcal{W} \mid v.\text{parent\_id} = u.\text{id} \}$
- $\text{Descendants}(u) = \text{Children}(u) \cup \bigcup_{v \in \text{Children}(u)} \text{Descendants}(v)$
- $\text{IsLeaf}(u) \iff \text{Children}(u) = \emptyset$
- $\text{LeafDescendants}(u) = \{ v \in \text{Descendants}(u) \mid \text{IsLeaf}(v) \}$
- $M(u)$: The manual estimate points assigned to $u$ ($M(u) \in \mathbb{R}_{\ge 0} \cup \{\text{None}\}$).
- $S(u)$: The state group of $u$, where $S(u) \in \{\text{backlog}, \text{unstarted}, \text{started}, \text{completed}, \text{cancelled}\}$.

---

## 3. Mathematical Formulation of Rules

### Rule 1: Leaf-level Estimation
For any work item $u$ where $\text{IsLeaf}(u) = \text{True}$:
- **Effective Estimate ($E(u)$):**
  $$E(u) = \begin{cases} M(u) & \text{if } M(u) \ne \text{None} \\ 0 & \text{if } M(u) = \text{None} \end{cases}$$
- **Completed Estimate ($C(u)$):**
  $$C(u) = \begin{cases} E(u) & \text{if } S(u) = \text{completed} \\ 0 & \text{otherwise} \end{cases}$$
- **Remaining Estimate ($R(u)$):**
  $$R(u) = \begin{cases} E(u) - C(u) & \text{if } S(u) \ne \text{cancelled} \\ 0 & \text{if } S(u) = \text{cancelled} \end{cases}$$
- **Unestimated Count ($U(u)$):**
  $$U(u) = \begin{cases} 1 & \text{if } M(u) = \text{None} \\ 0 & \text{if } M(u) \ne \text{None} \end{cases}$$
- **Is Rolled Up:** $\text{IsRolledUp}(u) = \text{False}$.

---

### Rule 2: Parent Rollup (Recursive & Multi-level)
For any work item $u$ where $\text{IsLeaf}(u) = \text{False}$:
- **Effective Rolled-Up Estimate ($E(u)$):**
  $$E(u) = \sum_{v \in \text{Children}(u)} E(v) = \sum_{l \in \text{LeafDescendants}(u)} E(l)$$
- **Completed Estimate ($C(u)$):**
  $$C(u) = \sum_{v \in \text{Children}(u)} C(v) = \sum_{l \in \text{LeafDescendants}(u)} C(l)$$
- **Remaining Estimate ($R(u)$):**
  $$R(u) = \sum_{v \in \text{Children}(u)} R(v) = \sum_{l \in \text{LeafDescendants}(u)} R(l)$$
- **Unestimated Descendant Count ($U(u)$):**
  $$U(u) = \sum_{l \in \text{LeafDescendants}(u)} U(l)$$
- **Is Rolled Up:** $\text{IsRolledUp}(u) = \text{True}$.

---

### Rule 3: Prevention of Double Counting

#### 3.1. Parent Manual Estimate Preservation
When an item $u$ transitions from leaf to parent (e.g. its first subtask is added):
- $M(u)$ (the manual estimate on $u$) **remains untouched in the database**.
- In all rollup and aggregation calculations, $M(u)$ is **suppressed** and replaced by $\sum_{v \in \text{Children}(u)} E(v)$.
- If all children of $u$ are subsequently deleted or detached, $u$ becomes a leaf again, and $E(u)$ automatically reverts to $M(u)$.

#### 3.2. Scope-based Aggregation (Cycles, Modules, Projects)
Let $\mathcal{I} \subseteq \mathcal{W}$ be a targeted subset of work items (for example, all items assigned to `Cycle C`).

Define the **In-Scope Children** for any $u \in \mathcal{I}$:
$$\text{Children}_{\mathcal{I}}(u) = \{ v \in \mathcal{I} \mid v.\text{parent\_id} = u.\text{id} \}$$

An item $u \in \mathcal{I}$ is an **In-Scope Leaf** iff $\text{Children}_{\mathcal{I}}(u) = \emptyset$.
$$\text{Leaves}(\mathcal{I}) = \{ u \in \mathcal{I} \mid \text{Children}_{\mathcal{I}}(u) = \emptyset \}$$

The Total Scope Estimate is defined strictly over **In-Scope Leaves**:
$$\text{TotalEstimate}(\mathcal{I}) = \sum_{u \in \text{Leaves}(\mathcal{I})} E(u)$$
$$\text{CompletedEstimate}(\mathcal{I}) = \sum_{u \in \text{Leaves}(\mathcal{I})} C(u)$$

> [!IMPORTANT]
> **Why this prevents double counting:**
> If both Parent $P \in \mathcal{I}$ and Child $C \in \mathcal{I}$, then $P \notin \text{Leaves}(\mathcal{I})$. Only $C$ is in $\text{Leaves}(\mathcal{I})$. $P$'s points are never added to $C$'s points.
> If Child $C \notin \mathcal{I}$ (assigned to another Cycle or unassigned), then $P$ has no children *in this cycle*, so $P \in \text{Leaves}(\mathcal{I})$ and its own effective estimate represents its contribution to Cycle $\mathcal{I}$.

---

### Rule 4: Distinguish Estimate Systems

Plane supports two distinct estimate systems configured per project:
1. **Points (`points`):**
   - Stored values are numbers or numeric strings (e.g. `0`, `1`, `2`, `3`, `5`, `8`, `13`).
   - Standard summation apply ($E(u) = \sum E(v)$).
2. **Categories (`categories`):**
   - Stored values are discrete t-shirt sizes (`XS`, `S`, `M`, `L`, `XL`).
   - Categorical estimates **cannot be added arithmetically** without a user-configured numerical mapping.
   - For categorical projects:
     - Rollup displays a distribution breakdown (e.g. `1 XS, 2 M`) or `N/A`.
     - Percentage progress is calculated using item counts rather than fake Fibonacci conversions.
     - Never assume $1 \text{ Point} = 1 \text{ Hour}$ or $\text{M} = 3 \text{ Points}$.

---

## 5. Progress Calculation Formula

$$\text{Estimate Progress (\%)} = \begin{cases} \dfrac{\text{Completed Effective Estimate}}{\text{Total Effective Estimate}} \times 100 & \text{if Total Effective Estimate} > 0 \\ 0\% & \text{if Total Effective Estimate} = 0 \end{cases}$$

### Completion State Rule
- A work item is considered **Completed** if and only if:
  $$S(u) = \text{completed}$$
- Items in `backlog`, `unstarted`, `started` (In Progress, In Review, In Testing), or `cancelled` are **NOT** considered completed.

### Unestimated Items Warning
- When $U(u) > 0$ and $E(u) > 0$:
  - The UI must display an unestimated children warning badge:
    `⚠️ {U(u)} sub-work items have no estimate`
  - $100\%$ completed points does **not** equal 100% project completion if $U(u) > 0$.

---

## 6. Cross-Cycle & Multi-Project Scoping

1. **Cross-Cycle Independence:**
   - Work items belong to cycles via `issue_cycle` entries.
   - If Task $T$ is in Cycle 1 and Subtask $S$ is in Cycle 2:
     - In Cycle 1: $\text{Children}_{\text{Cycle 1}}(T) = \emptyset \implies T$ contributes its own estimate to Cycle 1.
     - In Cycle 2: $S$ contributes its estimate to Cycle 2.
     - Effort is never counted twice across cycles.
2. **Multi-Project & Permissions Safety:**
   - Descendants in other projects with different estimate systems are handled safely:
     - If estimate systems differ or points are incompatible, values are not naively mixed.
     - Items in projects that the current user lacks permission to view are redacted or aggregated into an anonymized subtotal without exposing confidential titles or links.

---

## 7. Concrete Example Walkthroughs

### Example 1: Standard Hierarchy (Epic → Task → Subtask)
- **Subtask A1:** 3 Points, `completed`
- **Subtask A2:** 5 Points, `started`
- **Task A (Parent of A1, A2):** Has manual estimate = 8 (from before subtasks were created).
  - *Calculation:* $\text{IsLeaf}(A) = \text{False} \implies E(A) = 3 + 5 = 8$ Points.
  - *Completed:* $C(A) = 3$ Points.
  - *Progress:* $3 / 8 = 37.5\%$.
  - *Manual estimate 8:* Preserved in DB, not added ($8 + 8 \ne 16$).
- **Task B (Standalone Task):** 5 Points, `unstarted`.
- **Epic X (Parent of Task A, Task B):**
  - *Calculation:* $\text{Descendants}(X) = \{ A, A1, A2, B \}$.
  - *Leaves:* $\{ A1, A2, B \}$.
  - $E(X) = 3 + 5 + 5 = 13$ Points.
  - $C(X) = 3$ Points.
  - *Progress:* $3 / 13 = 23.1\%$.

### Example 2: Cycle Aggregation
Cycle contains $\{ \text{Epic X}, \text{Task A}, \text{Subtask A1}, \text{Subtask A2}, \text{Task B} \}$.
- Scope $\mathcal{I} = \{ X, A, A1, A2, B \}$.
- $\text{Leaves}(\mathcal{I}) = \{ A1, A2, B \}$.
- $\text{Total Cycle Points} = 3 + 5 + 5 = 11$ Points.
- **Double Counting Avoided:** $X$ (13 pts) and $A$ (8 pts) are parents in $\mathcal{I}$, so their rolled-up points are omitted from the sum. Total is exactly $13$ (or $3+5+5=13$).
