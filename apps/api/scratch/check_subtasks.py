import csv
from datetime import datetime

def analyze_csv(filepath):
    print(f"=== Analyzing {filepath} ===")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            subtasks = []
            all_issues = {}
            for row in reader:
                iid = row.get("Issue ID", "").strip()
                all_issues[iid] = row
                itype = row.get("Issue Type", "").strip()
                if itype.lower() in ["sub-task", "subtask"]:
                    subtasks.append(row)
    except Exception as e:
        print(f"Error opening {filepath}: {e}")
        return
        
    print(f"Total subtasks found: {len(subtasks)}")
    
    analyzed = []
    for s in subtasks:
        s_date_str = s.get("Start date", "").strip()
        d_date_str = s.get("Due date", "").strip()
        estimate = s.get("Original Estimate", "").strip()
        summary = s.get("Summary", "")
        issue_id = s.get("Issue ID", "")
        parent = s.get("Parent", "")
        parent_info = all_issues.get(parent, {})
        parent_summary = parent_info.get("Summary", "N/A")
        
        days = None
        s_dt = None
        d_dt = None
        if s_date_str and d_date_str:
            try:
                s_dt = datetime.strptime(s_date_str, "%d/%b/%y %I:%M %p")
                d_dt = datetime.strptime(d_date_str, "%d/%b/%y %I:%M %p")
                diff = d_dt - s_dt
                days = diff.total_seconds() / 86400.0
            except Exception:
                pass
                
        est_hours = float(estimate) / 3600.0 if estimate else 0.0
        
        analyzed.append({
            "id": issue_id,
            "parent": parent,
            "parent_summary": parent_summary,
            "summary": summary,
            "start": s_date_str,
            "due": d_date_str,
            "days": days,
            "est_hours": est_hours
        })
        
    # Sort by days descending
    with_days = [a for a in analyzed if a["days"] is not None]
    with_days.sort(key=lambda x: x["days"], reverse=True)
    
    print("\n--- Top subtasks with longest duration (days >= 3) ---")
    for a in with_days:
        if a["days"] >= 3.0:
            print(f"ID {a['id']} (Parent {a['parent']}: {a['parent_summary'][:30]}...)")
            print(f"   Summary: {a['summary']}")
            print(f"   Dates: {a['start']} -> {a['due']} ({a['days']:.1f} days) | Estimate: {a['est_hours']:.1f}h")
            print()

analyze_csv("apps/api/scratch/user_backlog.csv")
print("\n" + "="*60 + "\n")
analyze_csv("apps/api/scratch/user_full_backlog.csv")
