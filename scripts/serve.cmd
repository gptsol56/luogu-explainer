@echo off
REM 启动洛谷工具箱网页应用 (前端 + API 代理层)。
REM 用法: scripts\serve.cmd            监听 127.0.0.1:8848
REM       scripts\serve.cmd --port 9000
REM 需要先设置 MINIMAX_API_KEY (讲解功能) 与 LUOGU_CLIENT_ID / LUOGU_UID (打卡与自动取题)。
setlocal
cd /d "%~dp0.."
python server\app.py %*
exit /b %ERRORLEVEL%