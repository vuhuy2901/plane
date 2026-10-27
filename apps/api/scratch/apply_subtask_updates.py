import os
import sys
import csv
from datetime import datetime, timedelta

# Helper date functions
def add_business_days(start_date, num_days):
    cur = start_date
    added = 1
    while added < num_days:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            added += 1
    return cur

def next_business_day(cur):
    while True:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            return cur

# Complexity map: (be_days, fe_days, label)
COMPLEXITY = {
    '2001': (4, 3, "Nặng: JWT, Auth, Security"),
    '2002': (3, 2, "Vừa: RBAC, Phân quyền"),
    '2003': (2, 2, "Nhẹ: Profile, Đổi mật khẩu"),
    '2004': (2, 2, "Nhẹ: Sổ địa chỉ giao hàng"),
    '2005': (3, 2, "Vừa: Chat support trực tuyến"),
    '2006': (2, 2, "Nhẹ: Danh mục sản phẩm"),
    '2007': (4, 3, "Nặng: SKU variations, Barcode, Giá"),
    '2008': (2, 2, "Nhẹ: Thư viện ảnh sản phẩm"),
    '2009': (3, 2, "Vừa: Tìm kiếm & Lọc sản phẩm"),
    '2010': (2, 2, "Nhẹ: Chi tiết & gợi ý sản phẩm"),
    '2011': (2, 2, "Nhẹ: Đánh giá & nhận xét"),
    '2012': (2, 2, "Nhẹ: Danh mục kho vật lý"),
    '2013': (4, 3, "Nặng: Phiếu nhập & cập nhật tồn kho"),
    '2014': (4, 3, "Nặng: Phiếu xuất & kiểm soát khả dụng"),
    '2015': (3, 2, "Vừa: Sổ kho & cảnh báo tồn thấp"),
    '2016': (3, 2, "Vừa: Giỏ hàng & đồng bộ số lượng"),
    '2017': (3, 2, "Vừa: Tính tiền, thuế & phí ship"),
    '2018': (3, 2, "Vừa: Mã giảm giá & promotion"),
    '2019': (4, 3, "Nặng: Tạo đơn, lock tồn chống bán vượt"),
    '2020': (4, 3, "Nặng: Cổng thanh toán COD, Chuyển khoản"),
    '2021': (3, 2, "Vừa: State machine đơn hàng"),
    '2022': (3, 2, "Vừa: Hủy đơn, hoàn tồn, hoàn tiền"),
    '2023': (2, 2, "Nhẹ: Email thông báo đơn hàng"),
    '2024': (3, 3, "Vừa: Dashboard doanh thu & metrics"),
    '2025': (4, 3, "Nặng: Báo cáo tài chính & đối soát"),
    '2026': (3, 2, "Vừa: Báo cáo tồn & sản phẩm bán chạy"),
}

# 1. Update CSV files
def update_csv_file(filepath):
    print(f"\n--- Cập nhật file {filepath} ---")
    if not os.path.exists(filepath):
        print(f"File {filepath} không tồn tại!")
        return {}

    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    tasks = {}
    for r in rows:
        itype = r.get('Issue Type', '').strip()
        if itype.lower() == 'task':
            tasks[r['Issue ID'].strip()] = r

    updated_count = 0
    updated_map = {} # issue_id -> (start_dt, due_dt, estimate_sec, days)

    for r in rows:
        pid = r.get('Parent', '').strip()
        summary = r.get('Summary', '')
        iid = r.get('Issue ID', '').strip()

        if pid in COMPLEXITY and pid in tasks:
            be_d, fe_d, _ = COMPLEXITY[pid]
            p_task = tasks[pid]
            p_s = datetime.strptime(p_task['Start date'], '%d/%b/%y %I:%M %p')

            is_be = 'Backend' in summary or 'BE' in summary or iid.endswith('3')
            is_fe = 'Frontend' in summary or 'FE' in summary or iid.endswith('4')

            if is_be:
                days = be_d
                est_sec = days * 8 * 3600
                s_dt = next_business_day(p_s).replace(hour=9, minute=0)
                d_dt = add_business_days(s_dt, days).replace(hour=17, minute=0)
                r['Start date'] = s_dt.strftime('%d/%b/%y %I:%M %p')
                r['Due date'] = d_dt.strftime('%d/%b/%y %I:%M %p')
                r['Original Estimate'] = str(est_sec)
                updated_count += 1
                updated_map[summary] = (s_dt, d_dt, days, est_sec)
            elif is_fe:
                days = fe_d
                est_sec = days * 8 * 3600
                if be_d > fe_d:
                    s_dt = next_business_day(next_business_day(p_s)).replace(hour=9, minute=0)
                else:
                    s_dt = next_business_day(p_s).replace(hour=9, minute=0)
                d_dt = add_business_days(s_dt, days).replace(hour=17, minute=0)
                r['Start date'] = s_dt.strftime('%d/%b/%y %I:%M %p')
                r['Due date'] = d_dt.strftime('%d/%b/%y %I:%M %p')
                r['Original Estimate'] = str(est_sec)
                updated_count += 1
                updated_map[summary] = (s_dt, d_dt, days, est_sec)

    with open(filepath, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Đã cập nhật {updated_count} subtasks trong {filepath}")
    return updated_map

scratch_dir = os.path.dirname(os.path.abspath(__file__))
up_map = update_csv_file(os.path.join(scratch_dir, 'user_full_backlog.csv'))
update_csv_file(os.path.join(scratch_dir, 'user_backlog.csv'))

# 2. Update Database via Django ORM
print("\n--- Cập nhật Database Plane ---")
sys.path.insert(0, '/code')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plane.settings.local')
try:
    import django
    django.setup()
    from plane.db.models import Issue, Project

    project = Project.objects.filter(identifier='QLDP').first()
    if not project:
        project = Project.objects.first()
    print(f"Target Project: {project.name} ({project.identifier})")

    db_updated = 0
    for summary, (s_dt, d_dt, days, est_sec) in up_map.items():
        # Match issue in project by name
        issues = Issue.objects.filter(project=project, name=summary)
        for iss in issues:
            iss.start_date = s_dt.date()
            iss.target_date = d_dt.date()
            iss.save(update_fields=['start_date', 'target_date'])
            db_updated += 1

    print(f"Đã cập nhật thành công {db_updated} subtasks trong Database Plane!")

except Exception as e:
    print(f"DB update error: {e}")
