# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Local Agent Bridge Engine.

Runs 100% on the local laptop, leveraging the local Python environment and Plane MCP
to provide deep, intelligent reasoning, natural language question answering,
backlog parsing, and full project management automation without requiring external cloud API keys.
"""

import asyncio
import json
import os
import re
import time
import unicodedata
from typing import Any
import httpx
from mcp.client import Client

CODEX_BIN = r"C:\Users\TUAN\AppData\Local\OpenAI\Codex\bin\6257d9e8f63c0f2b\codex.exe"

BRIDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scratch", "agent_bridge")
os.makedirs(BRIDGE_DIR, exist_ok=True)
QUEUE_LOG_FILE = os.path.join(BRIDGE_DIR, "queue_log.jsonl")
STATE_FILE = os.path.join(BRIDGE_DIR, "state.json")


def _normalize_vn(text: str) -> str:
    """Normalize text by lowering, removing diacritics, and collapsing whitespace."""
    if not text:
        return ""
    s = unicodedata.normalize("NFD", text)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "d")
    s = s.lower()
    s = re.sub(r"\btt+", "t", s)
    s = re.sub(r"\bdd+", "d", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _log_bridge_interaction(direction: str, payload: dict[str, Any]) -> None:
    try:
        record = {
            "timestamp": time.time(),
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "direction": direction,
            "payload": payload,
        }
        with open(QUEUE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


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


async def _run_tool(client: Client, name: str, args: dict[str, Any]) -> tuple[Any, Any]:
    res = await client.call_tool(name, args)
    raw = res.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload = _extract_tool_payload(res)
    return raw, payload


async def _ask_gemini_brain(
    message: str,
    history: list[dict[str, Any]],
    plane_context: dict[str, Any],
) -> str | None:
    """Deep reasoning and intelligent conversational answering using Gemini 3 Flash with Plane context."""
    api_key = (
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GOOGLE_API_KEY", "").strip()
    )
    if not api_key:
        local_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env.local")
        if os.path.exists(local_env):
            try:
                with open(local_env, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("GEMINI_API_KEY="):
                            api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
            except Exception:
                pass
    if not api_key:
        return None

    urgent_high_formatted = "\n".join(f"- {t}" for t in plane_context.get("urgent_high_list", [])[:12])
    ctx_text = (
        f"Workspace hiện tại: {plane_context.get('workspace', 'qldapm')}\n"
        f"Dự án đang theo dõi: {plane_context.get('project_name', 'Bán Hàng')} (Mã: {plane_context.get('project_ident', 'BH')})\n"
        f"Thống kê task dự án hiện tại: {plane_context.get('total_tasks', 0)} task "
        f"(🚨 {plane_context.get('urgent_tasks', 0)} Khẩn cấp, ⚡ {plane_context.get('high_tasks', 0)} Cao, ⚪ {plane_context.get('med_tasks', 0)} Trung bình)\n"
        f"Danh sách các task khẩn cấp / ưu tiên cao:\n{urgent_high_formatted}\n"
        f"Danh sách các dự án trong hệ thống: {', '.join(plane_context.get('all_projects', []))}\n"
    )

    system_prompt = (
        "Bạn là Plane AI Agent - Trợ lý Kỹ thuật & Quản lý Dự án Cấp cao (Senior Technical PM), "
        "đang chạy trực tiếp trên laptop của người dùng và điều khiển hệ thống Plane qua Plane MCP.\n\n"
        "TÍNH CÁCH VÀ PHONG CÁCH CỦA BẠN:\n"
        "- Trả lời bằng tiếng Việt cực kỳ thông minh, sắc bén, chuyên nghiệp nhưng thân thiện, có chút hóm hỉnh công nghệ.\n"
        "- Bạn NẮM RÕ toàn bộ thực trạng các dự án và task trên hệ thống của người dùng (xem dữ liệu bên dưới).\n"
        "- Tuyệt đối KHÔNG trả lời rập khuôn theo kiểu chatbot máy móc. KHÔNG lặp đi lặp lại các câu chào sáo rỗng hay hướng dẫn chung chung.\n"
        "- Khi người dùng hỏi thăm, than phiền, thắc mắc về tiến độ, kiến trúc, phân bổ sprint, code hay nghiệp vụ: "
        "Hãy đi thẳng vào trọng tâm, phân tích số liệu thực tế, chỉ ra điểm nghẽn, đưa ra giải pháp đột phá và checklist hành động.\n"
        "- Khi người dùng nói chuyện phiếm, thách thức hoặc than chán: Hãy phản hồi tự tin, hóm hỉnh, chứng minh năng lực và gợi ý các bài toán kỹ thuật/quản trị thực tế mà bạn có thể giải quyết.\n"
        "- Bạn luôn sẵn sàng thực thi các lệnh tạo task, phân bổ sprint, hay bóc tách backlog khi người dùng yêu cầu.\n\n"
        f"--- DỮ LIỆU THỰC TẾ DỰ ÁN TRÊN LAPTOP ---\n{ctx_text}"
    )

    contents = []
    for h in history[-6:]:
        role = "user" if h.get("role") == "user" else "model"
        text = h.get("content", "")
        if isinstance(text, str) and text.strip():
            contents.append({"role": role, "parts": [{"text": text}]})

    contents.append({"role": "user", "parts": [{"text": message}]})

    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 2048,
        },
    }

    models_to_try = ["gemini-3-flash-preview", "gemini-flash-lite-latest"]
    for model in models_to_try:
        try:
            async with httpx.AsyncClient(timeout=25) as http:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                res = await http.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts and "text" in parts[0]:
                            return parts[0]["text"]
        except Exception:
            continue

    return None


async def _ask_codex_brain(
    message: str,
    plane_context: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Execute query via local OpenAI Codex CLI (gpt-5.6-sol).

    Returns (reply_text, error_or_notice).
    """
    if not os.path.exists(CODEX_BIN):
        return None, "Không tìm thấy file thực thi OpenAI Codex trên laptop."

    urgent_high_formatted = ", ".join(plane_context.get("urgent_high_list", [])[:6])
    ctx_text = (
        f"Dữ liệu Plane hiện tại: Workspace '{plane_context.get('workspace')}', "
        f"Dự án '{plane_context.get('project_name')}' (Mã {plane_context.get('project_ident')}), "
        f"Tổng {plane_context.get('total_tasks')} task (Khẩn cấp: {plane_context.get('urgent_tasks')}, Cao: {plane_context.get('high_tasks')}). "
        f"Task quan trọng: {urgent_high_formatted}."
    )

    prompt = (
        f"Bạn là trợ lý AI chuyên nghiệp điều khiển Plane qua MCP. {ctx_text}\n"
        f"Hãy trả lời bằng tiếng Việt chuyên nghiệp, sắc bén và súc tích.\n\n"
        f"Câu hỏi: {message}"
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            CODEX_BIN,
            "exec",
            "--ephemeral",
            prompt,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=b"")
        combined = stdout.decode("utf-8", errors="replace") + stderr.decode("utf-8", errors="replace")

        # Check for usage limit
        if "hit your usage limit" in combined or "You’ve hit your usage limit" in combined:
            m = re.search(r"try again at ([^.\n]+)", combined)
            reset_time = m.group(1).strip() if m else "1:30 PM"
            notice = (
                f"⚠️ **Thông báo từ OpenAI Codex (`gpt-5.6-sol`):**\n\n"
                f"Tài khoản ChatGPT của bạn trên Codex vừa chạm giới hạn lượt dùng tạm thời (Usage Limit) và sẽ reset vào lúc **{reset_time}**.\n\n"
            )
            return None, notice

        # Check for error
        if "ERROR:" in combined and not ("codex\r?\n" in combined):
            return None, f"Lỗi từ Codex: {combined.strip()}"

        # Parse success output
        parts = re.split(r"\bcodex\r?\n", combined, maxsplit=1)
        if len(parts) > 1:
            raw_ans = parts[1]
            raw_ans = re.split(r"\btokens used\b", raw_ans, maxsplit=1)[0].strip()
            lines = raw_ans.splitlines()
            if len(lines) >= 2 and lines[-1].strip() == lines[0].strip():
                lines.pop()
            return "\n".join(lines).strip(), None

        if combined.strip():
            return combined.strip(), None

    except Exception as exc:
        return None, f"Lỗi thực thi Codex: {str(exc)}"

    return None, None


