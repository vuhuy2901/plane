# Plane Docker Data Backup & Pre-seeded Dataset

Thư mục này chứa file dữ liệu cơ sở dữ liệu (dataset/seed) và các script tự động sao lưu/phục hồi cho dự án Plane chạy qua Docker.

## 📦 Dataset có sẵn trong kho lưu trữ

File seed: `backups/plane_database_backup.sql` (~4.8 MB, UTF-8 clean dump)
Bao gồm:

- **7 Users** (Các tài khoản trong nhóm như `quang.pm@local.test`, `tu.tester@local.test`, `nghi.fe@local.test`, `nam.ba@local.test`... - mật khẩu xem tại [LOCAL_TEAM_ACCOUNTS.txt](../LOCAL_TEAM_ACCOUNTS.txt))
- **2 Workspaces** (`qldapm`, `qlda`)
- **5 Projects** (`QLDAPM-Final`, `Quản lí dự án`, `Hệ thống ECommerce`, `Bán Hàng`, `QLDA`)
- **391 Issues / Work Items**, chu kỳ (Cycles), Modules, Views, Labels, States...

---

## 🚀 Tự động phục hồi dữ liệu (Restore / Seed)

### Dành cho AI Agent / Linux / macOS:

```bash
bash backups/restore_docker_data.sh
# Hoặc chạy lệnh pnpm:
pnpm db:restore
```

### Dành cho Windows (PowerShell):

```powershell
.\backups\restore_docker_data.ps1
# Hoặc:
pnpm db:restore
```

Script sẽ tự động:

1. Đảm bảo container `plane-db` được bật và sẵn sàng.
2. Nạp toàn bộ dữ liệu từ `backups/plane_database_backup.sql` vào database `plane`.
3. Khôi phục đầy đủ toàn bộ workspace, project, user và issue.

---

## 💾 Sao lưu dữ liệu mới (Backup)

Khi có thêm dữ liệu mới muốn cập nhật lại vào Git:

- **Windows**: `.\backups\backup_docker_data.ps1`
- **Linux/macOS**: `bash backups/backup_docker_data.sh`
- **pnpm**: `pnpm db:backup`
  Sau khi chạy xong, commit và push file `backups/plane_database_backup.sql` lên Git.
