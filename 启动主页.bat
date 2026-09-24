@echo off
chcp 65001 >nul
title Homepage Server
cd /d "%~dp0"

echo ============================================
echo   周亦乐个人主页 · 一键启动
echo   访问地址： http://127.0.0.1:8000/
echo ============================================
echo.

rem 检查 8000 端口是否已在运行
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo [提示] 服务已在运行，直接打开浏览器...
) else (
    echo [提示] 正在启动服务...
    start "Homepage Server" python server.py
)

rem 等待服务就绪后打开浏览器
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8000/

echo.
echo [完成] 浏览器已打开。
echo   反馈与聊天需保持 "Homepage Server" 窗口开启。
echo   关闭该窗口即停止服务；下次双击本脚本可重新启动。
echo.
pause
