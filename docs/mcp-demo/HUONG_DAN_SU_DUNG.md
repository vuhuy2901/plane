# Hướng dẫn cài đặt và sử dụng Plane MCP Connect

Tài liệu này hướng dẫn chạy bản Plane tùy biến trong repository này trên Windows, công khai MCP qua ngrok và kết nối với một MCP client như ChatGPT. Không đưa API key, Personal MCP URL hoặc `SECRET_KEY` lên ảnh chụp màn hình, chat hay tài liệu công khai.

## 1. Yêu cầu hệ thống

- Windows 10/11 và PowerShell.
- Docker Desktop đang chạy.
- Git.
- Node.js `>= 22.22.0`.
- Corepack và pnpm `11.10.0` (phiên bản được khóa trong `package.json`).
- Python phù hợp với `apps/api/pyproject.toml` và đúng phiên bản `uv` ghi trong trường `required-version`.
- ngrok CLI nếu cần kết nối từ Internet.

Kiểm tra nhanh:

```powershell
docker info
node --version
corepack pnpm --version
uv --version
ngrok version
```

## 2. Chuẩn bị lần đầu

Tại thư mục gốc của repository:

```powershell
corepack enable
bash ./setup.sh
cd apps/api
uv sync
cd ../..
```

`setup.sh` tạo các file `.env`, sinh Django `SECRET_KEY` và cài package JavaScript. Nếu không có Bash, có thể sao chép thủ công từng `.env.example` thành `.env`, chạy `corepack pnpm install`, rồi thêm một `SECRET_KEY` mạnh vào `apps/api/.env`.

Khởi động các dịch vụ hạ tầng và chạy migration:

```powershell
docker compose -f docker-compose-local.yml up -d plane-db plane-redis plane-mq plane-minio
cd apps/api
uv run --env-file .env python manage.py migrate
cd ../..
```

## 3. Cấu hình MCP

Các biến quan trọng trong `apps/api/.env`:

```dotenv
CORS_ALLOWED_ORIGINS="http://localhost:3000,http://localhost:3001,https://<ten-mien-public>"
MCP_ALLOWED_HOSTS="localhost,localhost:*,127.0.0.1,127.0.0.1:*,<ten-mien-public>"
MCP_ALLOWED_ORIGINS="https://chatgpt.com,https://<ten-mien-public>"
MCP_PUBLIC_BASE_URL="https://<ten-mien-public>"
MCP_ALLOW_LOCAL_PUBLIC_URL=0
MCP_CONNECTION_TTL_HOURS=168
```

Lưu ý:

- Chỉ nhập hostname, không có `https://`, trong `MCP_ALLOWED_HOSTS`.
- Nhập origin đầy đủ, có scheme nhưng không có path, trong `CORS_ALLOWED_ORIGINS` và `MCP_ALLOWED_ORIGINS`.
- Giữ `MCP_ALLOW_LOCAL_PUBLIC_URL=0` khi dùng ngoài môi trường phát triển.
- Sau khi đổi `.env`, khởi động lại API. Nếu API chạy trong container, cần tạo lại container để nạp biến môi trường mới.
- Người dùng có thể đặt Public Tunnel URL riêng trên portal; giá trị này được ưu tiên hơn `MCP_PUBLIC_BASE_URL`.

## 4. Chạy ứng dụng

Cách nhanh trên Windows:

```powershell
.\start-plane.ps1
```

Script mở các tiến trình hạ tầng, API, web và ngrok. Các địa chỉ mặc định:

- Web: `http://localhost:3000`
- Admin: `http://localhost:3001`
- API: `http://localhost:8000`
- MCP portal: `http://localhost:3000/mcp-connect`
- Ngrok inspector: `http://127.0.0.1:4040`

Có thể chạy từng phần để dễ xem log:

```powershell
# Cửa sổ 1: hạ tầng
docker compose -f docker-compose-local.yml up -d plane-db plane-redis plane-mq plane-minio

# Cửa sổ 2: API
cd apps/api
.\start-core.ps1

# Cửa sổ 3: web và admin
cd J:\plane
pnpm dev

# Cửa sổ 4: tunnel
cd J:\plane
.\start-ngrok.ps1
```

Nếu dùng domain ngrok khác, cập nhật domain trong `start-ngrok.ps1`, `apps/api/.env` và ô **Public Tunnel URL** trên portal.

## 5. Tạo Plane Personal API Key

1. Đăng nhập Plane bằng tài khoản chỉ có đúng quyền cần dùng.
2. Mở phần cài đặt hồ sơ và chọn **API Tokens**.
3. Tạo token có tên dễ nhận biết và thời hạn phù hợp.
4. Sao chép token ngay sau khi tạo; Plane không hiển thị lại token này.

Nên dùng tài khoản, workspace và project riêng cho demo hoặc thử nghiệm.

## 6. Tạo Personal MCP URL

