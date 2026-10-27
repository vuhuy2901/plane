# Plane Hierarchical Estimates — System Audit Report

**Date:** October 2026  
**Auditor:** Antigravity Agent  
**Repository:** `makeplane/plane`  
**Target Environment:** Django 5.2 / Postgres 15.7 / Next.js / MobX / Docker  

---

## 1. Executive Summary

This audit assesses the current state of the Estimates subsystem in Plane, specifically analyzing its support for work item hierarchies (**Epic → Task → Subtask**, plus Bug and custom work item types).

### Core Findings
1. **Estimate Assignment:** Plane currently allows assigning estimates (`estimate_point`) directly to any work item (`Issue`) regardless of hierarchy level, but it does **not** provide hierarchical rollup.
2. **Double Counting Defect:** In Cycle analytics, Module progress, and Project burndown charts, estimates are aggregated via naive SQL `Sum(Cast("estimate_point__value", FloatField()))`. When both a parent (e.g. Task or Epic) and its descendants (e.g. Subtasks) have estimates, **all points are summed together**, creating a severe double-counting defect.
3. **Data Integrity:** Existing manual estimates stored on parent issues must be preserved and not deleted or overwritten when children are attached. Instead, calculation logic must dynamically prioritize leaf-level estimates and suppress parent manual estimates when children exist.

---

## 2. Answers to Specific Audit Questions

### Question 1: Plane hiện cho phép Estimate ở những cấp nào?
- **Answer:** Plane cho phép gán Estimate (`estimate_point_id`) ở **mọi cấp** của Work Item (`Issue` model). 
- Bất kể một Work Item là Epic (`IssueType.is_epic = True`), Task độc lập, Task cha có Subtasks, hay Subtask (`Issue.parent_id` trỏ về task khác), trường `estimate_point` đều có thể được gán thủ công qua API `PATCH /api/v1/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/` hoặc giao diện `EstimateSelect`.
- Không có sự phân biệt giữa leaf work item và parent work item ở tầng lưu trữ hay giao diện chọn estimate hiện tại.

### Question 2: Khi Task có Subtasks, Estimate đã được tự động tổng hợp chưa?
- **Answer:** **CHƯA**. 
- Khi một Task có các Subtasks (các issue con có `parent_id = task.id`), giao diện `EstimateSelect` vẫn hiển thị estimate thủ công của chính Task đó.
- Task cha không tự động tính tổng (rollup) điểm từ các Subtasks con.
- Sub-issues widget (`SubIssuesCollapsibleTitle`) chỉ hiển thị tiến độ theo số lượng items (`completed_count / total_count`), hoàn toàn không tính toán theo Estimate Points.

### Question 3: Epic có hỗ trợ tổng hợp Estimate không?
- **Answer:** **CHƯA**.
- Epic trong Plane được định danh thông qua `IssueType.is_epic = True` (hoặc level 0 trong hierarchy) và chia sẻ cùng model `Issue`.
- Khi người dùng xem chi tiết Epic, hệ thống không tự động tổng hợp Estimate từ các Tasks con hoặc Subtasks thuộc Epic đó.
- Điểm hiển thị trên Epic (nếu có) chỉ là điểm gán thủ công trực tiếp lên Epic.

### Question 4: Có tình trạng tính trùng điểm giữa Parent và Children không?
- **Answer:** **CÓ, ĐÂY LÀ LỖI HIỆN HỮU TRẦM TRỌNG**.
- Trong `apps/api/plane/app/views/cycle/base.py` (hàm `CycleProgressEndpoint` và `CycleAnalyticsEndpoint`), hệ thống thực hiện:
  ```python
  total_estimate_points = Sum("value_as_float")  # Cast("estimate_point__value", FloatField())
  ```
- Tương tự trong `apps/api/plane/app/views/module/base.py` và `apps/api/plane/utils/analytics_plot.py`:
  ```python
  queryset.annotate(estimate=Sum(Cast("estimate_point__value", FloatField())))
  ```
- **Ví dụ thực tế:** Nếu Epic có 13 points, Task con có 8 points, 2 Subtasks có 3 và 5 points, và tất cả đều nằm trong Cycle hoặc Project:
  - Hiện tại Plane tính tổng: $13 + 8 + 3 + 5 = 29$ points!
  - Giá trị đúng thực tế: $8$ points (hoặc $3 + 5 = 8$). Điểm bị nhân đôi/nhân ba do cộng cả cha lẫn con.

### Question 5: Cycle Analytics đang lấy Estimate từ đâu?
- **Answer:** 
  1. `CycleProgressEndpoint` (`/api/v1/workspaces/{slug}/projects/{project_id}/cycles/{cycle_id}/progress/`): Lấy trực tiếp từ bảng `Issue` qua quan hệ `issue_cycle`, lọc `estimate_point__estimate__type="points"` và aggregate `Sum` theo `state__group`.
  2. `CycleAnalyticsEndpoint` (`/api/v1/workspaces/{slug}/projects/{project_id}/cycles/{cycle_id}/analytics/`): Tính phân bổ theo Assignees và Labels bằng cách `Sum(Cast("estimate_point__value", FloatField()))` trên toàn bộ issues thuộc `issue_cycle`.
  3. `CycleTransferIssues` (`apps/api/plane/utils/cycle_transfer_issues.py`): Tổng hợp estimate để chuyển issue dở dang sang cycle mới cũng dùng naive `Sum`.

