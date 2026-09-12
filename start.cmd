@echo off
setlocal
cd /d "%~dp0"

py -3.12 -c "import sys" >nul 2>&1
if %errorlevel%==0 (
  py -3.12 scripts\start_studio_guard.py %*
  exit /b %errorlevel%
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if %errorlevel%==0 (
  python scripts\start_studio_guard.py %*
  exit /b %errorlevel%
)

echo ERROR: Python 3.12+ is required to start AI Drama Studio.
exit /b 1