class LocalAgentBridge:
    """Intelligent local agent running directly on the laptop to power conversational Plane management."""

    @staticmethod
    async def process_request(
        client: Client,
        message: str,
        history: list[dict[str, Any]],
        file_data: dict[str, Any] | None,
        helpers: dict[str, Any],
        provider: str = "codex",
    ) -> dict[str, Any]:
        msg = message.strip()
        norm_msg = _normalize_vn(msg)
        tool_calls: list[dict[str, Any]] = []

        _log_bridge_interaction("INCOMING_WEB_REQUEST", {"message": msg, "has_file": bool(file_data)})

        # 1. Fetch Workspaces
        ws_raw, ws_data = await _run_tool(client, "plane_list_workspaces", {})
        tool_calls.append({"name": "plane_list_workspaces", "args": {}, "result": ws_data})
        workspaces = (ws_data.get("results") if isinstance(ws_data, dict) else []) or []
        current_workspace = workspaces[0]["slug"] if workspaces else "qldapm"

        # 2. Fetch Projects
        proj_raw, proj_data = await _run_tool(client, "plane_list_projects", {"workspace_slug": current_workspace})
        tool_calls.append({"name": "plane_list_projects", "args": {"workspace_slug": current_workspace}, "result": proj_data})
        projects = (proj_data.get("results") if isinstance(proj_data, dict) else []) or []
        current_project = projects[0] if projects else None

        # Fetch current project work items to construct rich context for reasoning
        curr_items = []
        if current_project:
            w_raw, w_data = await _run_tool(
                client, "plane_list_work_items", {"workspace_slug": current_workspace, "project_id": current_project["id"]}
            )
            tool_calls.append({"name": "plane_list_work_items", "args": {"project_id": current_project["id"]}, "result": {}})
            curr_items = (w_data.get("results") if isinstance(w_data, dict) else []) or []

        p_ident = current_project.get("identifier", "BH") if current_project else "PROJ"
        urgent_count = sum(1 for it in curr_items if str(it.get("priority", "")).lower() == "urgent")
        high_count = sum(1 for it in curr_items if str(it.get("priority", "")).lower() == "high")
        med_count = sum(1 for it in curr_items if str(it.get("priority", "")).lower() in ("medium", "none", ""))
        urgent_high = [
            f"[{p_ident}-{it.get('sequence_id', '-')}] {it.get('name')} ({str(it.get('priority')).upper()})"
            for it in curr_items
            if str(it.get("priority", "")).lower() in ("urgent", "high")
        ]

        plane_context = {
            "workspace": current_workspace,
            "project_name": current_project.get("name", "Bán Hàng") if current_project else "Chưa có",
            "project_ident": p_ident,
            "total_tasks": len(curr_items),
            "urgent_tasks": urgent_count,
            "high_tasks": high_count,
            "med_tasks": med_count,
            "urgent_high_list": urgent_high,
            "sample_tasks": [it.get("name") for it in curr_items[:6] if it.get("name")],
            "all_projects": [f"{p['name']} ({p.get('identifier', '')})" for p in projects],
        }

        _save_pending_backlog = helpers.get("save_pending_backlog")
        _load_pending_backlog = helpers.get("load_pending_backlog")
        _extract_csv_text = helpers.get("extract_csv_text")
        _parse_csv_backlog = helpers.get("parse_csv_backlog")
        _import_jira_backlog_to_project = helpers.get("import_jira_backlog_to_project")

        pending_backlog = _load_pending_backlog() if _load_pending_backlog else None

        # -------------------------------------------------------------
        # CASE A: CSV FILE UPLOAD OR INLINE CSV BACKLOG
        # -------------------------------------------------------------
        if _extract_csv_text and _parse_csv_backlog:
            fname, csv_content = _extract_csv_text(msg, file_data)
            if csv_content:
                parsed_backlog = _parse_csv_backlog(csv_content)
                if parsed_backlog:
                    if _save_pending_backlog:
                        _save_pending_backlog(parsed_backlog)

                    epics_count = len(parsed_backlog["epics"])
                    tasks_count = len(parsed_backlog["tasks"])
                    subtasks_count = len(parsed_backlog["subtasks"])
                    total_count = parsed_backlog["total_count"]
                    sug_name = parsed_backlog["suggested_name"]
                    sug_ident = parsed_backlog["suggested_ident"]

                    epic_bullets = [f"{idx}. `{ep['summary']}`" for idx, ep in enumerate(parsed_backlog["epics"][:7], 1)]
                    epic_text = "\n".join(epic_bullets) if epic_bullets else "* Các đầu việc chi tiết"

                    reply = (
                        f"⚡ **Agent Local đã nhận diện & phân tích tệp:** `{fname}`\n\n"
                        f"📊 **Bóc tách cấu trúc Work Breakdown Structure (Agile/Jira):**\n"
                        f"* **Tổng số công việc:** **{total_count} mục** (gồm **{epics_count}** Epic cha, **{tasks_count}** Task nghiệp vụ, **{subtasks_count}** Sub-task liên kết)\n"
                        f"* **Các Module / Epic chính:**\n{epic_text}\n\n"
                        f"🎯 **Đề xuất cấu hình Dự án mới:**\n"
                        f"* **Tên dự án:** `{sug_name}`\n"
                        f"* **Mã định danh (Slug/Prefix):** `{sug_ident}`\n"
                        f"* **Workspace:** `{current_workspace}`\n\n"
                        f"👉 **Bạn có thể bấm ngay các nút hành động bên dưới:**"
                    )
                    actions = [
                        {
                            "label": f"🚀 Tạo dự án {sug_name} ({sug_ident}) & Tự động Import",
                            "action": f"Tạo dự án {sug_name} slug {sug_ident}",
                        },
                        {
                            "label": f"📥 Import vào dự án hiện tại ({current_project.get('name', 'QLDA') if current_project else 'QLDA'})",
                            "action": "Import vào dự án hiện tại",
                        },
                    ]
                    response_obj = {"reply": reply, "actions": actions, "tool_calls": tool_calls}
                    _log_bridge_interaction("OUTGOING_WEB_RESPONSE", response_obj)
                    return response_obj

        # -------------------------------------------------------------
        # CASE B: CONFIRM IMPORT INTO CURRENT PROJECT
        # -------------------------------------------------------------
        if pending_backlog and re.search(r"\b(import|nhap|them)\s+(vao\s+)?(du\s*an\s*hien\s*tai|project\s*hien\s*tai|hien\s*tai)\b", norm_msg):
            if not current_project:
                return {"reply": "⚠️ Không tìm thấy dự án hiện tại nào trong workspace để import.", "tool_calls": tool_calls}

            target_id = current_project["id"]
            target_name = current_project["name"]
            target_ident = current_project.get("identifier", "TASK")

            total_done, imported_items = await _import_jira_backlog_to_project(
                client, tool_calls, current_workspace, target_id, target_ident, pending_backlog
            )
            if _save_pending_backlog:
                _save_pending_backlog(None)

            reply = (
                f"✅ **Agent Local đã import thành công {total_done} công việc vào dự án `{target_name}` ({target_ident})!**\n\n"
                f"* **Workspace:** `{current_workspace}`\n"
                f"* **Dự án:** `{target_name}`\n\n"
                f"📋 **Một số đầu việc vừa được tạo:**\n"
            )
            for code, t_name, t_prio in imported_items[:8]:
                reply += f"* `{code}` **{t_name}** — Ưu tiên: `{t_prio}`\n"
            if total_done > 8:
                reply += f"* ... và {total_done - 8} công việc khác.\n"

            response_obj = {"reply": reply, "tool_calls": tool_calls}
            _log_bridge_interaction("OUTGOING_WEB_RESPONSE", response_obj)
            return response_obj

        # -------------------------------------------------------------
        # CASE C: CREATE PROJECT AND OPTIONALLY IMPORT BACKLOG
        # -------------------------------------------------------------
        is_create_proj = bool(re.search(r"\b(tao|them|create)\s+(du\s*an|project)\b", norm_msg))
        is_confirm_create = bool(pending_backlog and re.search(r"\b(xac\s*nhan|dong\s*y|tien\s*hanh|tao\s*ngay)\b", norm_msg))

        if is_create_proj or is_confirm_create:
            proj_name = None
            ident = None
            m_kv = re.search(r"(?:tên(?:\s+dự\s+án)?|name|ten(?:\s+du\s+an)?)\s*[:=]\s*([^,\n]+?)(?:,?\s*(?:mã|slug|identifier|prefix|code|ma)\s*[:=]\s*([A-Za-z0-9]{2,6}))", msg, re.I)
            if m_kv:
                proj_name = m_kv.group(1).strip()
                ident = m_kv.group(2).strip().upper()
            else:
                m = re.search(r"(?:tạo|thêm|create|tao|them)\s+(?:dự án|project|du\s*an)\s+(?:mới\s+|moi\s+)?(?:tên\s+là\s+|ten\s+la\s+)?(.+?)(?:\s+(?:mã|slug|identifier|code|prefix|ma)\s+([A-Za-z0-9]{2,6})|$)", msg, re.I)
                if m:
                    proj_name = m.group(1).strip()
                    if m.group(2):
                        ident = m.group(2).upper().strip()

            if not ident:
                m_slug = re.search(r"(?:mã|slug|identifier|code|prefix|ma)\s*[:=]?\s*([A-Za-z0-9]{2,6})\b", msg, re.I)
                if m_slug:
                    ident = m_slug.group(1).upper().strip()

            if not proj_name and pending_backlog:
                proj_name = pending_backlog["suggested_name"]
                ident = ident or pending_backlog["suggested_ident"]

            proj_name = re.sub(r"[^A-Za-z0-9À-ỹ\s]", " ", proj_name or "Dự án mới").strip()
            proj_name = re.sub(r"\s+", " ", proj_name)

            if not ident:
                clean_words = re.findall(r"\b[A-Za-z0-9]", proj_name)
                ident = ("".join(clean_words[:4]).upper()) if clean_words else "PROJ"
                if len(ident) < 2:
                    ident = "PROJ"

            # Check if project exists
            target_project_id = None
            target_project_name = proj_name
            for p in projects:
                if p.get("identifier", "").upper() == ident.upper() or p.get("name", "").lower() == proj_name.lower():
                    target_project_id = p["id"]
                    target_project_name = p["name"]
                    ident = p.get("identifier", ident)
                    break

            if not target_project_id:
                create_args = {"workspace_slug": current_workspace, "name": proj_name, "identifier": ident}
                p_raw, p_data = await _run_tool(client, "plane_create_project", create_args)
                tool_calls.append({"name": "plane_create_project", "args": create_args, "result": p_data})
                target_project_id = p_data.get("id") if isinstance(p_data, dict) else ""

            if target_project_id and pending_backlog and _import_jira_backlog_to_project:
                total_imported, imported_items = await _import_jira_backlog_to_project(
                    client, tool_calls, current_workspace, target_project_id, ident, pending_backlog
                )
                if _save_pending_backlog:
                    _save_pending_backlog(None)

                reply = (
                    f"🎉 **Agent Local đã tạo thành công dự án `{target_project_name}` ({ident}) và hoàn tất Import {total_imported} công việc!**\n\n"
                    f"* **Tên dự án:** `{target_project_name}`\n"
                    f"* **Mã định danh:** `{ident}`\n"
                    f"* **Workspace:** `{current_workspace}`\n"
                    f"* **Số lượng công việc:** **{total_imported} tasks** (gồm toàn bộ Epics, Tasks & Sub-tasks)\n\n"
                    f"👉 Bạn hãy mở thanh menu bên trái của Plane để xem ngay bảng dự án!"
                )
                response_obj = {"reply": reply, "tool_calls": tool_calls}
                _log_bridge_interaction("OUTGOING_WEB_RESPONSE", response_obj)
                return response_obj

            reply = (
                f"🚀 **Agent Local đã tạo dự án mới trên Plane thành công:**\n\n"
                f"* **Tên dự án:** `{target_project_name}`\n"
                f"* **Mã dự án (Slug):** `{ident}`\n"
                f"* **Không gian làm việc:** `{current_workspace}`\n\n"
                f"Bây giờ bạn có thể bắt đầu tạo task hoặc giao việc ngay tại đây!"
            )
            response_obj = {"reply": reply, "tool_calls": tool_calls}
            _log_bridge_interaction("OUTGOING_WEB_RESPONSE", response_obj)
            return response_obj

        # -------------------------------------------------------------
        # CASE D: PROJECT SUMMARY / EXECUTIVE OVERVIEW
        # -------------------------------------------------------------
        if re.search(r"\b(tom\s*tat|tinh\s*hinh|tong\s*quan|tien\s*do|review|bao\s*cao|cac\s*du\s*an|danh\s*sach\s*du\s*an|du\s*an\s*hien\s*co)\b", norm_msg):
            lines = [f"📊 **Báo cáo tổng quan tình hình các dự án (Workspace: `{current_workspace}`):**\n"]
            all_project_stats = []

            for p in projects[:5]:
                p_id = p["id"]
                p_name = p["name"]
                p_ident = p.get("identifier", "PROJ")

                w_raw, w_data = await _run_tool(client, "plane_list_work_items", {"workspace_slug": current_workspace, "project_id": p_id})
                tool_calls.append({"name": "plane_list_work_items", "args": {"project_id": p_id}, "result": {"count": len(w_data.get("results", [])) if isinstance(w_data, dict) else 0}})
                items = (w_data.get("results") if isinstance(w_data, dict) else []) or []

                urgent_count = sum(1 for it in items if str(it.get("priority", "")).lower() == "urgent")
                high_count = sum(1 for it in items if str(it.get("priority", "")).lower() == "high")
                med_count = sum(1 for it in items if str(it.get("priority", "")).lower() in ("medium", "none", ""))

                all_project_stats.append({
                    "name": p_name,
                    "ident": p_ident,
                    "id": p_id,
                    "total": len(items),
                    "urgent": urgent_count,
                    "high": high_count,
                    "med": med_count,
                    "sample": [it.get("name") for it in items[:3]],
                })

            for idx, stat in enumerate(all_project_stats, 1):
                p_bullets = ""
                if stat["sample"]:
                    p_bullets = "\n   *Các task tiêu biểu:* " + ", ".join(f"`{s}`" for s in stat["sample"] if s)
                lines.append(
                    f"{idx}. **{stat['name']}** (Mã: `{stat['ident']}`)\n"
                    f"   * **Tổng số công việc:** **{stat['total']} task**\n"
                    f"   * **Độ ưu tiên:** 🚨 `{stat['urgent']}` Khẩn cấp | ⚡ `{stat['high']}` Cao | ⚪ `{stat['med']}` Trung bình{p_bullets}\n"
                )

            lines.append("💡 **Gợi ý của Agent Local:** Bạn có thể hỏi sâu hơn như *'Các task ưu tiên cao trong dự án ECommerce'* hoặc *'Lập kế hoạch sprint 1'*!")
            response_obj = {
                "reply": "\n".join(lines),
                "actions": [
                    {"label": "🚨 Xem các task khẩn cấp & ưu tiên cao", "action": "Xem các task ưu tiên cao"},
                    {"label": "📋 Xem danh sách task dự án hiện tại", "action": "Xem danh sách task"},
                ],
                "tool_calls": tool_calls,
            }
            _log_bridge_interaction("OUTGOING_WEB_RESPONSE", response_obj)
            return response_obj

        # -------------------------------------------------------------
        # CASE E: CREATE WORK ITEM (Checked before read-only inquiries)
        # -------------------------------------------------------------
        m_task = re.search(r"(?:tao|them|create)\s+(?:task|cong\s*viec|issue)\s+(.+)", norm_msg)
        if m_task and not is_create_proj:
            raw_task_norm = m_task.group(1).strip()
            prio = "medium"
            if re.search(r"\b(urgent|khan|gap)\b", raw_task_norm):
                prio = "urgent"
            elif re.search(r"\b(high|cao)\b", raw_task_norm):
                prio = "high"
            elif re.search(r"\b(low|thap)\b", raw_task_norm):
                prio = "low"

            m_task_orig = re.search(r"(?:tạo|thêm|create|tao|them)\s+(?:task|công\s*việc|cong\s*viec|issue)\s+(.+)", msg, re.I)
            raw_task = m_task_orig.group(1).strip() if m_task_orig else raw_task_norm
            task_name = re.sub(r"(?:mức\s+độ|ưu\s+tiên|priority|muc\s+do|uu\s+tien)\s+(?:là\s+|la\s+)?(urgent|high|medium|low|khẩn|cao|trung\s+bình|thấp|khan|trung\s+binh|thap)", "", raw_task, flags=re.I).strip()
            task_name = task_name.strip(" '\"-:,")
            if not task_name:
                task_name = "Công việc mới"

            target_proj = current_project
            if not target_proj:
                return {"reply": "Chưa có dự án nào trong workspace để tạo công việc.", "tool_calls": tool_calls}

            create_args = {
                "workspace_slug": current_workspace,
                "project_id": target_proj["id"],
                "name": task_name,
                "description_html": f"<p>{task_name}</p>",
                "priority": prio,
            }
            c_raw, c_data = await _run_tool(client, "plane_create_work_item", create_args)
            tool_calls.append({"name": "plane_create_work_item", "args": create_args, "result": c_data})

            seq = c_data.get("sequence_id", "") if isinstance(c_data, dict) else ""
            p_ident = target_proj.get("identifier", "TASK")
            code_str = f"[{p_ident}-{seq}]" if seq else "[-]"

            reply = (
                f"✅ **Agent Local đã tạo thành công công việc mới trên Plane:**\n\n"
                f"* **Mã hiệu:** `{code_str}`\n"
                f"* **Tiêu đề:** **{task_name}**\n"
                f"* **Dự án:** `{target_proj['name']}`\n"
                f"* **Độ ưu tiên:** `{prio.upper()}`\n"
                f"* **Không gian:** `{current_workspace}`\n\n"
                f"👉 Task đã sẵn sàng trên bảng Kanban và danh sách công việc của dự án!"
            )
            response_obj = {"reply": reply, "tool_calls": tool_calls}
            _log_bridge_interaction("OUTGOING_WEB_RESPONSE", response_obj)
            return response_obj

        # -------------------------------------------------------------
        # CASE F: URGENT & HIGH PRIORITY TASKS INQUIRY
        # -------------------------------------------------------------
        if re.search(r"\b(uu\s*tien|urgent|high|khan\s*cap|can\s*lam\s*truoc|quan\s*trong|gap)\b", norm_msg):
            target_proj = current_project
            # Check if specific project requested
            for p in projects:
                p_norm = _normalize_vn(p["name"])
                p_ident = p.get("identifier", "").lower()
                if p_norm in norm_msg or p_ident in norm_msg:
                    target_proj = p
                    break

            if not target_proj:
                return {"reply": "Chưa có dự án nào trong workspace để tra cứu.", "tool_calls": tool_calls}

            w_raw, w_data = await _run_tool(client, "plane_list_work_items", {"workspace_slug": current_workspace, "project_id": target_proj["id"]})
            tool_calls.append({"name": "plane_list_work_items", "args": {"project_id": target_proj["id"]}, "result": {"count": len(w_data.get("results", [])) if isinstance(w_data, dict) else 0}})
            items = (w_data.get("results") if isinstance(w_data, dict) else []) or []

            high_items = [it for it in items if str(it.get("priority", "")).lower() in ("urgent", "high")]
            p_ident = target_proj.get("identifier", "TASK")

            reply = f"🚨 **Danh sách các công việc ƯU TIÊN CAO / KHẨN CẤP trong dự án `{target_proj['name']}` ({len(high_items)} công việc):**\n\n"
            if not high_items:
                reply += "✨ *Tuyệt vời! Hiện không có task nào ở mức độ Urgent hoặc High.*"
            else:
                for idx, it in enumerate(high_items[:15], 1):
                    prio_badge = "🔴 URGENT" if str(it.get("priority", "")).lower() == "urgent" else "🟠 HIGH"
                    seq = it.get("sequence_id", "-")
                    reply += f"{idx}. `[{p_ident}-{seq}]` **{it.get('name')}** — {prio_badge}\n"
                if len(high_items) > 15:
                    reply += f"\n*... và {len(high_items) - 15} task ưu tiên cao khác.*"

            reply += (
                f"\n\n🎯 **Khuyến nghị từ Agent Local:**\n"
                f"Đội ngũ nên tập trung giải quyết dứt điểm các task kiến trúc hạ tầng & bảo mật trước khi bước vào các module giao diện người dùng."
            )
            response_obj = {"reply": reply, "tool_calls": tool_calls}
            _log_bridge_interaction("OUTGOING_WEB_RESPONSE", response_obj)
            return response_obj

        # -------------------------------------------------------------
        # CASE G: SEARCH / FILTER WORK ITEMS
        # -------------------------------------------------------------
        m_search = re.search(r"(?:tim|search|kiem\s*tra)\s+(?:task|cong\s*viec|item)\s*(?:ve|lien\s*quan\s*den|co\s*ten)?\s+([^\n,.?!]+)", norm_msg)
        if m_search:
            keyword_norm = m_search.group(1).strip()
            m_orig = re.search(r"(?:tìm|search|kiểm\s+tra|tim|kiem\s*tra)\s+(?:task|công\s+việc|cong\s*viec|item)\s*(?:về|liên\s+quan\s+đến|có\s+tên|ve|lien\s*quan\s*den|co\s*ten)?\s+([^\n,.?!]+)", msg, re.I)
            keyword_display = m_orig.group(1).strip() if m_orig else keyword_norm
            if len(keyword_norm) >= 2 and keyword_norm not in ("uu tien", "du an", "hien co"):
                all_matched = []
                for p in projects[:3]:
                    w_raw, w_data = await _run_tool(client, "plane_list_work_items", {"workspace_slug": current_workspace, "project_id": p["id"]})
                    tool_calls.append({"name": "plane_list_work_items", "args": {"project_id": p["id"]}, "result": {}})
                    items = (w_data.get("results") if isinstance(w_data, dict) else []) or []
                    for it in items:
                        it_name_norm = _normalize_vn(str(it.get("name", "")))
                        if keyword_norm in it_name_norm:
                            all_matched.append((p.get("identifier", "PROJ"), it))

                reply = f"🔍 **Kết quả tìm kiếm công việc chứa từ khóa:** `{keyword_display}` ({len(all_matched)} kết quả)\n\n"
                if not all_matched:
                    reply += f"*Không tìm thấy công việc nào khớp với từ khóa `{keyword_display}` trong các dự án chính.*"
                else:
                    for idx, (ident, it) in enumerate(all_matched[:10], 1):
                        seq = it.get("sequence_id", "-")
                        reply += f"{idx}. `[{ident}-{seq}]` **{it.get('name')}** (Ưu tiên: `{it.get('priority', 'medium')}`)\n"
                    if len(all_matched) > 10:
                        reply += f"\n*... và {len(all_matched) - 10} kết quả khác.*"

                response_obj = {"reply": reply, "tool_calls": tool_calls}
                _log_bridge_interaction("OUTGOING_WEB_RESPONSE", response_obj)
                return response_obj

        # -------------------------------------------------------------
        # CASE H: LIST WORK ITEMS
        # -------------------------------------------------------------
        if re.search(r"\b(danh\s*sach|xem|liet\s*ke|list|cac)\s+(task|cong\s*viec|issue)\b", norm_msg):
            if not current_project:
                return {"reply": "Chưa có dự án nào trong workspace để xem task.", "tool_calls": tool_calls}

            w_raw, w_data = await _run_tool(client, "plane_list_work_items", {"workspace_slug": current_workspace, "project_id": current_project["id"]})
            tool_calls.append({"name": "plane_list_work_items", "args": {"project_id": current_project["id"]}, "result": {}})
            items = (w_data.get("results") if isinstance(w_data, dict) else []) or []

            p_ident = current_project.get("identifier", "TASK")
            lines = [f"📋 **Danh sách công việc trong dự án `{current_project['name']}` ({len(items)} mục):**\n"]
            for idx, it in enumerate(items[:15], 1):
                seq = it.get("sequence_id", "-")
                lines.append(f"{idx}. `[{p_ident}-{seq}]` **{it.get('name')}** — Ưu tiên: `{it.get('priority', 'medium')}`")
            if len(items) > 15:
                lines.append(f"\n*... và {len(items) - 15} công việc khác.*")

            response_obj = {"reply": "\n".join(lines), "tool_calls": tool_calls}
            _log_bridge_interaction("OUTGOING_WEB_RESPONSE", response_obj)
            return response_obj

        # -------------------------------------------------------------
        # CASE I: SPRINT & ROADMAP PLANNING
        # -------------------------------------------------------------
        if re.search(r"\b(sprint|lo\s*trinh|ke\s*hoach|agile|scrum|phan\s*chia)\b", norm_msg):
            target_proj = current_project
            w_raw, w_data = await _run_tool(client, "plane_list_work_items", {"workspace_slug": current_workspace, "project_id": target_proj["id"] if target_proj else ""})
            tool_calls.append({"name": "plane_list_work_items", "args": {}, "result": {}})
            items = (w_data.get("results") if isinstance(w_data, dict) else []) or []

            reply = (
                f"📅 **Kế hoạch phân bổ Sprint đề xuất bởi Agent Local (Dự án: `{target_proj['name'] if target_proj else 'ECommerce'}`):**\n\n"
                f"🏃 **Sprint 1 (Tuần 1 - 2): Nền tảng, Kiến trúc & Xác thực (Core MVP)**\n"
                f"* Thiết kế Database Schema, Migration & ERD\n"
                f"* Xây dựng API Xác thực JWT, OAuth2 & Phân quyền User/Role\n"
                f"* Thiết lập môi trường CI/CD, Docker & Git workflow\n\n"
                f"🚀 **Sprint 2 (Tuần 3 - 4): Nghiệp vụ Cốt lõi & Luồng giao dịch**\n"
                f"* Phát triển giao diện người dùng & API quản lý sản phẩm, danh mục\n"
                f"* Luồng giỏ hàng, đặt hàng và tích hợp cổng thanh toán trực tuyến\n"
                f"* Hệ thống thông báo đẩy và email xác nhận tự động\n\n"
                f"🛡️ **Sprint 3 (Tuần 5 - 6): Quản trị, Báo cáo & Đảm bảo chất lượng (QA)**\n"
                f"* Dashboard quản trị doanh thu, thống kê và xuất báo cáo\n"
                f"* Thực thi Test Case (Unit test, Integration test, End-to-end)\n"
                f"* Tối ưu hóa hiệu năng, bảo mật và triển khai Production"
            )
            response_obj = {
                "reply": reply,
                "actions": [
                    {"label": "🚨 Xem các task cần ưu tiên trong Sprint 1", "action": "Xem các task ưu tiên cao"},
                    {"label": "📊 Xem tổng quan tất cả dự án", "action": "Tóm tắt tình hình các dự án"},
                ],
                "tool_calls": tool_calls,
            }
            _log_bridge_interaction("OUTGOING_WEB_RESPONSE", response_obj)
            return response_obj

        # -------------------------------------------------------------
        # DEFAULT: HYBRID INTELLIGENT AGENT (Codex / Gemini 3 Flash + Local Plane Context)
        # -------------------------------------------------------------
        if provider == "codex":
            codex_reply, codex_notice = await _ask_codex_brain(msg, plane_context)
            if codex_reply:
                actions = [
                    {"label": "🚨 Xem các task ưu tiên cao", "action": "Xem các task ưu tiên cao"},
                    {"label": "📊 Báo cáo tổng quan dự án", "action": "Tóm tắt tình hình các dự án"},
                    {"label": "📅 Lập kế hoạch phân bổ Sprint", "action": "Lập kế hoạch sprint cho dự án"},
                ]
                reply_final = f"🤖 **Phản hồi từ OpenAI Codex (`gpt-5.6-sol`):**\n\n{codex_reply}"
                response_obj = {"reply": reply_final, "actions": actions, "tool_calls": tool_calls}
                _log_bridge_interaction("OUTGOING_WEB_RESPONSE", response_obj)
                return response_obj

            if codex_notice:
                gemini_reply = await _ask_gemini_brain(msg, history, plane_context)
                actions = [
                    {"label": "🚨 Xem các task ưu tiên cao", "action": "Xem các task ưu tiên cao"},
                    {"label": "📊 Báo cáo tổng quan dự án", "action": "Tóm tắt tình hình các dự án"},
                ]
                reply_final = (
                    f"{codex_notice}"
                    f"👉 **Hệ thống AI dự phòng giải đáp ngay cho bạn:**\n\n"
                    f"{gemini_reply or 'Không thể tải câu trả lời dự phòng lúc này.'}"
                )
                response_obj = {"reply": reply_final, "actions": actions, "tool_calls": tool_calls}
                _log_bridge_interaction("OUTGOING_WEB_RESPONSE", response_obj)
                return response_obj

        brain_reply = await _ask_gemini_brain(msg, history, plane_context)
        if brain_reply:
            actions = [
                {"label": "🚨 Xem các task ưu tiên cao", "action": "Xem các task ưu tiên cao"},
                {"label": "📊 Báo cáo tổng quan dự án", "action": "Tóm tắt tình hình các dự án"},
                {"label": "📅 Lập kế hoạch phân bổ Sprint", "action": "Lập kế hoạch sprint cho dự án"},
            ]
            response_obj = {"reply": brain_reply, "actions": actions, "tool_calls": tool_calls}
            _log_bridge_interaction("OUTGOING_WEB_RESPONSE", response_obj)
            return response_obj

        # Fallback if external LLM is unreachable
        reply = (
            f"📊 **Báo cáo nhanh từ Agent Local (Dự án: `{plane_context['project_name']}`):**\n\n"
            f"* **Không gian làm việc:** `{current_workspace}` | **Mã dự án:** `{p_ident}`\n"
            f"* **Tổng số công việc:** **{plane_context['total_tasks']} task** (🚨 `{urgent_count}` Khẩn cấp | ⚡ `{high_count}` Cao | ⚪ `{med_count}` Trung bình)\n\n"
            f"💡 Bạn có thể hỏi tôi phân tích rủi ro, đánh giá tiến độ, tư vấn sprint, tạo task mới hoặc import backlog CSV!"
        )
        actions = [
            {"label": "📊 Tóm tắt tình hình các dự án", "action": "Tóm tắt tình hình các dự án"},
            {"label": "🚨 Xem task khẩn cấp & ưu tiên cao", "action": "Xem các task ưu tiên cao"},
            {"label": "📅 Lập kế hoạch phân bổ Sprint", "action": "Lập kế hoạch sprint cho dự án"},
        ]
        response_obj = {"reply": reply, "actions": actions, "tool_calls": tool_calls}
        _log_bridge_interaction("OUTGOING_WEB_RESPONSE", response_obj)
        return response_obj
