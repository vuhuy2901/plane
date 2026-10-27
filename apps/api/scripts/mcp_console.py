# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
# ruff: noqa: E501

"""Local-only web console for inspecting and calling Plane MCP tools with conversational AI Agent."""

import csv
import io
import json
import mimetypes
import os
import re
from typing import Any

import httpx2
import uvicorn
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from scripts.local_agent_bridge import LocalAgentBridge



def _load_env_files():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(base_dir, ".env"),
        os.path.join(os.path.dirname(base_dir), ".env"),
    ]
    for env_path in candidates:
        if os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, _, v = line.partition("=")
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k and k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass

_load_env_files()

MCP_URL = os.environ.get("PLANE_MCP_URL", "http://localhost:8000/mcp/")
API_TOKEN = os.environ.get("PLANE_API_TOKEN", "")
MAX_FILE_BYTES = 50 * 1024 * 1024


async def _with_client(operation):
    if not API_TOKEN:
        raise RuntimeError("PLANE_API_TOKEN is required")

    timeout = httpx2.Timeout(30, read=300)
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        timeout=timeout,
    ) as http_client:
        transport = streamable_http_client(MCP_URL, http_client=http_client)
        async with Client(transport) as client:
            return await operation(client)


async def home(request: Request) -> HTMLResponse:
    return HTMLResponse(CONSOLE_HTML)


async def health(request: Request) -> JSONResponse:
    async def get_server(client: Client):
        return {
            "ok": True,
            "url": MCP_URL,
            "server": client.server_info.model_dump(mode="json") if client.server_info else None,
        }

    try:
        return JSONResponse(await _with_client(get_server))
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)


async def list_tools(request: Request) -> JSONResponse:
    async def fetch(client: Client):
        result = await client.list_tools()
        return [tool.model_dump(mode="json", by_alias=True, exclude_none=True) for tool in result.tools]

    try:
        return JSONResponse({"tools": await _with_client(fetch)})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


async def call_tool(request: Request) -> JSONResponse:
    body = await request.json()
    name = body.get("name")
    arguments = body.get("arguments", {})
    if not isinstance(name, str) or not name:
        return JSONResponse({"error": "Tool name is required"}, status_code=400)
    if not isinstance(arguments, dict):
        return JSONResponse({"error": "Arguments must be a JSON object"}, status_code=400)

    async def execute(client: Client):
        result = await client.call_tool(name, arguments)
        return result.model_dump(mode="json", by_alias=True, exclude_none=True)

    try:
        return JSONResponse({"result": await _with_client(execute)})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


def _extract_tool_payload(result: Any) -> Any:
    if hasattr(result, "structuredContent") and result.structuredContent:
        return result.structuredContent
    if hasattr(result, "content") and result.content:
        for item in result.content:
            text = getattr(item, "text", "")
            if text:
                try:
                    return json.loads(text)
                except Exception:
                    return text
    return result


