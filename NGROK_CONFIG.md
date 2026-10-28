# Ngrok Tunnel Configuration for Plane MCP

## Thông tin Tunnel

- **Tài khoản**: `vuhuy2901`
- **Ngrok Public URL**: `https://geopolitical-anthropomorphously-rosena.ngrok-free.dev`
- **Target Backend**: `http://localhost:8000`
- **Ngrok Web Interface**: [http://127.0.0.1:4040](http://127.0.0.1:4040)

## Các vị trí đã được lưu và cấu hình trong dự án:

1. **[apps/api/.env](file:///j:/plane/apps/api/.env)**:
   - `MCP_PUBLIC_BASE_URL="https://geopolitical-anthropomorphously-rosena.ngrok-free.dev"`
   - `MCP_ALLOWED_HOSTS`: đã thêm `geopolitical-anthropomorphously-rosena.ngrok-free.dev`
   - `MCP_ALLOWED_ORIGINS`: đã thêm `https://geopolitical-anthropomorphously-rosena.ngrok-free.dev`
   - `CORS_ALLOWED_ORIGINS`: đã thêm `https://geopolitical-anthropomorphously-rosena.ngrok-free.dev`

2. **[apps/web/app/mcp-connect/page.tsx](file:///j:/plane/apps/web/app/mcp-connect/page.tsx)**:
   - Giá trị mặc định của `Public Tunnel URL` và placeholder trên giao diện portal MCP đã được điền sẵn link ngrok này.

3. **[start-ngrok.ps1](file:///j:/plane/start-ngrok.ps1)**:
   - Script chạy ngrok chỉ với 1 cú click:
     ```powershell
     .\start-ngrok.ps1
     ```

## URL MCP để kết nối AI Client (ChatGPT, Remote Agents, ...):

- **Endpoint chung**: `https://geopolitical-anthropomorphously-rosena.ngrok-free.dev/mcp/`
- **Personal MCP URL**: Xem và lấy trực tiếp từ trang portal: [http://localhost:3000/mcp-connect](http://localhost:3000/mcp-connect)
