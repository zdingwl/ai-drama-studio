@echo off
setlocal
cd /d "%~dp0"

py -3.12 -c "import sys" >nul 2>&1
if %errorlevel%==0 (
  py -3.12 scripts\stop_studio.py %*
  exit /b %errorlevel%
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if %errorlevel%==0 (
  python scripts\stop_studio.py %*
  exit /b %errorlevel%
)

echo ERROR: Python is required to stop AI Drama Studio safely.
exit /b 1