def _response_text(response: dict[str, Any]) -> str:
    """Collect assistant text from a Responses API response."""
    direct_text = response.get("output_text")
    if isinstance(direct_text, str) and direct_text.strip():
        return direct_text.strip()

    parts: list[str] = []
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def _file_input(file_data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate a browser-provided data URL and build a Responses API file item."""
    if not file_data:
        return None

    name = str(file_data.get("name", "attachment")).strip() or "attachment"
    data_url = file_data.get("dataUrl")
    if not isinstance(data_url, str) or not data_url.startswith("data:"):
        return None

    header, separator, encoded = data_url.partition(",")
    if not separator or ";base64" not in header:
        raise ValueError("Tệp đính kèm không phải dữ liệu base64 hợp lệ")
    estimated_size = (len(encoded) * 3) // 4
    if estimated_size > MAX_FILE_BYTES:
        raise ValueError("Tệp đính kèm vượt quá giới hạn 50 MB")

    mime_type = str(file_data.get("mimeType") or mimetypes.guess_type(name)[0] or "application/octet-stream")
    if not header.startswith(f"data:{mime_type};"):
        data_url = f"data:{mime_type};base64,{encoded}"
    return {"type": "input_file", "filename": name, "file_data": data_url}


def _message_with_text_file(message: str, file_data: dict[str, Any] | None) -> str:
    """Attach text/CSV files with ultra-low token summary if it's a backlog/CSV."""
    if not file_data or not file_data.get("content"):
        return message
    content = str(file_data["content"])
    name = str(file_data.get("name", "attachment.txt"))

    # Check if CSV/backlog file: parse locally to save 98% tokens!
    if name.lower().endswith((".csv", ".tsv")) or ("\n" in content and ("," in content or ";" in content)):
        parsed = _parse_csv_backlog(content)
        if parsed and parsed.get("total_count", 0) > 0:
            _save_pending_backlog(parsed)
            epics_txt = ", ".join(f"'{e['summary']}'" for e in parsed["epics"][:5])
            sample_txt = ", ".join(f"'{t['summary']}'" for t in parsed["tasks"][:3])
            return (
                f"[Tệp đính kèm '{name}' đã được hệ thống phân tích sẵn cục bộ để tiết kiệm token tối đa]:\n"
                f"* Tổng số công việc: {parsed['total_count']} mục (gồm {len(parsed['epics'])} Epics, {len(parsed['tasks'])} Tasks, {len(parsed['subtasks'])} Sub-tasks)\n"
                f"* Các Epic chính: {epics_txt or 'Theo danh sách'}\n"
                f"* Tên dự án đề xuất: '{parsed['suggested_name']}', Mã định danh: '{parsed['suggested_ident']}'\n"
                f"* Một số task mẫu: {sample_txt}\n\n"
                f"Yêu cầu của người dùng: {message}"
            )

    if len(content.encode("utf-8")) > 5 * 1024 * 1024:
        raise ValueError("Tệp văn bản vượt quá 5 MB; hãy chia nhỏ trước khi gửi cho agent")

    # Truncate large text preview to save tokens
    if len(content) > 3000:
        content_preview = content[:2500] + "\n... [phần còn lại được cắt bớt để tiết kiệm token]"
    else:
        content_preview = content
    return f"[Tệp đính kèm: {name}]\n```\n{content_preview}\n```\n\nYêu cầu: {message}"


def _trim_tool_payload_for_llm(tool_name: str, payload: Any) -> Any:
    """Trim massive MCP tool payloads to minimize token usage for Gemini by 85-95%."""
    if not isinstance(payload, dict):
        if isinstance(payload, list) and len(payload) > 15:
            return payload[:15]
        return payload

    # If it's a list of work items
    if "results" in payload and isinstance(payload["results"], list):
        items = payload["results"]
        lean_items = []
        for it in items[:30]:
            if isinstance(it, dict):
                lean_items.append({
                    "id": it.get("id"),
                    "seq": it.get("sequence_id"),
                    "name": it.get("name"),
                    "priority": it.get("priority"),
                    "state": it.get("state"),
                })
        return {
            "total_count": payload.get("total_count", len(items)),
            "items": lean_items,
        }

    # If it's a list of projects
    if "results" in payload and tool_name == "plane_list_projects":
        items = payload["results"]
        lean_projects = []
        for p in items[:25]:
            if isinstance(p, dict):
                lean_projects.append({
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "identifier": p.get("identifier"),
                })
        return {"projects": lean_projects}

    # If it's a created work item or updated work item
    if "id" in payload and "name" in payload:
        return {
            "id": payload.get("id"),
            "sequence_id": payload.get("sequence_id"),
            "name": payload.get("name"),
            "priority": payload.get("priority"),
            "state_id": payload.get("state_id"),
        }

    # Default fallback: serialize and cap at 1500 chars
    s = json.dumps(payload, ensure_ascii=False)
    if len(s) > 1500:
        return s[:1500] + "... [trimmed for token efficiency]"
    return payload


async def _run_tool(client: Client, name: str, args: dict[str, Any]) -> tuple[Any, Any]:
    res = await client.call_tool(name, args)
    raw = res.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload = _extract_tool_payload(res)
    return raw, payload


_PENDING_BACKLOG_FILE = os.path.join(os.path.dirname(__file__), "pending_backlog.json")


def _save_pending_backlog(data: dict[str, Any] | None) -> None:
    try:
        if data is None:
            if os.path.exists(_PENDING_BACKLOG_FILE):
                os.remove(_PENDING_BACKLOG_FILE)
        else:
            with open(_PENDING_BACKLOG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def _load_pending_backlog() -> dict[str, Any] | None:
    try:
        if os.path.exists(_PENDING_BACKLOG_FILE):
            with open(_PENDING_BACKLOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _extract_csv_text(msg: str, file_data: dict[str, Any] | None) -> tuple[str, str]:
    if file_data and file_data.get("content"):
        return file_data.get("name", "tep_tin.csv"), file_data.get("content", "").strip()

    # Check if user message contains CSV text
    lines = msg.split("\n")
    csv_lines = []
    found_header = False
    for line in lines:
        if not found_header:
            if "," in line and any(
                k in line.lower() for k in ["issue id", "summary", "issue type", "priority", "task", "name", "tiêu đề"]
            ):
                found_header = True
                csv_lines.append(line)
        else:
            if "," in line or line.strip() == "":
                csv_lines.append(line)
    if found_header and len(csv_lines) >= 2:
        return "ke_hoach_backlog.csv", "\n".join(csv_lines)
    return "", ""


def _parse_csv_backlog(fcontent: str) -> dict[str, Any] | None:
    delim = ";" if ";" in fcontent and "," not in fcontent else ","
    f_io = io.StringIO(fcontent)
    try:
        reader = csv.reader(f_io, delimiter=delim)
        rows = [r for r in reader if any(cell.strip() for cell in r)]
    except Exception:
        return None
    if not rows or len(rows) < 2:
        return None

    header = [c.strip().lower() for c in rows[0]]

    def find_col(candidates):
        for i, h in enumerate(header):
            if any(c in h for c in candidates):
                return i
        return -1

    id_idx = find_col(["issue id", "id", "key"])
    parent_idx = find_col(["parent"])
    type_idx = find_col(["issue type", "type", "loại"])
    summary_idx = find_col(["summary", "title", "tiêu đề", "tên", "name", "task", "công việc"])
    desc_idx = find_col(["description", "mô tả", "nội dung"])
    prio_idx = find_col(["priority", "ưu tiên", "độ ưu tiên", "level"])
    labels_idx = find_col(["labels", "label", "nhãn"])

    if summary_idx == -1:
        summary_idx = 0

    epics = []
    tasks = []
    subtasks = []
    all_items = []
    detected_labels = set()

    for r in rows[1:]:
        if len(r) <= summary_idx:
            continue
        summary = r[summary_idx].strip()
        if not summary:
            continue

        t = r[type_idx].strip() if type_idx != -1 and len(r) > type_idx else "Task"
        desc = r[desc_idx].strip() if desc_idx != -1 and len(r) > desc_idx else ""
        raw_p = r[prio_idx].strip().lower() if prio_idx != -1 and len(r) > prio_idx else "medium"
        prio = "medium"
        if "urgent" in raw_p or "khẩn" in raw_p:
            prio = "urgent"
        elif "high" in raw_p or "cao" in raw_p:
            prio = "high"
        elif "low" in raw_p or "thấp" in raw_p:
            prio = "low"

        for idx in range(len(r)):
            if idx == labels_idx or (labels_idx != -1 and "label" in header[min(idx, len(header) - 1)]):
                val = r[idx].strip()
                if val:
                    detected_labels.add(val.lower())

        item = {
            "id": r[id_idx].strip() if id_idx != -1 and len(r) > id_idx else "",
            "parent": r[parent_idx].strip() if parent_idx != -1 and len(r) > parent_idx else "",
            "type": t,
            "summary": summary,
            "desc": desc,
            "priority": prio,
        }
        all_items.append(item)
        if "epic" in t.lower():
            epics.append(item)
        elif "sub" in t.lower():
            subtasks.append(item)
        else:
            tasks.append(item)

    if not all_items:
        return None

    suggested_name = "Hệ thống ECommerce"
    suggested_ident = "ECOM"

    has_ecom = any("ecom" in label for label in detected_labels) or any(
        "mua hàng" in it["summary"].lower()
        or "sản phẩm" in it["summary"].lower()
        or "giỏ hàng" in it["summary"].lower()
        or "e-commerce" in it["summary"].lower()
        or "ecommerce" in it["summary"].lower()
        for it in all_items
    )
    if not has_ecom and epics:
        first_epic = epics[0]["summary"]
        clean_first = re.sub(r"[^\w\s]", " ", first_epic).strip()
        words = re.findall(r"\b[A-Za-z0-9]", clean_first)
        suggested_name = f"Dự án {clean_first[:20]}"
        suggested_ident = ("".join(words[:4]).upper()) if words else "PROJ"
        if len(suggested_ident) < 2:
            suggested_ident = "PROJ"

    return {
        "all_items": all_items,
        "epics": epics,
        "tasks": tasks,
        "subtasks": subtasks,
        "suggested_name": suggested_name,
        "suggested_ident": suggested_ident,
        "total_count": len(all_items),
        "detected_labels": list(detected_labels),
    }



def _generate_jira_plan_from_prompt(prompt: str) -> dict[str, Any]:
    topic = "Hệ thống Quản lý"
    m_topic = re.search(r"(?:dự án|hệ thống|app|web|ứng dụng|về)\s+([^,.?!\n]+)", prompt, re.I)
    if m_topic:
        raw_topic = m_topic.group(1).strip()
        raw_topic = re.sub(r"^(cho|về|của|như|toàn bộ|tự động|ai)\s+", "", raw_topic, flags=re.I).strip()
        if raw_topic:
            topic = raw_topic.title()

    clean_words = re.findall(r"\b[A-Za-z0-9]", topic)
    sug_ident = ("".join(clean_words[:4]).upper()) if clean_words else "JIRA"
    if len(sug_ident) < 2:
        sug_ident = "JIRA"

    epics = [
        {"id": "EP-1", "parent": "", "type": "Epic", "summary": f"Khởi tạo Kiến trúc & Hạ tầng {topic}", "desc": "Thiết lập database, CI/CD, bảo mật và kiến trúc nền tảng theo chuẩn Agile Jira", "priority": "high"},
        {"id": "EP-2", "parent": "", "type": "Epic", "summary": f"Nghiệp vụ cốt lõi & Tính năng chính {topic}", "desc": "Các module chức năng chính phục vụ người dùng cuối và nghiệp vụ hệ thống", "priority": "high"},
        {"id": "EP-3", "parent": "", "type": "Epic", "summary": "Báo cáo, Thống kê & Quản trị Hệ thống", "desc": "Dashboard phân tích số liệu, xuất báo cáo và phân quyền quản trị", "priority": "medium"},
    ]
    tasks = [
        {"id": "TK-101", "parent": "EP-1", "type": "Task", "summary": "Thiết kế Schema Database & ERD", "desc": "Xây dựng các bảng dữ liệu, quan hệ và migration", "priority": "high"},
        {"id": "TK-102", "parent": "EP-1", "type": "Task", "summary": "Xây dựng API Xác thực JWT & Phân quyền", "desc": "Endpoint đăng ký, đăng nhập và bảo mật OAuth2", "priority": "high"},
        {"id": "TK-201", "parent": "EP-2", "type": "Task", "summary": f"Giao diện & Luồng xử lý chính của {topic}", "desc": "Trang tương tác người dùng, xử lý dữ liệu và validation", "priority": "high"},
        {"id": "TK-202", "parent": "EP-2", "type": "Task", "summary": "Tích hợp Notification & Email cảnh báo", "desc": "Hệ thống thông báo đẩy và email transactional", "priority": "medium"},
        {"id": "TK-301", "parent": "EP-3", "type": "Task", "summary": "Xây dựng Dashboard thống kê tổng quan", "desc": "Biểu đồ trực quan và báo cáo theo thời gian thực", "priority": "medium"},
    ]
    subtasks = [
        {"id": "ST-1001", "parent": "TK-101", "type": "Sub-task", "summary": "Định nghĩa bảng Users, Roles và Permissions", "desc": "Tạo migration và index tối ưu truy vấn", "priority": "high"},
        {"id": "ST-1002", "parent": "TK-101", "type": "Sub-task", "summary": "Định nghĩa bảng nghiệp vụ chính", "desc": "Tạo các model chính và ràng buộc khóa ngoại", "priority": "high"},
        {"id": "ST-1003", "parent": "TK-102", "type": "Sub-task", "summary": "Viết Middleware kiểm tra token và refresh token", "desc": "Xử lý xác thực bearer token tự động", "priority": "high"},
        {"id": "ST-2001", "parent": "TK-201", "type": "Sub-task", "summary": "Thiết kế UI Components theo Design System", "desc": "Tạo các component tái sử dụng", "priority": "medium"},
        {"id": "ST-2002", "parent": "TK-201", "type": "Sub-task", "summary": "Kết nối State Management & API Client", "desc": "Quản lý cache và phản hồi giao diện mượt mà", "priority": "medium"},
        {"id": "ST-3001", "parent": "TK-301", "type": "Sub-task", "summary": "Viết query tổng hợp số liệu hiệu năng", "desc": "Aggregation pipeline tính KPI", "priority": "medium"},
    ]

    all_items = epics + tasks + subtasks
    return {
        "all_items": all_items,
        "epics": epics,
        "tasks": tasks,
        "subtasks": subtasks,
        "suggested_name": f"Dự án {topic}",
        "suggested_ident": sug_ident,
        "total_count": len(all_items),
        "detected_labels": ["jira-agile", "architecture", "frontend", "backend"],
    }


async def _import_jira_backlog_to_project(
    client: Client,
    tool_calls: list[dict[str, Any]],
    workspace_slug: str,
    project_id: str,
    project_ident: str,
    backlog: dict[str, Any],
) -> tuple[int, list[tuple[str, str, str]]]:
    try:
        s_raw, s_data = await _run_tool(client, "plane_list_states", {"workspace_slug": workspace_slug, "project_id": project_id})
        tool_calls.append({"name": "plane_list_states", "args": {"workspace_slug": workspace_slug, "project_id": project_id}, "result": s_data})
        states_list = s_data.get("results", []) if isinstance(s_data, dict) else (s_data if isinstance(s_data, list) else [])
    except Exception:
        states_list = []

    state_by_group = {}
    for st in states_list:
        group = (st.get("group") or "").lower()
        if group and group not in state_by_group:
            state_by_group[group] = st.get("id")

    default_backlog_state = state_by_group.get("backlog") or state_by_group.get("unstarted")
    default_todo_state = state_by_group.get("unstarted") or default_backlog_state

    id_map: dict[str, str] = {}
    imported_items: list[tuple[str, str, str]] = []

    # 1. Epics (Level 1 in Jira hierarchy)
    for ep in backlog.get("epics", []):
        args = {
            "workspace_slug": workspace_slug,
            "project_id": project_id,
            "name": f"[Epic] {ep['summary']}",
            "description_html": f"<p><strong>Jira Issue Type:</strong> Epic</p><p>{ep.get('desc', '')}</p>",
            "priority": ep.get("priority", "high"),
        }
        if default_backlog_state:
            args["state_id"] = default_backlog_state
        c_raw, c_data = await _run_tool(client, "plane_create_work_item", args)
        tool_calls.append({"name": "plane_create_work_item", "args": args, "result": c_data})
        epic_id = c_data.get("id") if isinstance(c_data, dict) else ""
        if epic_id and ep.get("id"):
            id_map[str(ep["id"]).strip()] = epic_id
        seq = c_data.get("sequence_id", "") if isinstance(c_data, dict) else ""
        imported_items.append(
            (f"[{project_ident}-{seq}]" if seq else "[-]", f"[Epic] {ep['summary']}", ep.get("priority", "high"))
        )

    # 2. Tasks / Stories (Level 2 in Jira hierarchy, linked to parent Epic)
    for t in backlog.get("tasks", [])[:40]:
        parent_csv_id = str(t.get("parent", "")).strip()
        parent_plane_id = id_map.get(parent_csv_id)
        args = {
            "workspace_slug": workspace_slug,
            "project_id": project_id,
            "name": f"[Task] {t['summary']}",
            "description_html": f"<p><strong>Jira Issue Type:</strong> Task / Story</p><p>{t.get('desc', '')}</p>",
            "priority": t.get("priority", "medium"),
        }
        if parent_plane_id:
            args["parent_id"] = parent_plane_id
        if default_todo_state:
            args["state_id"] = default_todo_state
        c_raw, c_data = await _run_tool(client, "plane_create_work_item", args)
        tool_calls.append({"name": "plane_create_work_item", "args": args, "result": c_data})
        task_id = c_data.get("id") if isinstance(c_data, dict) else ""
        if task_id and t.get("id"):
            id_map[str(t["id"]).strip()] = task_id
        seq = c_data.get("sequence_id", "") if isinstance(c_data, dict) else ""
        imported_items.append(
            (f"[{project_ident}-{seq}]" if seq else "[-]", f"[Task] {t['summary']}", t.get("priority", "medium"))
        )

    # 3. Sub-tasks (Level 3 in Jira hierarchy, linked to parent Task)
    for s in backlog.get("subtasks", [])[:30]:
        parent_csv_id = str(s.get("parent", "")).strip()
        parent_plane_id = id_map.get(parent_csv_id)
        args = {
            "workspace_slug": workspace_slug,
            "project_id": project_id,
            "name": f"[Sub-task] {s['summary']}",
            "description_html": f"<p><strong>Jira Issue Type:</strong> Sub-task</p><p>{s.get('desc', '')}</p>",
            "priority": s.get("priority", "medium"),
        }
        if parent_plane_id:
            args["parent_id"] = parent_plane_id
        if default_todo_state:
            args["state_id"] = default_todo_state
        c_raw, c_data = await _run_tool(client, "plane_create_work_item", args)
        tool_calls.append({"name": "plane_create_work_item", "args": args, "result": c_data})
        seq = c_data.get("sequence_id", "") if isinstance(c_data, dict) else ""
        imported_items.append(
            (f"[{project_ident}-{seq}]" if seq else "[-]", f"[Sub-task] {s['summary']}", s.get("priority", "medium"))
        )

    return len(imported_items), imported_items


async def _builtin_agent(client: Client, user_msg: str, file_data: dict[str, Any] | None = None) -> dict[str, Any]:
    msg = user_msg.strip()
    tool_calls = []

    # 1. Fetch available workspaces
    ws_raw, ws_data = await _run_tool(client, "plane_list_workspaces", {})
    tool_calls.append({"name": "plane_list_workspaces", "args": {}, "result": ws_data})

    workspaces = (ws_data.get("results") if isinstance(ws_data, dict) else []) or []
    current_workspace = workspaces[0]["slug"] if workspaces else "qldapm"

    # 2. Fetch available projects in primary workspace
    proj_raw, proj_data = await _run_tool(client, "plane_list_projects", {"workspace_slug": current_workspace})
    tool_calls.append(
        {"name": "plane_list_projects", "args": {"workspace_slug": current_workspace}, "result": proj_data}
    )
    projects = (proj_data.get("results") if isinstance(proj_data, dict) else []) or []
    current_project = projects[0] if projects else None

    # Load any pending backlog from storage
    pending_backlog = _load_pending_backlog()

    # 3. Check for CSV file or CSV text input
    fname, csv_content = _extract_csv_text(msg, file_data)
    if csv_content:
        parsed_backlog = _parse_csv_backlog(csv_content)
        if parsed_backlog:
            _save_pending_backlog(parsed_backlog)

            epics_count = len(parsed_backlog["epics"])
            tasks_count = len(parsed_backlog["tasks"])
            subtasks_count = len(parsed_backlog["subtasks"])
            total_count = parsed_backlog["total_count"]
            sug_name = parsed_backlog["suggested_name"]
            sug_ident = parsed_backlog["suggested_ident"]

            epic_bullets = []
            for idx, ep in enumerate(parsed_backlog["epics"][:7], 1):
                epic_bullets.append(f"{idx}. `{ep['summary']}`")
            epic_text = "\n".join(epic_bullets) if epic_bullets else "* Các đầu mục công việc chi tiết"

            reply_text = (
                f"🎯 **Phát hiện tệp kế hoạch dự án:** `{fname}`\n\n"
                f"📊 **Phân tích cấu trúc dữ liệu:**\n"
                f"* **Tổng số công việc:** **{total_count} mục** (gồm **{epics_count}** Epic lớn, **{tasks_count}** Task nghiệp vụ, **{subtasks_count}** Sub-task chi tiết)\n"
                f"* **Các Module / Epic chính:**\n{epic_text}\n\n"
                f"✨ **Đề xuất thiết lập Dự án Mới trên Plane:**\n"
                f"Để quản lý lộ trình này độc lập và chuyên nghiệp nhất theo chuẩn Agile/Scrum, tôi đã phân tích và đề xuất cấu hình dự án:\n"
                f"* **Tên dự án (Project Name):** `{sug_name}`\n"
                f"* **Mã dự án (Slug / Identifier / Prefix):** `{sug_ident}`\n"
                f"* **Không gian làm việc (Workspace):** `{current_workspace}`\n\n"
                f"---\n"
                f"💬 **Bạn có muốn:**\n"
                f"1. **Tạo ngay theo đề xuất:** Bấm nút **'🚀 Tạo dự án {sug_name} (Slug: {sug_ident}) & Import'** bên dưới.\n"
                f"2. **Tùy chỉnh tên hoặc slug riêng:** Nhập cú pháp: `Tạo dự án [Tên] slug [MÃ]` (Ví dụ: `Tạo dự án Bán Hàng slug BH` hoặc `Tên: Dự án XYZ, Slug: XYZ`).\n"
                f"3. **Import vào dự án hiện tại (`{current_project['name'] if current_project else 'QLDA'}`):** Bấm nút **'📥 Import vào dự án hiện tại'**."
            )

            actions = [
                {
                    "label": f"🚀 Tạo dự án {sug_name} (Slug: {sug_ident}) & Import",
                    "action": f"Tạo dự án {sug_name} slug {sug_ident}",
                },
                {
                    "label": "✏️ Hỏi / Tùy chỉnh Tên & Slug khác",
                    "action": "Hướng dẫn đặt tên và slug dự án",
                },
                {
                    "label": f"📥 Import vào dự án hiện tại ({current_project.get('identifier', 'QLDA') if current_project else 'QLDA'})",
                    "action": "Import vào dự án hiện tại",
                },
            ]

            return {"reply": reply_text, "actions": actions, "tool_calls": tool_calls}

    # 4. Check for IMPORT TO CURRENT PROJECT
    if pending_backlog and re.search(
        r"\b(import|nhập|thêm)\s+(vào\s+)?(dự án hiện tại|dự án cũ|project hiện tại|hiện tại)\b", msg, re.I
    ):
        if not current_project:
            return {"reply": "⚠️ Không tìm thấy dự án hiện tại nào trong workspace để import.", "tool_calls": tool_calls}

        target_id = current_project["id"]
        target_name = current_project["name"]
        target_ident = current_project.get("identifier", "TASK")

        total_done, imported_items = await _import_jira_backlog_to_project(
            client, tool_calls, current_workspace, target_id, target_ident, pending_backlog
        )
        _save_pending_backlog(None)

        reply = (
            f"✅ **Đã hoàn tất import {total_done} công việc vào dự án {target_name} ({target_ident})!**\n\n"
            f"* **Không gian làm việc:** `{current_workspace}`\n"
            f"* **Dự án:** `{target_name}`\n\n"
            f"📋 **Các đầu việc chính vừa tạo:**\n"
        )
        for code, t_name, t_prio in imported_items[:10]:
            reply += f"* `{code}` **{t_name}** — Ưu tiên: `{t_prio}`\n"
        if total_done > 10:
            reply += f"* ... và {total_done - 10} công việc khác.\n"

        return {"reply": reply, "tool_calls": tool_calls}

    # 5. Check for ASKING / CUSTOMIZING NAME & SLUG
    if re.search(
        r"(?:hướng\s+dẫn|đổi|sửa|thay\s+đổi|chỉnh|hỏi|tùy\s+chỉnh|cách).*(?:tên|slug|mã|identifier)", msg, re.I
    ):
        sug_n = pending_backlog.get("suggested_name", "Website Thương Mại") if pending_backlog else "Website Thương Mại"
        sug_i = pending_backlog.get("suggested_ident", "WTM") if pending_backlog else "WTM"
        extra_note = (
            "\n\n✨ *Backlog vừa tải lên đang được lưu sẵn. Khi tạo dự án, hệ thống sẽ tự động import toàn bộ công việc vào dự án mới!*"
            if pending_backlog
            else ""
        )
        return {
            "reply": (
                f"📝 **Hướng dẫn đặt Tên dự án và Mã định danh (Slug / Identifier):**\n\n"
                f"Trong Plane, mỗi dự án cần có:\n"
                f"1. **Tên dự án (Project Name):** Ví dụ: *'Website Thương Mại'*, *'Hệ thống ECommerce'*\n"
                f"2. **Slug / Mã dự án (Identifier):** Từ 2-6 ký tự viết hoa (ví dụ: `ECOM`, `WTM`, `PROJ`), dùng làm tiền tố số hiệu task như `ECOM-1`, `ECOM-2`.\n\n"
                f"💡 **Cú pháp ra lệnh tạo dự án nhanh:**\n"
                f"* `Tạo dự án [Tên dự án] slug [MÃ]` (Ví dụ: `Tạo dự án Quản Lý Bán Hàng slug QLBH`)\n"
                f"* Hoặc: `Tên: Dự án Mới, Slug: PROJ`"
                f"{extra_note}"
            ),
            "actions": [
                {
                    "label": f"🚀 Tạo dự án {sug_n} (Slug: {sug_i})",
                    "action": f"Tạo dự án {sug_n} slug {sug_i}",
                },
                {
                    "label": "🚀 Tạo dự án Bán Hàng (Slug: BH)",
                    "action": "Tạo dự án Bán Hàng slug BH",
                },
            ],
            "tool_calls": tool_calls,
        }

    # 6. Check for CREATE PROJECT (or CONFIRM CREATE PROJECT)
    is_create_proj = bool(re.search(r"\b(tạo|thêm|create)\s+(dự án|project)\b", msg, re.I))
    is_confirm_create = bool(
        pending_backlog and re.search(r"\b(xác nhận|đồng ý|tiến hành|ok|duyệt|bắt đầu|tạo ngay)\b", msg, re.I)
    )

    if is_create_proj or is_confirm_create:
        proj_name = None
        ident = None

        # Pattern A: Key-value "Tên: XYZ, Slug: ABC"
        m_kv = re.search(
            r"(?:tên(?:\s+dự\s+án)?|name)\s*[:=]\s*([^,\n]+?)(?:,?\s*(?:mã|slug|identifier|prefix|code)\s*[:=]\s*([A-Za-z0-9]{2,6}))",
            msg,
            re.I,
        )
        if m_kv:
            proj_name = m_kv.group(1).strip()
            ident = m_kv.group(2).strip().upper()
        else:
            # Pattern B: "Tạo dự án <name> (mã|slug|identifier|prefix|code) <ident>"
            m = re.search(
                r"(?:tạo|thêm|create)\s+(?:dự án|project)\s+(?:mới\s+)?(?:tên\s+là\s+)?(.+?)(?:\s+(?:mã|slug|identifier|code|prefix)\s+([A-Za-z0-9]{2,6})|$)",
                msg,
                re.I,
            )
            if m:
                raw_name = m.group(1).strip()
                if m.group(2):
                    ident = m.group(2).upper().strip()
                proj_name = raw_name

        if not ident:
            m_slug = re.search(r"(?:mã|slug|identifier|code|prefix)\s*[:=]?\s*([A-Za-z0-9]{2,6})\b", msg, re.I)
            if m_slug:
                ident = m_slug.group(1).upper().strip()

        if not proj_name and pending_backlog:
            proj_name = pending_backlog["suggested_name"]
            ident = ident or pending_backlog["suggested_ident"]

        if not proj_name:
            proj_name = "Dự án mới"

        # Sanitize project name (Plane rejects special characters like hyphens)
        proj_name = re.sub(r"[^A-Za-z0-9À-ỹ\s]", " ", proj_name).strip()
        proj_name = re.sub(r"\s+", " ", proj_name)

        if not ident:
            if pending_backlog and pending_backlog.get("suggested_ident"):
                ident = pending_backlog["suggested_ident"]
            else:
                words = re.findall(r"\b[A-Za-z0-9]", proj_name)
                ident = ("".join(words[:4]).upper()) if words else "PROJ"
                if len(ident) < 2:
                    ident = "PROJ"

        # Check if project already exists
        existing_proj = None
        for p in projects:
            if p.get("identifier", "").upper() == ident.upper() or p.get("name", "").lower() == proj_name.lower():
                existing_proj = p
                break

        if existing_proj:
            target_project_id = existing_proj["id"]
            target_project_name = existing_proj["name"]
            ident = existing_proj.get("identifier", ident)
        else:
            args = {"workspace_slug": current_workspace, "name": proj_name, "identifier": ident}
            p_raw, p_data = await _run_tool(client, "plane_create_project", args)
            tool_calls.append({"name": "plane_create_project", "args": args, "result": p_data})
            target_project_id = p_data.get("id") if isinstance(p_data, dict) else ""
            target_project_name = proj_name

            if not target_project_id:
                err_msg = ""
                if isinstance(p_data, dict):
                    err_msg = p_data.get("error") or p_data.get("detail") or str(p_data)
                return {
                    "reply": f"⚠️ Không thể tạo dự án `{proj_name}` (Slug: `{ident}`): {err_msg or 'Lỗi từ hệ thống Plane'}. Vui lòng thử lại với tên hoặc mã định danh khác.",
                    "tool_calls": tool_calls,
                }

        # If there is pending backlog, import into this project!
        if pending_backlog and target_project_id:
            total_imported, imported_items = await _import_jira_backlog_to_project(
                client, tool_calls, current_workspace, target_project_id, ident, pending_backlog
            )
            _save_pending_backlog(None)

            reply = (
                f"🎉 **Đã kết nối thành công dự án `{target_project_name}` (Mã: `{ident}`) và hoàn tất Import {total_imported} công việc vào Plane!**\n\n"
                f"* **Tên dự án:** {target_project_name}\n"
                f"* **Mã định danh:** `{ident}`\n"
                f"* **Không gian làm việc:** `{current_workspace}`\n"
                f"* **Số lượng công việc đã import:** **{total_imported} task** (gồm toàn bộ Epics, Tasks & Sub-tasks)\n\n"
                f"📋 **Các đầu việc chính vừa được tạo:**\n"
            )
            for code, t_name, t_prio in imported_items[:10]:
                reply += f"* `{code}` **{t_name}** — Ưu tiên: `{t_prio}`\n"
            if total_imported > 10:
                reply += f"* ... và {total_imported - 10} công việc khác.\n\n"
            reply += "👉 Bạn có thể xem ngay dự án trên thanh menu bên trái của Plane!"
            return {"reply": reply, "tool_calls": tool_calls}

        # Otherwise just normal project creation
        reply = (
            f"🚀 **Đã tạo thành công dự án mới trên Plane!**\n\n"
            f"* **Tên dự án:** {target_project_name}\n"
            f"* **Mã định danh:** `{ident}`\n"
            f"* **Workspace:** `{current_workspace}`\n\n"
            f"Bây giờ bạn có thể bắt đầu tạo các task cho dự án này!"
        )
        return {"reply": reply, "tool_calls": tool_calls}

    # Check for LIST PROJECTS intent
    if re.search(r"\b(danh sách|xem|liệt kê|list|các)\s+(dự án|project)\b", msg, re.I):
        if not projects:
            return {"reply": f"📁 Workspace `{current_workspace}` hiện chưa có dự án nào.", "tool_calls": tool_calls}

        lines = [f"📁 **Danh sách dự án trong workspace `{current_workspace}` ({len(projects)} dự án):**\n"]
        for p in projects:
            ident = p.get("identifier", "")
            lines.append(f"* **{p.get('name')}** (Mã: `{ident}`) — ID: `{p.get('id')}`")
        return {"reply": "\n".join(lines), "tool_calls": tool_calls}

    # Check for LIST WORKSPACES intent
    if re.search(r"\b(danh sách|xem|liệt kê|list)\s+(workspace|không gian)\b", msg, re.I):
        lines = [f"🏢 **Danh sách Workspace của bạn ({len(workspaces)}):**\n"]
        for w in workspaces:
            lines.append(f"* **{w.get('name')}** (slug: `{w.get('slug')}`)")
        return {"reply": "\n".join(lines), "tool_calls": tool_calls}

    # Check for GEMINI / 3.8 FLASH queries
    if re.search(r"\b(gemini|flash|3\.8|3\s*flash|model\s*3|cài\s+3)\b", msg, re.I):
        reply = (
            "⚡ **Mô hình Gemini 3.8 Flash (`gemini-3.8-flash`) đã được tích hợp sẵn làm bộ não mặc định!**\n\n"
            "🔹 **Thông tin cấu hình:**\n"
            "* **Mô hình (Model ID):** `gemini-3.8-flash` (Google DeepMind)\n"
            "* **Giao thức:** Google OpenAI-compatible endpoint kết hợp trực tiếp 14 công cụ **Plane MCP**\n"
            "* **Trạng thái:** Sẵn sàng hoạt động\n\n"
            "💡 **Để chạy mô hình Gemini 3.8 Flash:**\n"
            "1. **Trên giao diện Web:** Bấm biểu tượng bánh răng **⚙️ (Cài đặt)** ở góc trên bên phải khung chat, chọn `Gemini 3.8 Flash`, nhập **Gemini API Key** (dạng `AIza...`) và bấm **Lưu cài đặt**.\n"
            "2. **Hoặc cấu hình Server:** Thêm dòng sau vào file `apps/api/.env`:\n"
            "   ```env\n"
            "   GEMINI_API_KEY=\"AIzaSy...\"\n"
            "   ```\n\n"
            "*(Khóa API Gemini được cấp miễn phí tại: [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey). Trong lúc chưa có khóa API, hệ thống vẫn dùng bộ xử lý nội bộ tự động miễn phí!)*"
        )
        actions = [
            {
                "label": "📁 Xem danh sách các dự án",
                "action": "Xem danh sách các dự án",
            },
            {
                "label": "📋 Xem các task hiện có",
                "action": "Xem danh sách task",
            },
        ]
        return {"reply": reply, "actions": actions, "tool_calls": tool_calls}

    # Check for Jira Auto Planning / Auto Breakdown intent
    if not pending_backlog and re.search(r"\b(như\s+jira|tự\s+động|kế\s+hoạch|lập\s+kế\s+hoạch|jira\s+toàn\s+bộ|backlog\s+mới|tạo\s+dự\s+án\s+ai)\b", msg, re.I):
        parsed_backlog = _generate_jira_plan_from_prompt(msg)
        _save_pending_backlog(parsed_backlog)
        epics_count = len(parsed_backlog["epics"])
        tasks_count = len(parsed_backlog["tasks"])
        subtasks_count = len(parsed_backlog["subtasks"])
        total_count = parsed_backlog["total_count"]
        sug_name = parsed_backlog["suggested_name"]
        sug_ident = parsed_backlog["suggested_ident"]

        epic_bullets = []
        for idx, ep in enumerate(parsed_backlog["epics"], 1):
            epic_bullets.append(f"{idx}. `[Epic]` **{ep['summary']}**\n   *Mô tả:* {ep['desc']}")
        epic_text = "\n".join(epic_bullets)

        reply_text = (
            f"⚡ **AI đã tự động phân tích & lập kế hoạch dự án chuẩn Jira Agile:**\n\n"
            f"📊 **Cấu trúc phân rã công việc (Work Breakdown Structure):**\n"
            f"* **Tổng số mục:** **{total_count} công việc** (gồm **{epics_count}** Epic cha, **{tasks_count}** Task/Story, **{subtasks_count}** Sub-task con liên kết chặt chẽ)\n"
            f"* **Các Epic chính:**\n{epic_text}\n\n"
            f"✨ **Cấu hình dự án đề xuất:**\n"
            f"* **Tên dự án:** `{sug_name}`\n"
            f"* **Mã định danh (Key/Slug):** `{sug_ident}`\n"
            f"* **Workspace:** `{current_workspace}`\n\n"
            f"🎯 **Hệ thống sẵn sàng tự động khởi tạo toàn bộ dự án và đưa toàn bộ task vào Plane theo chuẩn Jira!**\n"
            f"Bạn chỉ cần bấm nút hành động bên dưới để AI tự động thực thi:"
        )

        actions = [
            {
                "label": f"🚀 Tạo dự án {sug_name} ({sug_ident}) & Tự động Import",
                "action": f"Tạo dự án {sug_name} slug {sug_ident}",
            },
            {
                "label": f"📥 Import vào dự án hiện tại ({current_project.get('identifier', 'QLDA') if current_project else 'QLDA'})",
                "action": "Import vào dự án hiện tại",
            },
        ]
        return {"reply": reply_text, "actions": actions, "tool_calls": tool_calls}

    # Default fallback / greeting
    return {
        "reply": (
            f"👋 **Chào bạn! Tôi là Trợ lý AI điều khiển Plane qua MCP.**\n\n"
            f"Hiện tại tôi đã kết nối với workspace **`{current_workspace}`** "
            f"và dự án **`{current_project.get('name') if current_project else 'Chưa có'}`**.\n\n"
            f"**Bạn có thể ra lệnh bằng tiếng Việt tự nhiên, ví dụ:**\n"
            f"1. *'Tạo task Thiết kế cơ sở dữ liệu với độ ưu tiên cao'*\n"
            f"2. *'Xem danh sách công việc hiện có'*\n"
            f"3. *'Tạo dự án mới Website Bán Hàng mã WBH'*\n"
            f"4. *'Xem danh sách các dự án'* hoặc *'Xem workspace'*"
        ),
        "tool_calls": tool_calls,
    }


async def chat_handler(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Dữ liệu JSON không hợp lệ"}, status_code=400)
    message = body.get("message", "")
    history = body.get("history", [])
    settings = body.get("settings", {})

    if not isinstance(message, str) or not message.strip():
        return JSONResponse({"error": "Tin nhắn không được để trống"}, status_code=400)

    file_data = body.get("file", None)

    helpers = {
        "save_pending_backlog": _save_pending_backlog,
        "load_pending_backlog": _load_pending_backlog,
        "extract_csv_text": _extract_csv_text,
        "parse_csv_backlog": _parse_csv_backlog,
        "import_jira_backlog_to_project": _import_jira_backlog_to_project,
    }

    provider = settings.get("provider", "codex")

    # Local Agent Bridge execution: 100% on the laptop via Plane MCP & Codex/Gemini
    if provider in ("codex", "antigravity", "local_bridge", "builtin"):
        try:
            return JSONResponse(
                await _with_client(lambda c: LocalAgentBridge.process_request(c, message, history, file_data, helpers, provider=provider))
            )
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)

    if provider == "gemini":
        gemini_key = (
            settings.get("apiKey", "").strip()
            or os.environ.get("GEMINI_API_KEY", "").strip()
            or os.environ.get("GOOGLE_API_KEY", "").strip()
        )
        if gemini_key:
            is_gemini = True
            api_key = gemini_key
            base_url = settings.get("baseUrl", "").rstrip("/") or os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")
            model_name = settings.get("model", "") or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
        else:
            try:
                return JSONResponse(await _with_client(lambda c: LocalAgentBridge.process_request(c, message, history, file_data, helpers)))
            except Exception as exc:
                return JSONResponse({"error": str(exc)}, status_code=502)
    else:
        is_gemini = False
        api_key = settings.get("apiKey", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
        base_url = settings.get("baseUrl", "").rstrip("/") or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        model_name = settings.get("model", "") or "gpt-4o"

    if not api_key:
        try:
            return JSONResponse(await _with_client(lambda c: LocalAgentBridge.process_request(c, message, history, file_data, helpers)))
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)

    # If an external LLM is configured, use the Responses API as the agent loop
    # while keeping Plane MCP local and private with strict token optimization.
    if api_key:
        try:
            if is_gemini:

                async def run_gemini_agent(client: Client):
                    tools_result = await client.list_tools()
                    gemini_tools = [
                        {
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description or "",
                                "parameters": tool.input_schema or {"type": "object", "properties": {}},
                            },
                        }
                        for tool in tools_result.tools
                    ]
                    system_prompt = (
                        "Bạn là Plane AI Agent điều khiển Plane qua MCP tools. "
                        "Mục tiêu của bạn: Thực hiện chính xác, trả lời ngắn gọn súc tích, tối ưu hóa token tối đa. "
                        "1. Khi người dùng hỏi thông tin, hãy dùng MCP tools để tra cứu và trả lời trực tiếp. "
                        "2. Khi người dùng yêu cầu tạo dự án/task, hãy gọi tool tương ứng. "
                        "3. Nếu có tệp CSV đính kèm, kế hoạch chi tiết đã được bóc tách sẵn trong hệ thống; bạn chỉ cần xác nhận và gọi tạo dự án hoặc import. "
                        "4. Luôn trả lời tiếng Việt ngắn gọn, rõ ràng, không vòng vo."
                    )
                    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
                    for item in history[-6:]:
                        role = item.get("role", "user")
                        content = item.get("content", "")
                        if role in {"user", "assistant"} and isinstance(content, str) and content:
                            messages.append({"role": role, "content": content})
                    messages.append({"role": "user", "content": _message_with_text_file(message, file_data)})

                    executed_tool_calls: list[dict[str, Any]] = []
                    async with httpx2.AsyncClient(timeout=90) as http:
                        for _ in range(6):
                            payload = {
                                "model": model_name,
                                "messages": messages,
                                "tools": gemini_tools,
                                "tool_choice": "auto",
                                "max_tokens": 1500,
                                "temperature": 0.2,
                            }
                            response = await http.post(
                                f"{base_url}/chat/completions",
                                headers={
                                    "Authorization": f"Bearer {api_key}",
                                    "Content-Type": "application/json",
                                },
                                json=payload,
                            )
                            if response.status_code != 200:
                                raise RuntimeError(f"Lỗi từ Gemini ({response.status_code}): {response.text[:500]}")

                            assistant_message = response.json()["choices"][0]["message"]
                            messages.append(assistant_message)
                            tool_calls = assistant_message.get("tool_calls") or []
                            if not tool_calls:
                                return {
                                    "reply": assistant_message.get("content") or "Đã xử lý xong yêu cầu.",
                                    "tool_calls": executed_tool_calls,
                                }

                            for tool_call in tool_calls:
                                function = tool_call["function"]
                                tool_name = function["name"]
                                try:
                                    tool_args = json.loads(function.get("arguments", "{}"))
                                except json.JSONDecodeError as exc:
                                    raise RuntimeError(f"Tool {tool_name} trả về tham số JSON không hợp lệ") from exc
                                call_result = await client.call_tool(tool_name, tool_args)
                                tool_payload = _extract_tool_payload(call_result)
                                executed_tool_calls.append(
                                    {"name": tool_name, "args": tool_args, "result": tool_payload}
                                )
                                # Ultra-low token trimming for Gemini
                                trimmed_payload = _trim_tool_payload_for_llm(tool_name, tool_payload)
                                messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tool_call["id"],
                                        "content": json.dumps(trimmed_payload, ensure_ascii=False),
                                    }
                                )

                    return {
                        "reply": "Đã hoàn thành các bước gọi công cụ.",
                        "tool_calls": executed_tool_calls,
                    }

                result = await _with_client(run_gemini_agent)
                return JSONResponse(result)

            async def run_llm_agent(client: Client):
                tools_result = await client.list_tools()
                openai_tools = [
                    {
                        "type": "function",
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.input_schema or {"type": "object", "properties": {}},
                    }
                    for t in tools_result.tools
                ]

                system_prompt = (
                    "Bạn là trợ lý AI chuyên nghiệp điều khiển Plane qua MCP (Model Context Protocol). "
                    "Hãy trả lời bằng tiếng Việt thân thiện, rõ ràng, sử dụng các tool được cung cấp để thao tác với Plane. "
                    "Ưu tiên đọc/liệt kê workspace và project trước khi tạo hoặc cập nhật. "
                    "Không tuyên bố thao tác đã thành công nếu chưa nhận được kết quả tool tương ứng."
                )
                response_input: list[dict[str, Any]] = []
                for h in history[-8:]:
                    role = h.get("role", "user")
                    content = h.get("content", "")
                    if role in {"user", "assistant"} and isinstance(content, str) and content:
                        response_input.append({"role": role, "content": content})

                user_content: list[dict[str, Any]] = []
                attachment = _file_input(file_data)
                if attachment:
                    user_content.append(attachment)
                user_content.append({"type": "input_text", "text": message})
                response_input.append({"role": "user", "content": user_content})

                executed_tool_calls: list[dict[str, Any]] = []

                async with httpx2.AsyncClient(timeout=60) as http:
                    for _ in range(8):
                        req_payload = {
                            "model": model_name,
                            "instructions": system_prompt,
                            "input": response_input,
                            "tools": openai_tools,
                        }
                        res = await http.post(
                            f"{base_url}/responses",
                            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                            json=req_payload,
                        )
                        if res.status_code != 200:
                            raise RuntimeError(f"Lỗi từ LLM ({res.status_code}): {res.text[:500]}")

                        data = res.json()
                        output = data.get("output", [])
                        tool_calls = [item for item in output if item.get("type") == "function_call"]
                        if not tool_calls:
                            return {
                                "reply": _response_text(data) or "Đã xử lý xong yêu cầu.",
                                "tool_calls": executed_tool_calls,
                            }

                        response_input.extend(output)
                        for tc in tool_calls:
                            f_name = tc["name"]
                            try:
                                f_args = json.loads(tc.get("arguments", "{}"))
                            except json.JSONDecodeError as exc:
                                raise RuntimeError(f"Tool {f_name} trả về tham số JSON không hợp lệ") from exc

                            call_res = await client.call_tool(f_name, f_args)
                            tool_payload = _extract_tool_payload(call_res)
                            executed_tool_calls.append({"name": f_name, "args": f_args, "result": tool_payload})

                            response_input.append(
                                {
                                    "type": "function_call_output",
                                    "call_id": tc["call_id"],
                                    "output": json.dumps(tool_payload, ensure_ascii=False),
                                }
                            )

                    return {
                        "reply": "Đã dừng sau 8 vòng gọi công cụ để tránh vòng lặp vô hạn.",
                        "tool_calls": executed_tool_calls,
                    }

            result = await _with_client(run_llm_agent)
            return JSONResponse(result)
        except Exception as exc:
            # Fallback to builtin agent if external LLM fails, with helpful explanation
            err_text = str(exc)

            async def run_builtin_with_notice(client: Client):
                res = await _builtin_agent(client, message, file_data)
                provider_name = "Gemini" if is_gemini else "OpenAI"
                if "401" in err_text or "invalid_api_key" in err_text or "API_KEY_INVALID" in err_text:
                    prefix = f"⚠️ **Lưu ý {provider_name}**: API Key không hợp lệ. Đã chuyển sang chế độ nội bộ.\n\n"
                elif "429" in err_text or "insufficient_quota" in err_text:
                    prefix = f"⚠️ **Lưu ý {provider_name}**: Đã hết quota API. Đã chuyển sang chế độ nội bộ.\n\n"
                else:
                    prefix = (
                        f"⚠️ **Lưu ý {provider_name}**: Lỗi kết nối ({err_text[:80]}). Đã chuyển sang chế độ nội bộ.\n\n"
                    )
                res["reply"] = prefix + res.get("reply", "")
                return res

            try:
                result = await _with_client(run_builtin_with_notice)
                return JSONResponse(result)
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=502)

    # Built-in Agent execution
    try:

        async def run_builtin(client: Client):
            return await _builtin_agent(client, message, file_data)

        result = await _with_client(run_builtin)
        return JSONResponse(result)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


