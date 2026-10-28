# Hướng dẫn Dependencies, Blocking và Automation

## 1. Khái niệm

Dependency là quan hệ giữa hai Work Item. Quan hệ này độc lập với State và không tự đổi ngày trên Gantt.

| Quan hệ    | Ý nghĩa                                     | Ví dụ                      |
| ---------- | ------------------------------------------- | -------------------------- |
| Blocks     | Work Item hiện tại chặn Work Item kia       | Bug A blocks Task B        |
| Blocked by | Work Item hiện tại bị Work Item kia chặn    | Task B is blocked by Bug A |
| Relates to | Hai Work Item có liên quan, không chặn nhau | Task A relates to Task B   |

`Blocks` và `Blocked by` là hai cách nhìn của cùng một quan hệ. Nếu thêm `Bug A blocks Task B`, khi mở Task B sẽ thấy `Blocked by Bug A`. Hệ thống chỉ lưu một bản ghi chuẩn, không tạo hai bản ghi ngược nhau.

Một Work Item được xem là **Blocked** khi có ít nhất một Work Item trong `Blocked by` chưa ở nhóm State `Completed`. Khi blocker hoàn tất, Work Item tự hết Blocked nhưng quan hệ vẫn còn. Nếu blocker được mở lại, Work Item tự Blocked lại.

## 2. Thêm dependency thủ công

1. Mở Work Item.
2. Mở phần Relations hoặc dùng menu thêm relation.
3. Chọn `Blocks`, `Blocked by` hoặc `Relates to`.
4. Tìm Work Item theo mã hoặc tên.
5. Chọn một hoặc nhiều Work Item.

Danh sách relation hiển thị mã, tên, State, Priority và Assignee. Chọn một Work Item để mở chi tiết. Dùng menu của từng dòng để xoá relation.

Hệ thống từ chối các trường hợp sau:

- Work Item liên kết với chính nó.
- Quan hệ đã tồn tại.
- Giữa cùng hai Work Item đã có một loại quan hệ khác.
- Dependency blocking tạo vòng lặp, ví dụ A blocks B, B blocks C, sau đó C blocks A.

## 3. Hiểu màn hình Automation theo cách của Jira

Automation có ba phần:

1. **When**: Sự kiện nào khởi động rule, ví dụ State Changed.
2. **If**: Work Item gây ra sự kiện phải thoả điều kiện nào, ví dụ Work Item Type is Task.
3. **Then**: Hệ thống phải làm gì, ví dụ Create Work Item hoặc Add Dependency.

`Source event` là sự kiện ở phần When. Nó không phải là `Updated Field`.

- `Work Item Updated`: một Work Item được sửa. Có thể chọn `Updated Field` để giới hạn field cần theo dõi.
- `State Changed`: State đổi từ trạng thái này sang trạng thái khác. Đây là lựa chọn rõ ràng hơn khi rule phụ thuộc vào chuyển trạng thái.
- `Work Item Linked`: một relation được tạo.

Nếu cần rule “Task từ Testing bị trả lại thì tạo Bug”, nên chọn `State Changed`, không chọn `Work Item Updated + Work Item Type`.

## 4. Automation Add Dependency và Remove Dependency

Trong phần Then, chọn:

- `Add Dependency` để tạo quan hệ.
- `Remove Dependency` để xoá quan hệ nếu có.

Mỗi action có:

- `Dependency Type`: hướng quan hệ, ví dụ Source blocks target.
- `From Work Item`: đầu nguồn của quan hệ.
- `To Work Item`: đầu đích của quan hệ.

Mỗi đầu có ba cách chọn:

- `Triggering work item`: Work Item đã gây ra event.
- `Work item created by an earlier action`: Work Item được action Create Work Item phía trước tạo ra.
- `Specific work item`: một Work Item cụ thể trong project.

Mode `Work item created by an earlier action` chỉ xuất hiện khi rule có Create Work Item ở phía trước. Nếu có nhiều action tạo Work Item, action dependency dùng Work Item gần nhất được tạo trước nó.

Retry an toàn:

- Add một dependency đã tồn tại không tạo bản ghi thứ hai.
- Remove một dependency không còn tồn tại không gây lỗi.
- Execution history lưu source ID, target ID và relation type đã xử lý.

## 5. Tạo Bug con và để Bug chặn Task

