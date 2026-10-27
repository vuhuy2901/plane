import csv
from datetime import datetime, timedelta

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

# Complexity map: (be_days, fe_days)
# Rule: be_days >= fe_days, both in [2, 4]
COMPLEXITY = {
    '2001': (4, 3, "Nặng (Heavy: JWT, Auth, Security)"),
    '2002': (3, 2, "Vừa (Medium: RBAC, Phân quyền)"),
    '2003': (2, 2, "Nhẹ (Light: Profile, Đổi mật khẩu)"),
    '2004': (2, 2, "Nhẹ (Light: Sổ địa chỉ giao hàng)"),
    '2005': (3, 2, "Vừa (Medium: Chat support trực tuyến)"),
    '2006': (2, 2, "Nhẹ (Light: Danh mục sản phẩm)"),
    '2007': (4, 3, "Nặng (Heavy: SKU variations, Barcode, Giá)"),
    '2008': (2, 2, "Nhẹ (Light: Thư viện ảnh sản phẩm)"),
    '2009': (3, 2, "Vừa (Medium: Tìm kiếm & Lọc sản phẩm)"),
    '2010': (2, 2, "Nhẹ (Light: Chi tiết & gợi ý sản phẩm)"),
    '2011': (2, 2, "Nhẹ (Light: Đánh giá & nhận xét)"),
    '2012': (2, 2, "Nhẹ (Light: Danh mục kho vật lý)"),
    '2013': (4, 3, "Nặng (Heavy: Phiếu nhập & cập nhật tồn kho)"),
    '2014': (4, 3, "Nặng (Heavy: Phiếu xuất & kiểm soát khả dụng)"),
    '2015': (3, 2, "Vừa (Medium: Sổ kho & cảnh báo tồn thấp)"),
    '2016': (3, 2, "Vừa (Medium: Giỏ hàng & đồng bộ số lượng)"),
    '2017': (3, 2, "Vừa (Medium: Tính tiền, thuế & phí ship)"),
    '2018': (3, 2, "Vừa (Medium: Mã giảm giá & promotion)"),
    '2019': (4, 3, "Nặng (Heavy: Tạo đơn, lock tồn chống bán vượt)"),
    '2020': (4, 3, "Nặng (Heavy: Cổng thanh toán COD, Chuyển khoản)"),
    '2021': (3, 2, "Vừa (Medium: State machine đơn hàng)"),
    '2022': (3, 2, "Vừa (Medium: Hủy đơn, hoàn tồn, hoàn tiền)"),
    '2023': (2, 2, "Nhẹ (Light: Email thông báo đơn hàng)"),
    '2024': (3, 3, "Vừa (Medium: Dashboard doanh thu & metrics)"),
    '2025': (4, 3, "Nặng (Heavy: Báo cáo tài chính & đối soát)"),
    '2026': (3, 2, "Vừa (Medium: Báo cáo tồn & sản phẩm bán chạy)"),
}

with open('apps/api/scratch/user_full_backlog.csv', 'r', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

tasks = {}
for r in rows:
    itype = r.get('Issue Type', '').strip()
    iid = r.get('Issue ID', '').strip()
    if itype.lower() == 'task':
        tasks[iid] = r

print("=== KIỂM TRA LỊCH TRÌNH 26 TÍNH NĂNG (BACKEND >= FRONTEND, 2-4 NGÀY) ===")
all_ok = True
for tid, (be_d, fe_d, note) in COMPLEXITY.items():
    t = tasks[tid]
    p_s = datetime.strptime(t['Start date'], '%d/%b/%y %I:%M %p')
    p_d = datetime.strptime(t['Due date'], '%d/%b/%y %I:%M %p')
    
    # BE starts on day 2 of parent task
    be_start = next_business_day(p_s).replace(hour=9, minute=0)
    be_due = add_business_days(be_start, be_d).replace(hour=17, minute=0)
    
    # FE starts on day 2 or day 3
    # If BE is 4 days and FE is 3 days: FE starts day 3, ends day 5 (or starts day 2, ends day 4)
    # Let's start FE on day 2 (mock API) or day 3:
    # Starting FE on day 3 (or day 2 for lighter tasks):
    if be_d > fe_d:
        fe_start = next_business_day(be_start).replace(hour=9, minute=0)
    else:
        fe_start = be_start
    fe_due = add_business_days(fe_start, fe_d).replace(hour=17, minute=0)
    
    # Check within parent
    if be_due > p_d or fe_due > p_d:
        print(f"LỖI: Task {tid} vượt quá ngày Task cha ({p_d})")
        all_ok = False
        
    print(f"[{tid}] {t['Summary'][:35]} | {note}")
    print(f"   Parent: {p_s.strftime('%d/%b')} -> {p_d.strftime('%d/%b')}")
    print(f"   BE ({be_d} ngày): {be_start.strftime('%d/%b')} -> {be_due.strftime('%d/%b')} ({be_d*8}h)")
    print(f"   FE ({fe_d} ngày): {fe_start.strftime('%d/%b')} -> {fe_due.strftime('%d/%b')} ({fe_d*8}h)")
    print()

if all_ok:
    print(">>> TẤT CẢ 26 TÍNH NĂNG ĐỀU KHỚP HOÀN TOÀN VÀ NẰM GỌN TRONG TASK CHA! <<<")