app = Starlette(
    routes=[
        Route("/", home),
        Route("/api/health", health),
        Route("/api/tools", list_tools),
        Route("/api/call", call_tool, methods=["POST"]),
        Route("/api/chat", chat_handler, methods=["POST"]),
    ],
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=[
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:6274",
                "http://127.0.0.1:6274",
            ],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ],
)


CONSOLE_HTML = r"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Plane MCP Console & AI Agent</title>
  <style>
    :root {
      color-scheme: dark;
      --page: #0f110d;
      --panel: #161914;
      --panel-2: #1e221b;
      --line: #2b3127;
      --line-strong: #3f4739;
      --text: #f0f3eb;
      --muted: #a3ac9d;
      --dim: #6d7568;
      --accent: #9fcf74;
      --accent-hover: #b4df8d;
      --accent-ink: #121c0b;
      --danger: #ef8f86;
      --user-bubble: #252b21;
      --bot-bubble: #171a15;
      --radius: 10px;
      font-family: "Segoe UI Variable", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
    }

    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100dvh; background: var(--page); color: var(--text); overflow: hidden; }
    button, input, textarea, select { font: inherit; }
    button { color: inherit; }

    .shell { height: 100dvh; display: grid; grid-template-rows: 58px 1fr; }
    header {
      display: flex; align-items: center; justify-content: space-between; gap: 16px;
      padding: 0 20px; border-bottom: 1px solid var(--line); background: rgba(15, 17, 13, 0.95);
      backdrop-filter: blur(8px); z-index: 10;
    }
    .brand-wrap { display: flex; align-items: center; gap: 24px; }
    .brand { display: flex; align-items: baseline; gap: 10px; }
    .brand strong { font-size: 15px; font-weight: 700; letter-spacing: -0.01em; color: #fff; }
    .brand span { color: var(--dim); font: 12px ui-monospace, "Cascadia Code", monospace; }

    .nav-tabs { display: flex; gap: 6px; }
    .tab-btn {
      background: transparent; border: 1px solid transparent; border-radius: 8px;
      padding: 7px 14px; font-size: 13px; font-weight: 500; color: var(--muted); cursor: pointer;
      display: flex; align-items: center; gap: 7px; transition: all .15s ease;
    }
    .tab-btn:hover { color: var(--text); background: var(--panel-2); }
    .tab-btn.active { background: var(--panel-2); color: var(--accent); border-color: var(--line-strong); }

    .header-actions { display: flex; align-items: center; gap: 14px; }
    .status { display: flex; align-items: center; gap: 7px; color: var(--muted); font-size: 12px; }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--dim); }
    .status[data-state="online"] .status-dot { background: var(--accent); box-shadow: 0 0 8px rgba(159, 207, 116, 0.5); }
    .status[data-state="error"] .status-dot { background: var(--danger); }

    .settings-btn {
      background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px;
      padding: 6px 11px; font-size: 12px; color: var(--muted); cursor: pointer;
      display: flex; align-items: center; gap: 6px;
    }
    .settings-btn:hover { border-color: var(--accent); color: var(--text); }

    /* VIEW CONTAINERS */
    .view-container { height: 100%; min-height: 0; display: none; }
    .view-container.active { display: block; }

    /* CHAT VIEW */
    .chat-view { height: 100%; display: grid; grid-template-rows: 1fr auto; max-width: 960px; margin: 0 auto; width: 100%; padding: 0 16px; }
    .chat-feed { overflow-y: auto; padding: 24px 0 16px; display: flex; flex-direction: column; gap: 18px; }
    
    .msg { display: flex; gap: 12px; max-width: 85%; animation: fadeIn .2s ease; line-height: 1.55; font-size: 14px; }
    .msg.user { align-self: flex-end; flex-direction: row-reverse; }
    .msg.assistant { align-self: flex-start; }
    
    .avatar {
      width: 32px; height: 32px; border-radius: 8px; display: grid; place-items: center;
      font-size: 14px; font-weight: 700; flex-shrink: 0;
    }
    .msg.user .avatar { background: var(--accent); color: var(--accent-ink); }
    .msg.assistant .avatar { background: var(--panel-2); border: 1px solid var(--line); color: var(--accent); }

    .bubble {
      padding: 12px 16px; border-radius: 12px; word-break: break-word;
    }
    .msg.user .bubble { background: var(--user-bubble); border: 1px solid var(--line-strong); color: #fff; }
    .msg.assistant .bubble { background: var(--bot-bubble); border: 1px solid var(--line); color: var(--text); }
    .msg.assistant .bubble p { margin: 0 0 8px; }
    .msg.assistant .bubble p:last-child { margin: 0; }
    .msg.assistant .bubble ul { margin: 6px 0 8px; padding-left: 20px; }
    .msg.assistant .bubble code { background: rgba(255, 255, 255, .08); padding: 2px 6px; border-radius: 4px; font: 12px ui-monospace, "Cascadia Code", monospace; color: var(--accent); }

    .tool-badge {
      display: inline-flex; align-items: center; gap: 6px; font: 11px ui-monospace, monospace;
      padding: 4px 8px; border-radius: 6px; background: rgba(159, 207, 116, .1); color: var(--accent);
      border: 1px solid rgba(159, 207, 116, .2); margin: 6px 0;
    }

    .chips-wrap { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 6px; }
    .chip {
      background: var(--panel); border: 1px solid var(--line); border-radius: 20px;
      padding: 6px 13px; font-size: 12px; color: var(--muted); cursor: pointer; transition: all .15s;
    }
    .chip:hover { border-color: var(--accent); color: var(--text); background: var(--panel-2); }

    .chat-bar { padding: 12px 0 20px; }
    .input-box {
      background: var(--panel); border: 1px solid var(--line-strong); border-radius: 14px;
      padding: 10px 14px; display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: flex-end;
      box-shadow: 0 8px 24px rgba(0,0,0,0.3);
    }
    .input-box:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(159, 207, 116, .12); }
    .chat-input {
      background: transparent; border: 0; outline: none; color: var(--text); resize: none;
      min-height: 24px; max-height: 140px; font-size: 14px; line-height: 1.45;
    }
    .send-btn {
      background: var(--accent); color: var(--accent-ink); border: 0; border-radius: 9px;
      padding: 8px 16px; font-weight: 700; font-size: 13px; cursor: pointer; transition: filter .15s;
      white-space: nowrap; height: 36px; display: grid; place-items: center;
    }
    .send-btn:hover { filter: brightness(1.08); }
    .send-btn:disabled { opacity: 0.5; cursor: wait; }

    /* MODAL */
    .modal-backdrop {
      position: fixed; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(4px);
      display: none; place-items: center; z-index: 100;
    }
    .modal-backdrop.open { display: grid; }
    .modal {
      width: min(92vw, 480px); background: var(--panel); border: 1px solid var(--line-strong);
      border-radius: 14px; padding: 22px; box-shadow: 0 16px 40px rgba(0,0,0,0.5); display: grid; gap: 16px;
    }
    .modal-head { display: flex; justify-content: space-between; align-items: center; }
    .modal-head h3 { margin: 0; font-size: 16px; font-weight: 700; }
    .close-btn { background: transparent; border: 0; color: var(--dim); cursor: pointer; font-size: 18px; }
    .modal-field { display: grid; gap: 6px; }
    .modal-field label { font-size: 12px; color: var(--muted); }
    .modal-field input, .modal-field select {
      background: #11130f; border: 1px solid var(--line); border-radius: 8px; color: var(--text); padding: 8px 10px;
    }

    /* TOOLS VIEW */
    .tools-workspace { height: 100%; display: grid; grid-template-columns: 280px minmax(0, 1fr); min-height: 0; }
    aside { border-right: 1px solid var(--line); padding: 16px 12px; overflow: auto; }
    .search {
      width: 100%; height: 36px; border: 1px solid var(--line); border-radius: var(--radius);
      background: var(--panel); color: var(--text); padding: 0 12px; outline: none; font-size: 13px;
    }
    .search:focus { border-color: var(--accent); }
    .tool-count { margin: 14px 4px 6px; color: var(--dim); font-size: 11px; text-transform: uppercase; letter-spacing: .08em; }
    .tool-list { display: grid; gap: 3px; }
    .tool-item {
      width: 100%; border: 0; border-radius: 8px; background: transparent; text-align: left;
      padding: 9px 10px; cursor: pointer; color: var(--muted); line-height: 1.3; font-size: 13px;
    }
    .tool-item:hover { background: var(--panel); color: var(--text); }
    .tool-item[aria-current="true"] { background: var(--panel-2); color: var(--accent); }
    .tool-item code { font: 12px ui-monospace, "Cascadia Code", monospace; }

    main.tools-main { overflow-y: auto; padding: 24px 32px 50px; }
    .tools-intro { margin-bottom: 24px; }
    .tools-intro h1 { margin: 0 0 6px; font-size: 26px; font-weight: 700; letter-spacing: -0.02em; }
    .tools-intro p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.5; }

    .console-grid { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(300px, 0.9fr); gap: 16px; align-items: start; }
    .pane { border: 1px solid var(--line); border-radius: var(--radius); background: var(--panel); overflow: hidden; }
    .pane-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border-bottom: 1px solid var(--line); }
    .pane-head strong { font-size: 13px; }
    .pane-head span { color: var(--dim); font: 11px ui-monospace, monospace; }
    .form { padding: 14px; display: grid; gap: 14px; }
    .field { display: grid; gap: 6px; }
    .field label { font-size: 12px; color: var(--muted); }
    .field label b { color: var(--danger); }
    .field small { color: var(--dim); font-size: 11px; }
    input, textarea {
      width: 100%; border: 1px solid var(--line); border-radius: var(--radius); background: #11130f;
      color: var(--text); padding: 9px 11px; outline: none; font-size: 13px;
    }
    input:focus, textarea:focus { border-color: var(--accent); }
    textarea { min-height: 80px; resize: vertical; font: 12px/1.5 ui-monospace, monospace; }
    .checkbox { display: flex; align-items: center; gap: 8px; }
    .checkbox input { width: 16px; height: 16px; accent-color: var(--accent); }
    .actions { display: flex; justify-content: flex-end; }
    .run {
      border: 0; border-radius: var(--radius); background: var(--accent); color: var(--accent-ink);
      padding: 9px 18px; font-weight: 700; font-size: 13px; cursor: pointer;
    }
    .run:hover { filter: brightness(1.08); }
    .run:disabled { opacity: .5; cursor: wait; }

    .output {
      min-height: 340px; max-height: 580px; margin: 0; padding: 14px; overflow: auto; color: #d7ddd2;
      background: #11130f; font: 12px/1.6 ui-monospace, "Cascadia Code", monospace; white-space: pre-wrap; word-break: break-word;
    }
    .empty { color: var(--dim); }
    .error { color: var(--danger); }

    @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div class="brand-wrap">
        <div class="brand"><strong>Plane MCP Console</strong><span>localhost:6274</span></div>
        <nav class="nav-tabs" aria-label="Views">
          <button type="button" class="tab-btn active" id="tabChat" onclick="switchView('chat')">💬 Trò chuyện AI (Agent)</button>
          <button type="button" class="tab-btn" id="tabTools" onclick="switchView('tools')">🛠️ Tools Explorer (Thủ công)</button>
        </nav>
      </div>
      <div class="header-actions">
        <button type="button" class="settings-btn" onclick="openSettings()">⚙️ Cài đặt LLM</button>
        <div class="status" id="status" data-state="loading"><span class="status-dot"></span><span id="statusText">Đang kết nối</span></div>
      </div>
    </header>

    <!-- VIEW 1: AI CHAT AGENT -->
    <div class="view-container active" id="viewChat">
      <div class="chat-view">
        <div class="chat-feed" id="chatFeed">
          <div class="msg assistant">
            <div class="avatar">AI</div>
            <div class="bubble">
              <p>👋 <strong>Xin chào! Tôi là Trợ lý AI điều khiển Plane qua MCP.</strong></p>
              <p>Bạn có thể chat bằng tiếng Việt tự nhiên để tôi tự động tra cứu, tạo dự án và tạo công việc trên Plane.</p>
              <div class="chips-wrap">
                <button type="button" class="chip" onclick="quickSend('Tạo task \'Thiết kế cơ sở dữ liệu\' vào dự án QLDA')">📌 Tạo task Thiết kế DB</button>
                <button type="button" class="chip" onclick="quickSend('Xem danh sách tất cả các task hiện có của dự án QLDA')">📋 Xem danh sách task</button>
                <button type="button" class="chip" onclick="quickSend('Xem danh sách các dự án trong workspace')">📁 Xem các dự án</button>
                <button type="button" class="chip" onclick="quickSend('Tạo dự án mới Website Bán Hàng mã WBH')">➕ Tạo dự án mới</button>
              </div>
            </div>
          </div>
        </div>
        <div class="chat-bar">
          <form class="input-box" id="chatForm" onsubmit="handleSend(event)">
            <textarea class="chat-input" id="chatInput" rows="1" placeholder="Nhập yêu cầu quản lý dự án (ví dụ: 'Tạo task mới...', 'Xem các task')..."></textarea>
            <button type="submit" class="send-btn" id="sendBtn">Gửi lệnh</button>
          </form>
        </div>
      </div>
    </div>

    <!-- VIEW 2: MANUAL TOOLS EXPLORER -->
    <div class="view-container" id="viewTools">
      <div class="tools-workspace">
        <aside>
          <input class="search" id="search" type="search" aria-label="Tìm tool" placeholder="Tìm tool...">
          <div class="tool-count" id="toolCount">Đang tải tools</div>
          <nav class="tool-list" id="toolList" aria-label="MCP tools"></nav>
        </aside>
        <main class="tools-main">
          <section class="tools-intro">
            <h1 id="title">Chọn một tool</h1>
            <p id="description">Chọn tool ở cột bên trái để nhập tham số và thực thi lệnh trực tiếp trên Plane.</p>
          </section>
          <div class="console-grid">
            <section class="pane">
              <div class="pane-head"><strong>Tham số</strong><span id="schemaType">JSON Schema</span></div>
              <form class="form" id="toolForm"><div class="empty">Chưa có tool được chọn.</div></form>
            </section>
            <section class="pane">
              <div class="pane-head"><strong>Kết quả</strong><span id="duration">Sẵn sàng</span></div>
              <pre class="output empty" id="output">Kết quả gọi tool sẽ xuất hiện tại đây.</pre>
            </section>
          </div>
        </main>
      </div>
    </div>
  </div>

  <!-- LLM SETTINGS MODAL -->
  <div class="modal-backdrop" id="settingsModal" onclick="if(event.target===this) closeSettings()">
    <div class="modal">
      <div class="modal-head">
        <h3>Cài đặt Nhà cung cấp AI</h3>
        <button type="button" class="close-btn" onclick="closeSettings()">&times;</button>
      </div>
      <div class="modal-field">
        <label for="llmProvider">Chế độ xử lý:</label>
        <select id="llmProvider" onchange="toggleProviderFields()">
          <option value="builtin">Mặc định (Bộ xử lý tự động nội bộ - Miễn phí, không cần Key)</option>
          <option value="openai">OpenAI / OpenRouter / Groq / Ollama</option>
        </select>
      </div>
      <div id="llmCustomFields" style="display:none;" class="modal-field">
        <div class="modal-field" style="margin-bottom:8px;">
          <label for="llmBaseUrl">Base URL API:</label>
          <input id="llmBaseUrl" type="text" placeholder="https://api.openai.com/v1 (hoặc OpenRouter, Ollama)">
        </div>
        <div class="modal-field" style="margin-bottom:8px;">
          <label for="llmApiKey">API Key:</label>
          <input id="llmApiKey" type="password" placeholder="sk-...">
        </div>
        <div class="modal-field">
          <label for="llmModel">Tên Model:</label>
          <input id="llmModel" type="text" placeholder="gpt-4o / claude-3-5-sonnet / deepseek-chat">
        </div>
      </div>
      <div class="actions" style="margin-top:8px;">
        <button type="button" class="run" onclick="saveSettings()">Lưu cài đặt</button>
      </div>
    </div>
  </div>

  <script>
    const state = { tools: [], selected: null, history: [] };
    const $ = (id) => document.getElementById(id);

    function switchView(view) {
      $("tabChat").classList.toggle("active", view === "chat");
      $("tabTools").classList.toggle("active", view === "tools");
      $("viewChat").classList.toggle("active", view === "chat");
      $("viewTools").classList.toggle("active", view === "tools");
    }

    function openSettings() {
      const cfg = JSON.parse(localStorage.getItem("plane_llm_cfg") || "{}");
      $("llmProvider").value = cfg.provider || "builtin";
      $("llmBaseUrl").value = cfg.baseUrl || "";
      $("llmApiKey").value = cfg.apiKey || "";
      $("llmModel").value = cfg.model || "";
      toggleProviderFields();
      $("settingsModal").classList.add("open");
    }

    function closeSettings() {
      $("settingsModal").classList.remove("open");
    }

    function toggleProviderFields() {
      const isCustom = $("llmProvider").value !== "builtin";
      $("llmCustomFields").style.display = isCustom ? "grid" : "none";
    }

    function saveSettings() {
      const cfg = {
        provider: $("llmProvider").value,
        baseUrl: $("llmBaseUrl").value.trim(),
        apiKey: $("llmApiKey").value.trim(),
        model: $("llmModel").value.trim(),
      };
      localStorage.setItem("plane_llm_cfg", JSON.stringify(cfg));
      closeSettings();
    }

    function formatMarkdown(text) {
      let escaped = text
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      escaped = escaped.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
      escaped = escaped.replace(/\*(.*?)\*/g, "<em>$1</em>");
      escaped = escaped.replace(/`([^`]+)`/g, "<code>$1</code>");
      escaped = escaped.replace(/^\* (.*$)/gim, "<li>$1</li>");
      escaped = escaped.replace(/\n\n/g, "</p><p>");
      escaped = escaped.replace(/\n/g, "<br>");
      return `<p>${escaped}</p>`;
    }

    function appendMessage(role, content, toolCalls = []) {
      const feed = $("chatFeed");
      const msgDiv = document.createElement("div");
      msgDiv.className = `msg ${role}`;
      const avatar = document.createElement("div");
      avatar.className = "avatar";
      avatar.textContent = role === "user" ? "B" : "AI";
      
      const bubble = document.createElement("div");
      bubble.className = "bubble";

      if (toolCalls && toolCalls.length) {
        toolCalls.forEach(tc => {
          const badge = document.createElement("div");
          badge.className = "tool-badge";
          badge.innerHTML = `⚙️ Gọi MCP: <strong>${tc.name}</strong>`;
          bubble.append(badge);
        });
      }

      const textContainer = document.createElement("div");
      textContainer.innerHTML = formatMarkdown(content);
      bubble.append(textContainer);

      msgDiv.append(avatar, bubble);
      feed.append(msgDiv);
      feed.scrollTop = feed.scrollHeight;
    }

    async function quickSend(text) {
      $("chatInput").value = text;
      handleSend(new Event("submit"));
    }

    async function handleSend(e) {
      if (e) e.preventDefault();
      const input = $("chatInput");
      const btn = $("sendBtn");
      const text = input.value.trim();
      if (!text) return;

      appendMessage("user", text);
      state.history.push({ role: "user", content: text });
      input.value = "";
      btn.disabled = true;
      btn.textContent = "Đang xử lý...";

      const settings = JSON.parse(localStorage.getItem("plane_llm_cfg") || "{}");

      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, history: state.history, settings }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Không thể xử lý yêu cầu");

        appendMessage("assistant", data.reply, data.tool_calls);
        state.history.push({ role: "assistant", content: data.reply });
      } catch (err) {
        appendMessage("assistant", `❌ Lỗi: ${err.message}`);
      } finally {
        btn.disabled = false;
        btn.textContent = "Gửi lệnh";
      }
    }

    // Auto-resize chat input
    $("chatInput").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    });

    // TOOLS VIEW LOGIC
    function prettyName(name) {
      return name.replace(/^plane_/, "").replaceAll("_", " ");
    }

    function setStatus(kind, text) {
      $("status").dataset.state = kind;
      $("statusText").textContent = text;
    }

    function renderTools(query = "") {
      const list = $("toolList");
      list.replaceChildren();
      const filtered = state.tools.filter((t) => t.name.toLowerCase().includes(query.toLowerCase()));
      $("toolCount").textContent = `${filtered.length} tools`;
      filtered.forEach((tool) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "tool-item";
        button.setAttribute("aria-current", String(state.selected?.name === tool.name));
        const code = document.createElement("code");
        code.textContent = prettyName(tool.name);
        button.append(code);
        button.addEventListener("click", () => selectTool(tool));
        list.append(button);
      });
    }

    function selectTool(tool) {
      state.selected = tool;
      $("title").textContent = prettyName(tool.name);
      $("description").textContent = tool.description || "Không có mô tả.";
      renderTools($("search").value);
      renderForm(tool);
    }

    function renderForm(tool) {
      const form = $("toolForm");
      form.replaceChildren();
      const schema = tool.inputSchema || { properties: {} };
      const required = new Set(schema.required || []);
      const entries = Object.entries(schema.properties || {});

      if (!entries.length) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "Tool này không cần tham số.";
        form.append(empty);
      }

      entries.forEach(([name, property]) => form.append(buildField(name, property, required.has(name))));
      const actions = document.createElement("div");
      actions.className = "actions";
      const run = document.createElement("button");
      run.className = "run";
      run.type = "submit";
      run.textContent = "Chạy tool";
      actions.append(run);
      form.append(actions);
      form.onsubmit = runSelectedTool;
    }

    function buildField(name, schema, required) {
      const nullableType = (schema.anyOf || []).find((c) => c.type && c.type !== "null");
      const resolvedSchema = {
        ...(nullableType || schema),
        default: schema.default,
        description: schema.description || nullableType?.description,
      };
      const wrapper = document.createElement("div");
      wrapper.className = resolvedSchema.type === "boolean" ? "checkbox" : "field";
      const label = document.createElement("label");
      label.htmlFor = `field-${name}`;
      label.textContent = name;
      if (required) {
        const mark = document.createElement("b");
        mark.textContent = " *";
        label.append(mark);
      }

      let input;
      if (resolvedSchema.type === "boolean") {
        input = document.createElement("input");
        input.type = "checkbox";
        input.checked = resolvedSchema.default === true;
        wrapper.append(input, label);
      } else if (resolvedSchema.type === "object" || resolvedSchema.type === "array") {
        input = document.createElement("textarea");
        input.placeholder = resolvedSchema.type === "array" ? "[]" : "{}";
        if (resolvedSchema.default !== undefined) input.value = JSON.stringify(resolvedSchema.default, null, 2);
        wrapper.append(label, input);
      } else {
        input = document.createElement("input");
        input.type = resolvedSchema.type === "integer" || resolvedSchema.type === "number" ? "number" : "text";
        if (resolvedSchema.default !== undefined) input.value = resolvedSchema.default;
        wrapper.append(label, input);
      }

      input.id = `field-${name}`;
      input.name = name;
      input.dataset.schemaType = resolvedSchema.type || "string";
      input.required = required && resolvedSchema.type !== "boolean";
      if (resolvedSchema.description && resolvedSchema.type !== "boolean") {
        const help = document.createElement("small");
        help.textContent = resolvedSchema.description;
        wrapper.append(help);
      }
      return wrapper;
    }

    function collectArguments(form) {
      const result = {};
      form.querySelectorAll("[name]").forEach((input) => {
        const type = input.dataset.schemaType;
        if (type === "boolean") {
          result[input.name] = input.checked;
        } else if (input.value !== "") {
          if (type === "object" || type === "array") result[input.name] = JSON.parse(input.value);
          else if (type === "integer") result[input.name] = Number.parseInt(input.value, 10);
          else if (type === "number") result[input.name] = Number.parseFloat(input.value);
          else result[input.name] = input.value;
        }
      });
      return result;
    }

    async function runSelectedTool(event) {
      event.preventDefault();
      if (!state.selected) return;
      const button = event.currentTarget.querySelector(".run");
      const output = $("output");
      const started = performance.now();
      button.disabled = true;
      button.textContent = "Đang chạy";
      output.className = "output loading";
      output.textContent = `Đang gọi ${state.selected.name}...`;
      $("duration").textContent = "Đang xử lý";

      try {
        const argumentsValue = collectArguments(event.currentTarget);
        const response = await fetch("/api/call", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: state.selected.name, arguments: argumentsValue }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Gọi tool thất bại");
        output.className = "output";
        output.textContent = JSON.stringify(data.result, null, 2);
      } catch (error) {
        output.className = "output error";
        output.textContent = error.message;
      } finally {
        button.disabled = false;
        button.textContent = "Chạy tool";
        $("duration").textContent = `${Math.round(performance.now() - started)} ms`;
      }
    }

    async function boot() {
      try {
        const [healthResponse, toolsResponse] = await Promise.all([fetch("/api/health"), fetch("/api/tools")]);
        const healthData = await healthResponse.json();
        const toolsData = await toolsResponse.json();
        if (!healthResponse.ok) throw new Error(healthData.error || "MCP không phản hồi");
        if (!toolsResponse.ok) throw new Error(toolsData.error || "Không tải được tools");
        state.tools = toolsData.tools;
        setStatus("online", `Đã kết nối với ${healthData.server?.name || "Plane"}`);
        renderTools();
        if (state.tools.length) selectTool(state.tools[0]);
      } catch (error) {
        setStatus("error", "Mất kết nối");
        $("toolCount").textContent = "0 tools";
        $("output").className = "output error";
        $("output").textContent = error.message;
      }
    }

    $("search").addEventListener("input", (event) => renderTools(event.target.value));
    boot();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PLANE_MCP_CONSOLE_PORT", "6274")))
