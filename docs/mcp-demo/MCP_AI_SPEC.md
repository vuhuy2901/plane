# Đặc tả Plane MCP AI

## 1. Mục tiêu

Plane MCP AI cung cấp một kết nối để ChatGPT Work đọc và thao tác dữ liệu Plane thông qua Model Context Protocol (MCP). Người dùng tạo một URL riêng cho từng kết nối. URL này mang quyền của Personal API Key đã chọn và có thể thu hồi bất cứ lúc nào.

Phạm vi của đặc tả:

- Cài đặt và kết nối Plane với ChatGPT Work.
- Chọn workspace và project để chạy demo.
- Kiểm tra tool đọc và tool ghi.
- Xử lý lỗi xác thực, OAuth, hostname và tunnel.
- Thu hồi thông tin truy cập sau buổi demo.

## 2. Mô hình kết nối

```text
ChatGPT Work
    |
    | HTTPS + MCP Streamable HTTP
    v
Public tunnel or reverse proxy
    |
    | /mcp/c/<opaque-token>
    v
Plane ASGI application
    |
    | resolve token -> decrypt stored Personal API Key
    v
Plane MCP tools -> Plane REST API -> PostgreSQL
```

Portal web ở `/mcp-connect/` chỉ tạo và quản lý kết nối. MCP server vẫn dùng registry tool hiện có của Plane.

## 3. Điều kiện trước khi dùng

- Plane API và web đang chạy.
- API được phục vụ bằng ASGI/Uvicorn để route `/mcp/c/*` đi vào `plane.asgi:application`.
- ChatGPT Work có quyền dùng custom MCP hoặc plugin theo chính sách workspace.
- Có một Personal API Token của tài khoản demo.
- Có một project demo riêng để thử thao tác ghi.
- ChatGPT truy cập được URL HTTPS public. `localhost` chỉ dùng cho trình duyệt trên cùng máy và không thể dùng làm MCP URL cho ChatGPT Work.

## 4. Cấu hình local

Trong `apps/api/.env`, dùng các biến sau khi có hostname public:

```env
WEB_URL="https://<public-host>"
APP_BASE_URL="http://localhost:3000"
MCP_PUBLIC_BASE_URL="https://<public-host>"
MCP_ALLOWED_HOSTS="localhost,localhost:*,127.0.0.1,127.0.0.1:*,<public-host>"
MCP_ALLOWED_ORIGINS="http://localhost:3000,https://<public-host>,https://chatgpt.com,https://chat.openai.com"
```

Sau khi sửa `.env`, phải recreate API container để nạp environment mới:

```powershell
docker compose -f docker-compose-local.yml up -d --force-recreate api
```

`MCP_PUBLIC_BASE_URL` quyết định URL được hiển thị khi người dùng bấm Copy MCP URL. `WEB_URL` giữ vai trò URL public chung của Plane. Nếu dùng quick tunnel, hostname có thể đổi sau mỗi lần khởi động; cập nhật cả hai biến allowlist và recreate API.

Không commit `apps/api/.env` hoặc các file `.env` có secret. Chỉ commit `.env.example` và cấu hình deployment không chứa credential.

## 5. Tạo Personal API Key

1. Mở avatar tài khoản và vào phần settings.
2. Mở **Personal Access Tokens** hoặc **API Tokens**.
3. Bấm **Add access token**.
4. Đặt tên, ví dụ `MCP classroom demo`, và đặt thời hạn phù hợp.
5. Copy key ngay trong màn hình tạo token.

Plane chỉ hiển thị đầy đủ key một lần. Danh sách token chỉ hiển thị tên và trạng thái; không thể copy lại một token cũ nếu đã mất giá trị ban đầu.

## 6. Tạo kết nối trong Plane

1. Bấm mục **AI / MCP** ở sidebar trái.
2. Trong tab **Connect**, nhập Plane Server URL của instance đang chạy portal.
3. Nhập workspace slug. Đây là mã workspace trong URL workspace, không phải project slug.
4. Dán Personal API Key.
5. Bấm **Test connection**.
6. Bấm **Generate MCP connection**.
7. Vào **Dashboard** và copy URL bắt đầu bằng `https://` của public tunnel.

Sau khi tạo, browser giữ connection token trong HttpOnly cookie. Server lưu token dưới dạng hash và lưu Personal API Key ở dạng mã hóa.

## 7. Kết nối ChatGPT Work

Trong ChatGPT Work, mở phần tạo custom app/MCP theo chính sách workspace:

