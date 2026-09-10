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


API_KEY = load_api_key()


def call_deepseek(messages):
    """调用 DeepSeek chat completions，返回助手回复文本。"""
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": 800,
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
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError("DeepSeek HTTP %s: %s" % (e.code, detail[:500]))
    except urllib.error.URLError as e:
        raise RuntimeError("无法连接 DeepSeek：%s" % e.reason)


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
            reply = call_deepseek(messages)
            self._send_json(200, {"reply": reply})
        except ValueError as e:
            self._send_json(400, {"error": "参数错误：%s" % e})
        except RuntimeError as e:
            self._send_json(502, {"error": str(e)})
        except Exception as e:  # 兜底
            self._send_json(500, {"error": "服务器错误：%s" % e})

    # ---------- 路由 ----------
    def do_GET(self):
        self._serve_static()

    def do_POST(self):
        if self.path.split("?", 1)[0] == "/api/chat":
            self._handle_chat()
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
