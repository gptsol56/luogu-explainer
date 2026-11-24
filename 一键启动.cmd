@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title 洛谷题目自动讲解 · 一键启动

REM ============================================================
REM  双击这个文件就能起本地站点, 并自动打开浏览器。
REM  用法:
REM      一键启动.cmd                     默认 127.0.0.1:8848
REM      一键启动.cmd 9000                换端口
REM      一键启动.cmd 8848 --no-browser   不自动开浏览器 (调试用)
REM ============================================================

set "PORT=8848"
set "HOST=127.0.0.1"
set "NO_BROWSER="
set "PY="

:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="--no-browser" (
    set "NO_BROWSER=1"
    shift
    goto parse_args
)
set "PORT=%~1"
shift
goto parse_args
:args_done

echo.
echo   ==================================================
echo     洛谷题目自动讲解  ·  一键启动
echo   ==================================================
echo.

REM ---------- 1. 找 Python ----------
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo   [1/4] 没找到 Python。
    echo         装一个 Python 3.9 以上, 安装时勾上 "Add Python to PATH",
    echo         然后再双击本文件。
    echo.
    pause
    exit /b 1
)
echo   [1/4] Python: %PY%

REM ---------- 2. 载入 .env (有才载) ----------
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" set "%%A=%%B"
    )
    echo   [2/4] 已载入 .env
) else (
    echo   [2/4] 没有 .env, 跳过
    echo         站点照样能开, 只是要在页面上自己填密钥。
)

REM ---------- 3. 是不是已经在跑了 ----------
REM   用 HTTP 探活, 不用 netstat —— 有些机器上 netstat 根本列不出自己的 socket。
%PY% -c "import urllib.request,sys; r=urllib.request.urlopen('http://%HOST%:%PORT%/api/health',timeout=2); sys.exit(0 if r.getcode()==200 else 1)" >nul 2>&1
if not errorlevel 1 (
    echo   [3/4] 这个端口上已经有服务在跑, 不重复起, 直接开浏览器。
    goto :open_browser
)

REM ---------- 4. 起服务 ----------
echo   [3/4] 正在起服务: %PY% server\app.py --port %PORT%
start "洛谷讲解助手 · 服务" cmd /k %PY% server\app.py --host %HOST% --port %PORT%

set /a tries=0
:wait_ready
%PY% -c "import urllib.request,sys; r=urllib.request.urlopen('http://%HOST%:%PORT%/api/health',timeout=2); sys.exit(0 if r.getcode()==200 else 1)" >nul 2>&1
if not errorlevel 1 goto :ready
set /a tries+=1
if !tries! geq 30 goto :failed
ping -n 2 127.0.0.1 >nul
goto :wait_ready

:ready
:open_browser
if not defined NO_BROWSER (
    echo   [4/4] 服务已就绪, 正在打开浏览器 ...
    start "" "http://%HOST%:%PORT%/"
) else (
    echo   [4/4] 服务已就绪，按参数要求没有自动开浏览器。
)
echo.
echo   地址: http://%HOST%:%PORT%/
echo   关掉「洛谷讲解助手 · 服务」那个窗口, 就等于停服务。
echo.
pause
exit /b 0

:failed
echo   [X] 服务没起来。
echo       看「洛谷讲解助手 · 服务」窗口里的报错, 多半是端口被占或者少装了依赖。
echo.
pause
exit /b 1