1. Bật Developer mode nếu workspace cho phép.
2. Tạo custom MCP app hoặc connector.
3. Dán Personal MCP URL đã copy.
4. Chọn **No authentication** nếu giao diện yêu cầu phương thức xác thực.
5. Không chọn OAuth cho URL demo này. URL đã chứa bearer credential; server không triển khai OAuth issuer, authorization endpoint hoặc callback.
6. Chọn **Scan Tools**.
7. Xác nhận server được tạo và mở một cuộc trò chuyện mới.
8. Chọn app Plane trong tool menu.

Một số workspace có thể chỉ cho kết nối MCP thông qua plugin hoặc admin policy. Khi không thấy nút Create hoặc Scan Tools, cần bật quyền tương ứng ở workspace hoặc dùng MCP Inspector để kiểm tra server.

## 8. Kiểm tra kết nối

Bắt đầu bằng tool đọc:

```text
List my Plane projects
```

Sau đó kiểm tra project:

```text
List work items in project <project name>
```

Chỉ thử tool ghi trong project demo:

```text
Create a test work item in project <project name> titled "MCP connection test"
```

ChatGPT phải yêu cầu hoặc hiển thị bước xác nhận trước thao tác ghi. Kiểm tra work item được tạo trong Plane, sau đó thu hồi hoặc xóa dữ liệu demo.

## 9. Tool và quyền

Portal lấy danh sách tool động từ MCP registry. Tool được phân loại thành:

- **Read**: liệt kê project, work item, trạng thái và đọc chi tiết.
- **Write**: tạo work item, tạo subtask hoặc cập nhật trạng thái.

Portal yêu cầu `confirm_write: true` cho tool ghi. Mọi tool request được giới hạn theo workspace đã lưu trong connection. Activity log chỉ lưu loại request, tên tool, request ID, trạng thái và thời gian; không lưu API key, URL bearer hoặc arguments nhạy cảm.

## 10. Xử lý lỗi

### `OAuth` hoặc `Không xác thực OAuth`

Chọn **No authentication**. Đây là bearer URL, không phải OAuth server. Nếu ChatGPT vẫn thử OAuth, xóa connector cũ và tạo lại custom MCP app với URL mới.

### `Server không thể hoàn tất việc thiết lập MCP`

Kiểm tra lần lượt:

1. URL public trả HTTPS và không phải `localhost`.
2. Tunnel đang chạy và trỏ vào API port 8000.
3. API chạy `plane.asgi:application` bằng Uvicorn.
4. Hostname tunnel có trong `MCP_ALLOWED_HOSTS`.
5. Origin của client có trong `MCP_ALLOWED_ORIGINS`.
6. `MCP_PUBLIC_BASE_URL` trùng hostname URL được copy từ portal.
7. Tạo connection mới sau khi đổi hostname hoặc secret.

Probe tối thiểu cần đạt:

- `initialize`: HTTP 200 và trả `serverInfo`.
- `tools/list`: HTTP 200 và trả danh sách tool không rỗng.

Log `Invalid Host header` nghĩa là thiếu hostname trong `MCP_ALLOWED_HOSTS`. HTTP 403 khi request có `Origin` nghĩa là thiếu origin trong `MCP_ALLOWED_ORIGINS`.

### URL vẫn hiển thị `localhost`

Đặt `MCP_PUBLIC_BASE_URL` bằng HTTPS hostname và recreate API container để đổi mặc định toàn server. Hoặc vào **Dashboard → Edit Public URL** để lưu hostname riêng cho connection hiện tại; thao tác này cập nhật URL ngay mà không regenerate token hay credentials.

### URL vẫn hiển thị IP Radmin VPN

Kiểm tra process `manage.py runserver` trên host. Một API host cũ có thể chiếm port 8000 và không dùng cấu hình ASGI mới. Dừng process trùng port, để Docker API Uvicorn phục vụ cổng 8000.

## 11. Thu hồi sau demo

1. Vào **AI / MCP → Dashboard**.
2. Bấm **Disconnect** để revoke URL hiện tại, hoặc **Regenerate connection** để revoke URL cũ và tạo URL mới.
3. Revoke Personal API Token trong Plane nếu token chỉ dùng cho buổi demo.
4. Xóa work item và dữ liệu demo.
5. Dừng tunnel nếu không còn cần truy cập public.

## 12. Tiêu chí nghiệm thu

- Người dùng vào portal bằng mục **AI / MCP** ở sidebar.
- Personal API Key hợp lệ tạo được URL HTTPS riêng.
- URL sai, hết hạn hoặc đã revoke trả 404.
- `initialize` và `tools/list` trả HTTP 200 qua tunnel public.
- Tool đọc chạy được trong workspace đã kết nối.
- Tool ghi yêu cầu xác nhận và ghi đúng project demo.
- Regenerate làm URL cũ không còn dùng được.
- Disconnect xóa cookie portal và revoke server-side connection.
- Không có API key hoặc bearer URL trong activity log và source code commit.
