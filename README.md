# 周亦乐个人主页

一个深色简约风格的个人主页，包含个人信息展示、版本归档、一个「数字分身」AI 聊天窗口（接入 DeepSeek），以及页面反馈功能。

- 在线演示（静态版）：https://zylie314.github.io/zhou-yile-homepage/
- 在线版为静态展示，AI 聊天需本地运行。

## 本地运行

### 前置条件

- Python 3（3.6 及以上，仅使用标准库，无需安装任何第三方依赖）
- Windows 可用一键脚本；macOS / Linux 手动运行即可

### 方式一：一键启动（Windows）

双击项目根目录下的 `启动主页.bat`，脚本会自动：

1. 检查 8000 端口是否已被占用；
2. 未占用则启动后端服务 `server.py`；
3. 自动打开浏览器访问 http://127.0.0.1:8000/ 。

保持弹出的「Homepage Server」窗口开启即可正常使用聊天与反馈；关闭该窗口即停止服务。

### 方式二：手动启动（Windows / macOS / Linux）

```bash
cd 项目目录
python server.py
```

然后浏览器访问 http://127.0.0.1:8000/ 。

指定端口：

```bash
python server.py 9000
```

### 手机 / 局域网访问

服务绑定 `0.0.0.0`，同一局域网内的手机等设备可通过本机 IP 访问，例如：

```
http://<本机IP>:8000/
```

启动时终端会打印本机局域网访问地址。

## 配置（可选）

AI 聊天需要 DeepSeek 的 API Key。在项目根目录新建 `.env` 文件（该文件已被 `.gitignore` 忽略，不会提交到仓库）：

```
DEEPSEEK_API_KEY=你的DeepSeek密钥
```

- 未配置 `DEEPSEEK_API_KEY` 时，聊天自动降级为内置规则回复，不影响页面其它功能；
- 反馈表单默认直连 Supabase（匿名密钥已内置在页面中），无需额外配置。

## 目录结构

- `index.html` — 最新版本页面
- `v1.0.html` ~ `v3.3.html` — 历史版本归档
- `server.py` — 本地后端（静态托管 + AI 聊天代理 + 反馈接口）
- `启动主页.bat` — Windows 一键启动脚本
- `CHANGELOG.md` — 版本与改动记录
