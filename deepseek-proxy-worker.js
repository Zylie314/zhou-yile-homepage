// =====================================================================
// Cloudflare Worker：DeepSeek 安全代理
// 作用：把 DeepSeek Key 藏到服务端，前端只请求本 Worker，源码不再出现 Key。
//       别人打开你的主页照样能用 AI 对话，但拿不到 Key、也无法盗刷。
// =====================================================================
//
// 部署步骤（在 Cloudflare 控制台完成，约 5 分钟）：
// 1. 打开 https://dash.cloudflare.com 注册/登录，进入「Workers & Pages」。
// 2. 点「Create application」→「Create Worker」→ 起个名字（如 deepseek-proxy）。
// 3. 删掉默认模板代码，把本文件内容全部粘贴进去，点「Deploy」。
// 4. 进入该 Worker 的「Settings → Variables and Secrets」：
//      - 点「Add Secret」，名称填 DEEPSEEK_KEY，值填你的「新」DeepSeek Key（加密存储，不进源码）。
// 5. 回到 Worker 概览页，复制它的 *.workers.dev 地址（形如
//    https://deepseek-proxy.你的账号.workers.dev），后面填到主页前端 PROXY_URL。
// 6. 建议再给 DeepSeek 账户设置余额上限/预警，作为最终兜底。
//
// 注意：部署前请务必先在 DeepSeek 平台吊销旧的、已泄露的 Key，再生成新 Key。
// =====================================================================

const ALLOWED_ORIGIN = 'https://zylie314.github.io'; // 你的主页域名（只放行它）
const UPSTREAM = 'https://api.deepseek.com/chat/completions';

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';

    // 1) CORS 预检请求（浏览器跨域会先发 OPTIONS）
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': ALLOWED_ORIGIN,
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
          'Access-Control-Max-Age': '86400',
        },
      });
    }

    // 2) 只允许 POST
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    // 3) 来源校验：只放行你自己的主页，挡住其它网站盗用你的代理
    if (origin && origin !== ALLOWED_ORIGIN) {
      return new Response('Forbidden', { status: 403 });
    }

    // 4) 从服务端 Secret 读取 Key（Key 只存在这里，不进入前端源码）
    const key = env.DEEPSEEK_KEY;
    if (!key) {
      return new Response('Server not configured', { status: 500 });
    }

    // 5) 原样转发请求体到 DeepSeek（保持流式），只在服务端附上 Key
    const upstream = await fetch(UPSTREAM, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + key,
      },
      body: request.body,
    });

    // 6) 透传 SSE 流式响应回前端
    const headers = new Headers();
    headers.set(
      'Content-Type',
      upstream.headers.get('Content-Type') || 'text/event-stream; charset=utf-8'
    );
    headers.set('Access-Control-Allow-Origin', ALLOWED_ORIGIN);
    headers.set('Cache-Control', 'no-cache');

    return new Response(upstream.body, {
      status: upstream.status,
      headers,
    });
  },
};
