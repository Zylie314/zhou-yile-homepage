# -*- coding: utf-8 -*-
# =====================================================================
# 腾讯云函数（SCF）：DeepSeek 安全代理
# 作用：把 DeepSeek Key 藏到云函数的环境变量里，前端只请求本函数，
#       源码里不再出现 Key。别人打开主页照样能聊 AI，但拿不到 Key。
#
# 运行环境：Python 3.9（或 3.7）
# 触发器：API 网关触发器（鉴权方式选「免鉴权」）
# 环境变量：DEEPSEEK_KEY = 你的「新」DeepSeek Key
#
# 说明：本函数以非流式（stream=false）转发，返回完整 JSON。
#       前端已相应改为非流式渲染，避免国内 API 网关对流式(SSE)支持不稳。
# =====================================================================

import base64
import json
import os
import urllib.error
import urllib.request

ALLOWED_ORIGIN = 'https://zylie314.github.io'   # 你的主页域名（只放行它）
UPSTREAM = 'https://api.deepseek.com/chat/completions'


def _cors(status, body='', extra_headers=None):
    headers = {'Access-Control-Allow-Origin': ALLOWED_ORIGIN}
    if extra_headers:
        headers.update(extra_headers)
    return {
        'isBase64Encoded': False,
        'statusCode': status,
        'headers': headers,
        'body': body,
    }


def main_handler(event, context):
    method = (event.get('httpMethod') or event.get('method') or '').upper()
    headers = event.get('headers') or {}

    # 1) CORS 预检（浏览器跨域会先发 OPTIONS）
    if method == 'OPTIONS':
        return _cors(204, extra_headers={
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '86400',
        })

    # 2) 只允许 POST
    if method != 'POST':
        return _cors(405, 'Method Not Allowed')

    # 3) 来源校验：只放行你自己的主页，挡住其它网站盗用
    origin = headers.get('origin') or headers.get('Origin') or ''
    if origin and origin != ALLOWED_ORIGIN:
        return _cors(403, 'Forbidden')

    # 4) 从环境变量读 Key（Key 只存在云函数配置里，不进前端源码）
    key = os.environ.get('DEEPSEEK_KEY', '')
    if not key:
        return _cors(500, 'Server not configured')

    # 5) 取出请求体（兼容 base64 编码的情况）
    body = event.get('body') or '{}'
    if event.get('isBase64Encoded'):
        body = base64.b64decode(body).decode('utf-8')

    # 6) 转发到 DeepSeek（非流式），只在服务端附上 Key
    req = urllib.request.Request(
        UPSTREAM,
        data=body.encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + key,
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read().decode('utf-8')
            return _cors(200, data, extra_headers={
                'Content-Type': 'application/json; charset=utf-8',
                'Cache-Control': 'no-cache',
            })
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', 'ignore')
        return _cors(e.code or 502, err_body, extra_headers={
            'Content-Type': 'application/json; charset=utf-8',
        })
    except Exception as e:
        return _cors(502, json.dumps({'error': str(e)}, ensure_ascii=False),
                     extra_headers={'Content-Type': 'application/json; charset=utf-8'})
