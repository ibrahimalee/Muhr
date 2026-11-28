@echo off
REM Start the MUHR registry from the repo root (keeps muhr.db at the repo root).
cd /d "%~dp0"
python -m uvicorn registry.main:app --host 127.0.0.1 --port 8000 --reload