Luồng chuẩn cho trường hợp Testing Rejected:

### When

- Event: `State Changed`.
- From State: trạng thái Testing thực tế của project.
- To State: trạng thái bị trả về, ví dụ In Progress hoặc Rejected.

### If

- Work Item Type `Is` Task.

### Then

Action 1, `Create Work Item`:

- New work item type: Bug.
- Placement: Child of source work item.
- Title: `Testing rejected: {work_item_title}`.
- Priority: chọn theo quy trình của đội.
- Có thể chọn relation trực tiếp là `Created Work Item BLOCKS Triggering Work Item`.

Hoặc để tách rõ hai việc:

1. Create Work Item, không chọn relation.
2. Add Dependency:
   - Type: Source blocks target.
   - From: Work item created by an earlier action.
   - To: Triggering work item.

Kết quả:

- Bug là con trực tiếp của Task nguồn.
- Bug giữ Work Item Type là Bug.
- Task nguồn hiện `Blocked by` Bug.
- Retry worker không tạo thêm Bug nhờ checkpoint `created_issue_id`.

## 6. Blocked và State

Blocked là tín hiệu riêng, không phải một State mới. Mặc định người dùng vẫn có thể chuyển một Work Item đang Blocked sang Completed.

Admin có thể bật:

`Project Settings → Features → Prevent blocked completion`

Khi bật, transition từ State chưa Completed sang nhóm Completed bị từ chối nếu còn blocker active. Khi tắt, hệ thống chỉ cảnh báo bằng badge và không can thiệp workflow.

## 7. List và bộ lọc

List hiển thị:

- Badge đỏ `Blocked N` khi có N blocker active.
- Badge vàng `Blocking N` khi Work Item đang chặn N Work Item khác.

Bộ lọc có:

- `Blocked = Yes`: chỉ Work Item đang bị blocker active chặn.
- `Blocked = No`: Work Item không có blocker active.
- `Blocking = Yes`: Work Item đang chặn ít nhất một Work Item khác.

Trạng thái Blocked được tính theo State hiện tại của blocker, không dựa trên cờ cache nên hoàn tất hoặc reopen blocker cho kết quả đúng.

## 8. Gantt

Gantt hiển thị đường dependency khi cả blocker và Work Item bị chặn đều đang có trong dữ liệu Gantt:

- Đường đỏ liền: dependency đang chặn.
- Đường xám nét đứt: blocker đã Completed.
- Di chuột lên đường để xem tên blocker, Work Item bị chặn và trạng thái dependency.

Đường dependency chỉ để quan sát. Thêm hoặc xoá dependency không tự thay đổi Start Date hoặc Target Date.

## 9. Lịch sử và realtime

- Thêm hoặc xoá relation thủ công tiếp tục tạo Issue Activity như trước.
- Automation ghi kết quả vào Automation Execution History.
- UI cập nhật relation hai chiều trong store. Xoá relation sẽ bỏ ngay ở cả `Blocks` và `Blocked by` mà không cần reload.
- API list relation prefetch Work Item và State liên quan để tránh truy vấn N+1.

## 10. Kiểm tra rule an toàn

UI Dry-run cũ đã được bỏ. Để kiểm tra một rule mà không ảnh hưởng dữ liệu thật:

1. Tạo một project test hoặc các Work Item test riêng.
2. Save rule ở trạng thái disabled.
3. Kiểm tra lại When, If và thứ tự Then.
4. Enable rule.
5. Thực hiện đúng event trên Work Item test, ví dụ đổi State từ Testing sang Rejected.
6. Kiểm tra Automation History, Bug được tạo, quan hệ Blocked by và Activity.
7. Disable rule sau khi kiểm tra nếu chưa muốn áp dụng cho dữ liệu thật.

Không cần chọn “automation nào” ở một màn hình test riêng. Rule đang mở chính là automation được cấu hình; chỉ rule đã Save và Enable mới nhận event tương lai.

## 11. Lưu ý vận hành

- Chạy migration `0136_issue_relation_integrity` trước khi deploy worker mới.
- Migration thêm setting project mặc định `false`, archive mềm self-relation active cũ và thêm DB constraint ngăn self-relation mới.
- Deploy API và worker cùng phiên bản vì worker cần hiểu hai action dependency mới.
- Nếu dùng nhiều worker, row lock và event advisory lock giữ thao tác relation idempotent.
