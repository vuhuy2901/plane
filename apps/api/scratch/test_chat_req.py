import requests
import json

csv_sample = """Issue ID,Parent,Issue Type,Summary,Description,Start date,Due date,Original Estimate,Priority,Labels,Labels,Labels
1000,,Epic,Khởi tạo dự án,"Epic 0: thống nhất mục tiêu, phạm vi MVP, bên liên quan, backlog, kiến trúc và chuẩn bị Jira/Git/môi trường Dev/Test. Hoàn tất trước khi bắt đầu phát triển tính năng.",04/Jan/27 9:00 AM,08/Jan/27 5:00 PM,,High,module-ecommerce,epic-khoi-tao,
2101,1000,Task,Kick-off dự án và xác định phạm vi MVP,"PM thống nhất mục tiêu, KPI thành công, phạm vi in/out, vai trò, rủi ro, kế hoạch truyền thông và biên bản kick-off.",04/Jan/27 9:00 AM,05/Jan/27 5:00 PM,,High,module-ecommerce,,
40001,2101,Sub-task,PM — Kick-off và thống nhất stakeholder,"Biên bản họp, RACI, kế hoạch phối hợp và mốc bàn giao.",04/Jan/27 9:00 AM,04/Jan/27 5:00 PM,21600,Medium,module-ecommerce,role-pm,
1001,,Epic,"Tài khoản, phân quyền và khách hàng","Epic theo module nghiệp vụ. Hoàn thành khi mọi Task con DONE; QA đạt; không còn Bug nghiêm trọng chặn; PM phê duyệt.",11/Jan/27 9:00 AM,17/Feb/27 5:00 PM,,High,module-ecommerce,epic-tai-khoan,
"""

res = requests.post("http://127.0.0.1:6274/api/chat", json={"message": "Tôi muốn import file này:\n" + csv_sample})
print("Status:", res.status_code)
data = res.json()
print("Reply:\n", data.get("reply"))
print("Actions:\n", json.dumps(data.get("actions"), indent=2, ensure_ascii=False))
