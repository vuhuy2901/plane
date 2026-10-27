import os
import sys
import datetime

sys.path.insert(0, "/code")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.local")
import django
django.setup()

from plane.db.models import Issue, Project

print("=================================================================")
print("KIỂM TRA TOÀN BỘ SUBTASK TRONG DATABASE")
print("=================================================================")

subtasks = Issue.objects.filter(parent__isnull=False).select_related('parent')
total_subtasks = subtasks.count()
print(f"Tổng số subtask: {total_subtasks}")

results = []

for s in subtasks:
    parent = s.parent
    if not s.start_date or not s.target_date:
        continue
    
    cal_days = (s.target_date - s.start_date).days
    
    # Tính số ngày làm việc (không tính T7, CN)
    cur = s.start_date
    work_days = 0
    while cur <= s.target_date:
        if cur.weekday() < 5: # Thứ 2 - Thứ 6
            work_days += 1
        cur += datetime.timedelta(days=1)
        
    issues_found = []
    
    # 1. Quá dài: >= 7 ngày lịch hoặc >= 5 ngày làm việc (1 tuần)
    if cal_days >= 7:
        issues_found.append(f"Kéo dài >= 7 ngày lịch ({cal_days} ngày, {work_days} ngày làm việc)")
    elif cal_days >= 5:
        issues_found.append(f"Kéo dài 5-6 ngày lịch ({cal_days} ngày, {work_days} ngày làm việc)")
        
    # 2. Vượt quá ngày của Task cha
    if parent and parent.start_date and parent.target_date:
        if s.start_date < parent.start_date:
            issues_found.append(f"Start date ({s.start_date}) sớm hơn Task cha ({parent.start_date})")
        if s.target_date > parent.target_date:
            issues_found.append(f"Due date ({s.target_date}) trễ hơn Task cha ({parent.target_date})")
            
    if issues_found:
        results.append({
            "id": s.sequence_id,
            "name": s.name,
            "start": s.start_date,
            "target": s.target_date,
            "cal_days": cal_days,
            "work_days": work_days,
            "parent_id": parent.sequence_id if parent else None,
            "parent_name": parent.name if parent else None,
            "issues": issues_found
        })

print(f"\nSố lượng subtask có dấu hiệu bất thường về thời gian: {len(results)}")

ge_7_days = [r for r in results if r["cal_days"] >= 7]
d5_to_6 = [r for r in results if 5 <= r["cal_days"] < 7]

print(f"\n1. Subtask kéo dài TỪ 1 TUẦN TRỞ LÊN (>= 7 ngày lịch): {len(ge_7_days)} subtask")
for r in ge_7_days:
    print(f"  - [#{r['id']}] {r['name']}")
    print(f"      Thời gian: {r['start']} -> {r['target']} ({r['cal_days']} ngày lịch | {r['work_days']} ngày làm việc)")
    print(f"      Thuộc Task cha: [#{r['parent_id']}] {r['parent_name']}")
    print(f"      Vấn đề: {'; '.join(r['issues'])}\n")

print(f"\n2. Subtask kéo dài 5 - 6 ngày lịch (tương đương 1 tuần làm việc): {len(d5_to_6)} subtask")
for r in d5_to_6:
    print(f"  - [#{r['id']}] {r['name']}")
    print(f"      Thời gian: {r['start']} -> {r['target']} ({r['cal_days']} ngày lịch | {r['work_days']} ngày làm việc)")
    print(f"      Thuộc Task cha: [#{r['parent_id']}] {r['parent_name']}")
    print(f"      Vấn đề: {'; '.join(r['issues'])}\n")
