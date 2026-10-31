@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Local environment missing. See README.md for setup.
  exit /b 1
)
set PYTHONUTF8=1
".venv\Scripts\python.exe" scripts\run_local.py
