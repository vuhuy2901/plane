# Plane Docker Data Backup & Restore

Thư mục này chứa các script sao lưu và phục hồi dữ liệu cơ sở dữ liệu PostgreSQL cho dự án Plane trong môi trường Docker.

## 1. Sao lưu dữ liệu (Backup)
Khi Docker Desktop đang chạy:
```powershell
.\backups\backup_docker_data.ps1
```
Script sẽ khởi động container database và xuất toàn bộ schema + data ra file `backups/plane_database_backup.sql`.

## 2. Phục hồi dữ liệu (Restore)
Khi chuyển sang máy mới hoặc cài đặt lại môi trường:
```powershell
.\backups\restore_docker_data.ps1
```
Script sẽ nạp lại toàn bộ dữ liệu vào container `plane-db`.

## 3. Khởi động toàn bộ môi trường Docker
```powershell
docker compose -f docker-compose-local.yml up -d
```