1. Mở `http://localhost:3000/mcp-connect`.
2. Kiểm tra **Plane Server URL**.
3. Nhập workspace slug. Ví dụ URL workspace là `/acme/` thì slug là `acme`.
4. Dán Personal API Key.
5. Chọn **Test connection**.
6. Nhập URL HTTPS của ngrok/Cloudflare Tunnel vào **Public Tunnel URL**.
7. Chọn **Generate MCP connection**.
8. Sao chép **Personal MCP URL** từ dashboard.

Personal MCP URL là bearer credential: ai có URL này có thể thao tác với quyền của API key cho đến khi kết nối hết hạn hoặc bị thu hồi.

Để đổi hostname tunnel mà không đổi token, mở **Dashboard → Edit Public URL → Save**. Sau đó cập nhật URL trong MCP client.

## 7. Kết nối ChatGPT

Khả năng thêm MCP tùy chỉnh phụ thuộc gói ChatGPT, vai trò tài khoản và chính sách workspace.

1. Trong ChatGPT web, bật Developer mode tại **Settings → Apps → Advanced settings** nếu tùy chọn này xuất hiện.
2. Mở **Settings → Apps → Create**.
3. Dán Personal MCP URL.
4. Chọn **No authentication** vì credential đã nằm trong URL.
5. Chọn **Scan Tools**, kiểm tra danh sách tool rồi tạo app.
6. Mở cuộc trò chuyện mới và chọn app Plane trong menu tools.
7. Thử lệnh chỉ đọc trước, ví dụ: `Liệt kê các project Plane của tôi`.
8. Với thao tác ghi, kiểm tra lại workspace, project và nội dung trước khi xác nhận.

Nếu không có nút **Create**, dùng MCP Inspector hoặc MCP client khác để kiểm thử.

## 8. Kiểm thử và xác minh

Trên portal, phần **Tools** tải schema trực tiếp từ MCP registry. Nên thử theo thứ tự:

1. Liệt kê project.
2. Liệt kê work item của một project.
3. Tạo một work item thử nghiệm trong project dùng riêng cho demo.
4. Đọc lại work item vừa tạo.
5. Cập nhật state hoặc tạo child work item.
6. Xóa dữ liệu thử nghiệm sau khi hoàn tất.

Kiểm tra endpoint công khai bằng MCP client hoặc MCP Inspector. Một kết nối đúng phải hoàn thành `initialize` và trả về danh sách tool không rỗng từ `tools/list`.

Chạy kiểm tra mã nguồn trước khi phát hành:

```powershell
pnpm check

cd apps/api
uv run pytest plane/tests/unit/mcp/test_connections.py
uv run pytest plane/tests/unit/services/test_automation_runtime.py plane/tests/unit/services/test_workflow.py
```

## 9. Thu hồi hoặc tạo lại kết nối

- Chọn **Disconnect** để thu hồi kết nối hiện tại ngay lập tức.
- Chọn regenerate để tạo URL mới; URL cũ bị vô hiệu hóa.
- Xóa hoặc thu hồi Personal API Key trong Plane khi không còn sử dụng.
- Đổi Django `SECRET_KEY` sẽ làm các credential đã mã hóa không thể giải mã; cần tạo lại kết nối.

## 10. Xử lý lỗi thường gặp

### `Invalid Host header`

Thêm chính xác hostname tunnel vào `MCP_ALLOWED_HOSTS`, sau đó khởi động lại API.

### HTTP 403 khi MCP client kết nối

Thêm origin của client, ví dụ `https://chatgpt.com`, vào `MCP_ALLOWED_ORIGINS`. Không dùng dấu `/` ở cuối origin.

### Portal mở được nhưng Personal MCP URL không hoạt động

- Xác nhận ngrok đang trỏ tới `http://localhost:8000`.
- Xác nhận API được chạy bằng ASGI/Uvicorn qua `apps/api/start-core.ps1`.
- Dừng các tiến trình `manage.py runserver` cũ đang chiếm cổng 8000.
- Mở ngrok inspector tại `http://127.0.0.1:4040` để xem status và request.

### Đổi ngrok URL nhưng client vẫn dùng URL cũ

Cập nhật **Public Tunnel URL** trên dashboard, lưu lại, rồi thay server URL trong MCP client. Nếu dùng ngrok URL ngẫu nhiên, thao tác này phải làm lại sau mỗi lần tunnel đổi hostname.

### Migration hoặc API lỗi sau khi cập nhật code

```powershell
cd apps/api
uv sync
uv run --env-file .env python manage.py migrate
```

Kiểm tra log của API và các container bằng:

```powershell
docker compose -f docker-compose-local.yml ps
docker compose -f docker-compose-local.yml logs --tail=200 plane-db plane-redis plane-mq
```

## 11. Nguyên tắc an toàn

- Không commit API key, Personal MCP URL, ngrok authtoken hoặc `SECRET_KEY` thật.
- Không công khai PostgreSQL, Redis, RabbitMQ, MinIO hay cổng quản trị qua tunnel.
- Chỉ tunnel cổng API/reverse proxy cần thiết.
- Dùng token có thời hạn và quyền tối thiểu; thu hồi ngay khi không còn sử dụng.
