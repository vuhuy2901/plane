import csv
from datetime import datetime, timedelta

with open('apps/api/scratch/user_full_backlog.csv', 'r', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

tasks = [r for r in rows if r['Issue Type'] == 'Task' and r['Issue ID'].startswith('20')]
tasks.sort(key=lambda x: datetime.strptime(x['Start date'], '%d/%b/%y %I:%M %p'))

print(f"Tổng số Task tính năng: {len(tasks)}")
for t in tasks:
    iid = t['Issue ID']
    s = t['Start date'].split()[0]
    d = t['Due date'].split()[0]
    print(f"[{iid}] ({s} -> {d}): {t['Summary'][:45]}")
