import csv
from datetime import datetime, timedelta

with open('apps/api/scratch/user_full_backlog.csv', 'r', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

# Group subtasks by role
roles = {
    'PM': [],
    'BA': [],
    'Backend': [],
    'Frontend': [],
    'Tester': [],
    'DevOps': []
}

for r in rows:
    summary = r.get('Summary', '')
    s_str = r.get('Start date', '')
    d_str = r.get('Due date', '')
    iid = r.get('Issue ID', '')
    if not s_str or not d_str:
        continue
    try:
        s_dt = datetime.strptime(s_str, '%d/%b/%y %I:%M %p')
        d_dt = datetime.strptime(d_str, '%d/%b/%y %I:%M %p')
    except:
        continue
        
    for role in roles:
        if summary.startswith(f'{role} —') or summary.startswith(f'{role} -'):
            roles[role].append({
                'id': iid,
                'summary': summary,
                'start': s_dt,
                'due': d_dt
            })
            break

def get_working_days_gap(d1, d2):
    # d1 is due date, d2 is next start date
    # count working days strictly between d1.date() and d2.date()
    cur = d1.date() + timedelta(days=1)
    target = d2.date()
    count = 0
    while cur < target:
        if cur.weekday() < 5:
            count += 1
        cur += timedelta(days=1)
    return count

print("=== KIỂM TRA TÍNH LIÊN TỤC & KHOẢNG NGHỈ GIỮA CÁC TASK CỦA TỪNG VAI TRÒ ===\n")

for role, items in roles.items():
    items.sort(key=lambda x: (x['start'], x['due']))
    print(f"*** VAI TRÒ: {role} (Tổng cộng: {len(items)} sub-tasks) ***")
    if not items:
        print("   Không có task nào.\n")
        continue
        
    start_fmt = items[0]['start'].strftime("%d/%b/%Y")
    due_fmt = items[-1]['due'].strftime("%d/%b/%Y")
    print(f"   Thời gian toàn dự án: {start_fmt} -> {due_fmt}")
    
    # Calculate coverage and overlaps / gaps
    # To check day-by-day:
    min_date = items[0]['start'].date()
    max_date = items[-1]['due'].date()
    
    # Build list of working days
    work_days = []
    cur = min_date
    while cur <= max_date:
        if cur.weekday() < 5:
            work_days.append(cur)
        cur += timedelta(days=1)
        
    idle_days = []
    for wd in work_days:
        active = False
        for it in items:
            if it['start'].date() <= wd <= it['due'].date():
                active = True
                break
        if not active:
            idle_days.append(wd)
            
    print(f"   Tổng số ngày làm việc trong dự án: {len(work_days)} ngày")
    print(f"   Số ngày BỊ NGHỈ (không có task nào): {len(idle_days)} ngày")
    
    # Check individual gaps
    gaps = []
    for i in range(len(items) - 1):
        cur_task = items[i]
        next_task = items[i+1]
        
        if next_task['start'].date() > cur_task['due'].date() + timedelta(days=1):
            w_gap = get_working_days_gap(cur_task['due'], next_task['start'])
            if w_gap > 0:
                gaps.append((cur_task, next_task, w_gap))
                
    if gaps:
        print(f"   Chi tiết các khoảng nghỉ ({len(gaps)} khoảng trống):")
        for cur_t, next_t, w_gap in gaps[:8]:
            d1_str = cur_t['due'].strftime('%d/%b')
            d2_str = next_t['start'].strftime('%d/%b')
            print(f"      • Nghỉ {w_gap} ngày làm việc (từ {d1_str} đến {d2_str})")
            print(f"        Task trước [{cur_t['id']}]: {cur_t['summary'][:45]}")
            print(f"        Task sau   [{next_t['id']}]: {next_t['summary'][:45]}")
        if len(gaps) > 8:
            print(f"      ... và còn {len(gaps) - 8} khoảng nghỉ khác.")
    else:
        print("   -> Không có khoảng nghỉ nào giữa các task liên tiếp!")
        
    print()