### Question 6: Có thể tái sử dụng API và service nào?
- **Answer:**
  1. **Models:** Tái sử dụng nguyên vẹn `Estimate`, `EstimatePoint`, `Issue`, `IssueType`, `State`. Không cần thay đổi schema DB hay migration phá vỡ cấu trúc.
  2. **API Endpoints:**
     - `IssueEndpoint` & `WorkItemSerializer` / `IssueListDetailSerializer`: Mở rộng response để trả về `rolled_up_estimate`, `completed_estimate`, `remaining_estimate`, `is_rolled_up`, `unestimated_children_count`.
     - `CycleProgressEndpoint` & `CycleAnalyticsEndpoint`: Tái sử dụng cấu trúc response hiện tại (`total_estimate_points`, `completed_estimate_points`, v.v.) nhưng thay thế bộ lọc aggregation bằng service tính toán phân cấp chính xác (Leaf-only aggregation trong phạm vi scope).
     - `ModuleDetailEndpoint` & `ProjectAnalytics`: Kế thừa logic tính toán từ service chung.
  3. **Frontend Components:**
     - Tái sử dụng `@plane/propel` primitives: `ProgressBar`, `CircularProgress`, `Badge`, `Tooltip`.
     - Tái sử dụng `EstimateSelect` cho Leaf-level items, bọc ngoài bằng `HierarchicalEstimateDisplay` khi item là Parent/Epic có children.

### Question 7: Có dữ liệu Estimate hiện hữu cần bảo toàn không?
- **Answer:** **CÓ**.
- Mọi giá trị `estimate_point` đã được người dùng gán trên các Parent Work Items từ trước **phải được giữ nguyên vẹn trong Database**.
- Không chạy script update gán `estimate_point = NULL` khi task có con. 
- Thay vào đó, service tính toán sẽ tự động xác định trạng thái `is_rolled_up`:
  - Nếu `has_children = True`: hiển thị `rolled_up_estimate` từ descendants, đồng thời giữ `estimate_point` trong DB phòng khi tất cả children bị xóa hoặc tách (unparenting), hoặc để người dùng tham khảo giá trị manual trước đó.

---

## 3. Database & Architecture Inventory

### 3.1. Models Analysis
- `Estimate` (`apps/api/plane/db/models/estimate.py`):
  - `type`: `points` hoặc `categories` (XS, S, M, L, XL).
  - `last_used`: timestamp.
  - `project_id`: foreign key liên kết với Project.
- `EstimatePoint` (`apps/api/plane/db/models/estimate.py`):
  - `estimate_id`: foreign key tới `Estimate`.
  - `key`: int (thứ tự).
  - `value`: varchar(255) (e.g., `"1"`, `"2"`, `"3"`, `"5"`, `"8"` hoặc `"XS"`, `"S"`, `"M"`).
- `Issue` (`apps/api/plane/db/models/issue.py`):
  - `parent_id`: self-referential foreign key (`related_name="parent_issue"`). Hỗ trợ độ sâu vô hạn (arbitrary depth: Epic → Task → Subtask → ...).
  - `type_id`: foreign key tới `IssueType` (`is_epic`, `level`, `name`).
  - `estimate_point_id`: foreign key tới `EstimatePoint`.
  - `state_id`: foreign key tới `State` (`group`: `backlog`, `unstarted`, `started`, `completed`, `cancelled`).

### 3.2. Current Database State (`plane-api-1` / `plane-plane-db-1`)
- **Total Work Items:** 380 issues.
- **Issues with Parent:** 241 issues.
- **Parent Issues:** 54 issues.
- **Deep Hierarchy (Depth $\ge 2$):** 167 issues (Epic → Task → Subtask structure already in heavy active use!).
- **Work Item Types:** `epic` (`is_epic=True`), `Task`, `Sub-task`, `Bug`.

---

## 4. Gap Analysis & Required Enhancements

| Area | Current State | Required Target State |
| :--- | :--- | :--- |
| **Parent Estimate** | Static manual dropdown | Auto-calculated rollup badge + progress + unestimated warning |
| **Leaf Estimate** | Manual dropdown | Manual dropdown (preserved) |
| **Double Counting** | Naive `Sum(estimate_point__value)` sums parent & children | Scope-aware leaf summation: sums only leaves within scope |
| **Progress by Estimate** | Issue count only (`completed/total`) | Completed Points / Total Points (37.5%) with visual progress bar |
| **Cycle & Sprint** | Double-counts parent and children | Accurate sum of unique leaf issues assigned to cycle |
| **Analytics** | Hardcoded SQL float cast across all issues | Unified Python/SQL calculation service avoiding duplicates |
| **Categories Handling** | May crash on float cast if non-numeric | Graceful handling: category systems show count/breakdown, no fake math |

---

## 5. Conclusion & Transition to Phase 2

Plane's underlying database schema and hierarchical relationships (`Issue.parent`, `IssueType.is_epic`) are already well structured and fully capable of supporting hierarchical estimates. The primary limitation is the lack of a **Unified Hierarchical Estimation Calculation Service** in the backend and corresponding reactive presentation logic in the frontend.

Phase 2 establishes the formal mathematical rules, leaf resolution algorithms, and double-counting prevention mechanisms.
