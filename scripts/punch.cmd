@echo off
REM 手动触发一次洛谷打卡。需先设置 LUOGU_CLIENT_ID / LUOGU_UID 两个环境变量。
REM 用法: scripts\punch.cmd            打一次卡
REM       scripts\punch.cmd --json     JSON 输出
REM       scripts\punch.cmd --selftest 离线自检
setlocal
cd /d "%~dp0.."
python luogu_punch.py %*
exit /b %ERRORLEVEL%