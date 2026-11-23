@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo [run_demo] 工作目录: %CD%
python "%~dp0demo_agent_loop.py" %*
echo.
if errorlevel 1 echo [run_demo] 退出码非 0, 请看上面的报错
pause