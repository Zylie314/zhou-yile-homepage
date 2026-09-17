#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
个人主页数字分身后端服务

职责：
  1. 托管个人主页静态文件（index.html 及各版本归档）
  2. 提供 POST /api/chat 接口，代理调用 DeepSeek 真实模型

用法：
  python server.py          # 默认 0.0.0.0:8000
  python server.py 9000     # 指定端口

API Key 读取优先级：
  环境变量 DEEPSEEK_API_KEY > 同目录 .env 文件中的 DEEPSEEK_API_KEY
"""

import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

# 数字分身人设系统提示词
SYSTEM_PROMPT = (
    "你是「周亦乐」的数字分身，请以第一人称扮演周亦乐本人，帮他回答访客的问题。\n"
    "\n"
    "【关于周亦乐】\n"
    "- 身份：大学生，正在用学习去感知智能信息时代。\n"
    "- 近期关注的方向：AI 应用、内容表达、知识整理。\n"
    "- 兴趣：游戏、音乐、诗词。\n"
    "- 性格特点：喜欢简明扼要、富有逻辑的对话。\n"
    "- 其他：擅长时间管理、计算机学习，正在学习如何正确利用 AI。\n"
    "\n"
    "【语言风格要求】\n"
    "- 语言幽默，思维跳脱但又富有逻辑。\n"
    "- 回答简洁、像人说人话，不要官方腔、不要堆砌术语。\n"
    "- 擅长把复杂问题讲清楚，能用打比方的方式让人秒懂。\n"
    "- 每轮回复控制在 2~4 句话左右，除非对方明确要详细解释。\n"
    "\n"
    "【注意】\n"
    "- 只以周亦乐的口吻回答，不要暴露自己是 AI 或模型。\n"
    "- 涉及你没把握的个人隐私时，坦率说不知道，别编造。\n"
    "- 中文回答。"
)


def load_api_key():
    """优先读环境变量，其次读 .env 文件。"""
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key

    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == "DEEPSEEK_API_KEY":
                    return v.strip().strip('"').strip("'")
    return ""


def load_supabase_config():
    """优先读环境变量，其次读 .env 文件，返回 (SUPABASE_URL, SUPABASE_ANON_KEY)。"""
    url = os.environ.get("SUPABASE_URL", "").strip()
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if url and anon_key:
        return url, anon_key

    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                if k == "SUPABASE_URL" and not url:
                    url = v.strip().strip('"').strip("'")
                elif k == "SUPABASE_ANON_KEY" and not anon_key:
                    anon_key = v.strip().strip('"').strip("'")
    return url, anon_key


# 反馈数据：追加写入 JSONL，每条含提交时间与页面版本（反馈内容不公开，文件已加入 .gitignore）
FEEDBACK_VERSION = "v3.1"  # 当前页面版本；归档新版本时同步更新
FEEDBACK_FILE = os.path.join(BASE_DIR, "feedback.jsonl")


API_KEY = load_api_key()
SUPABASE_URL, SUPABASE_ANON_KEY = load_supabase_config()


def call_deepseek_stream(messages):
    """以流式方式调用 DeepSeek，逐段 yield 增量文本。

    使用 stream=True，响应为 SSE 格式（每行 data: {...}），
    增量内容位于 choices[0].delta.content。
    """
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": 800,
        "stream": True,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + API_KEY,
        },
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=120)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError("DeepSeek HTTP %s: %s" % (e.code, detail[:500]))
    except urllib.error.URLError as e:
        raise RuntimeError("无法连接 DeepSeek：%s" % e.reason)

    with resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                obj = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            choices = obj.get("choices") or []
            if not choices:
                continue
            piece = (choices[0].get("delta") or {}).get("content")
            if piece:
                yield piece


def insert_feedback_supabase(record):
    """写入 Supabase feedback 表，返回 (status_code, error_detail)。

    使用 anon key（最小权限），依赖表的 RLS 策略允许 anon 插入。
    """
    url = SUPABASE_URL.rstrip("/") + "/rest/v1/feedback"
    data = json.dumps(record).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": "Bearer " + SUPABASE_ANON_KEY,
            "Prefer": "return=minimal",
        },
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.status, None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        return e.code, detail[:500]
    except urllib.error.URLError as e:
        return None, "无法连接 Supabase：%s" % e.reason


def save_feedback_local(record):
    """回退方案：写入本地 feedback.jsonl（含提交时间）。"""
    local = dict(record)
    local["time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(local, ensure_ascii=False) + "\n")


class Handler(BaseHTTPRequestHandler):
    server_version = "HomepageServer/1.0"

    def log_message(self, fmt, *args):  # 静默日志，减少终端刷屏
        pass

    # ---------- 响应工具 ----------
    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False),
                   "application/json; charset=utf-8")

    # ---------- 静态文件 ----------
    def _serve_static(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            path = "/index.html"
        # 防目录穿越
        rel = path.lstrip("/")
        target = os.path.normpath(os.path.join(BASE_DIR, rel))
        if not target.startswith(BASE_DIR) or not os.path.isfile(target):
            self._send(404, "Not Found")
            return

        ext = os.path.splitext(target)[1].lower()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }.get(ext, "application/octet-stream")

        with open(target, "rb") as f:
            self._send(200, f.read(), ctype)

    # ---------- 聊天代理 ----------
    def _handle_chat(self):
        if not API_KEY:
            self._send_json(500, {"error": "后端未配置 DEEPSEEK_API_KEY"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8")
            req = json.loads(raw or "{}")
            history = req.get("messages", [])
            if not isinstance(history, list):
                raise ValueError("messages 必须是数组")
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
        except ValueError as e:
            self._send_json(400, {"error": "参数错误：%s" % e})
            return

        # 流式响应头（在开始流式前必须先拿到首个增量，否则出错时无法优雅返回 JSON）
        gen = call_deepseek_stream(messages)
        try:
            first = next(gen)
        except StopIteration:
            self._send_json(200, {"reply": ""})
            return
        except RuntimeError as e:
            self._send_json(502, {"error": str(e)})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(first.encode("utf-8"))
            self.wfile.flush()
            for piece in gen:
                self.wfile.write(piece.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ---------- 反馈 ----------
    def _handle_feedback(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8")
            req = json.loads(raw or "{}")
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"error": "请求体不是合法 JSON"})
            return

        name = (req.get("name") or "").strip()
        relation = (req.get("relation") or "").strip()
        device = (req.get("device") or "").strip()
        content = (req.get("content") or "").strip()
        version = (req.get("version") or FEEDBACK_VERSION).strip()

        if not content:
            self._send_json(400, {"error": "反馈内容不能为空"})
            return
        if len(content) > 2000:
            self._send_json(400, {"error": "反馈内容过长（最多 2000 字）"})
            return

        record = {
            "version": version,
            "name": name[:100],
            "relation": relation[:100],
            "device": device[:100],
            "content": content,
        }

        # 优先写入 Supabase；未配置或失败时回退本地文件，确保不丢反馈
        if SUPABASE_URL and SUPABASE_ANON_KEY:
            status, err = insert_feedback_supabase(record)
            if status == 201:
                self._send_json(200, {"ok": True, "backend": "supabase"})
                return
            try:
                save_feedback_local(record)
            except OSError as e:
                self._send_json(500, {"error": "Supabase 写入失败且本地保存也失败：%s" % e})
                return
            self._send_json(200, {"ok": True, "backend": "local",
                                  "note": "Supabase 写入失败，已保存到本地文件"})
            return

        try:
            save_feedback_local(record)
        except OSError as e:
            self._send_json(500, {"error": "保存反馈失败：%s" % e})
            return
        self._send_json(200, {"ok": True, "backend": "local"})

    # ---------- 路由 ----------
    def do_GET(self):
        self._serve_static()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/chat":
            self._handle_chat()
        elif path == "/api/feedback":
            self._handle_feedback()
        else:
            self._send(404, "Not Found")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = HTTPServer(("127.0.0.1", port), Handler)
    if not API_KEY:
        print("警告：未找到 DEEPSEEK_API_KEY（请配置 .env 或环境变量），聊天接口将不可用。")
    print("个人主页服务已启动： http://127.0.0.1:%d" % port)
    print("按 Ctrl+C 停止服务。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止服务。")


if __name__ == "__main__":
    main()
