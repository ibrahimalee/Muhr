@echo off
REM Start the MUHR registry and all three sellers from the repo root (DEMO mode by default).
cd /d "%~dp0"

echo [1/4] Registry on http://127.0.0.1:8000
start "MUHR Registry" cmd /k "python -m uvicorn registry.main:app --host 127.0.0.1 --port 8000"
timeout /t 3 /nobreak >nul

echo [2/4] Summarizer seller on http://127.0.0.1:8001
start "MUHR Summarizer" cmd /k "python -m uvicorn sellers.summarizer.app:app --host 127.0.0.1 --port 8001"

echo [3/4] Classifier seller on http://127.0.0.1:8002
start "MUHR Classifier" cmd /k "python -m uvicorn sellers.classifier.app:app --host 127.0.0.1 --port 8002"

echo [4/4] Urdu translation seller on http://127.0.0.1:8003
start "MUHR Urdu" cmd /k "python -m uvicorn sellers.urdu.app:app --host 127.0.0.1 --port 8003"

echo.
echo Dashboard: cd front-end\muhr-nexus ^&^& npm run dev   (http://127.0.0.1:8080)
echo SSE feed:  http://127.0.0.1:8000/api/feed
pause
