@echo off
echo Starting MUHR Seller Services...
echo.

cd /d "%~dp0"
REM Set PYTHONPATH to include the project root
set PYTHONPATH=%CD%

echo [1/2] Starting Summarizer on port 8001...
start "MUHR Summarizer" cmd /k "set PYTHONPATH=%CD% && python -m uvicorn sellers.summarizer.app:app --port 8001"
timeout /t 2 /nobreak >nul

echo [2/2] Starting Classifier on port 8002...
start "MUHR Classifier" cmd /k "set PYTHONPATH=%CD% && python -m uvicorn sellers.classifier.app:app --port 8002"
timeout /t 2 /nobreak >nul

echo.
echo ✓ Seller services started!
echo.
echo Summarizer:  http://localhost:8001
echo Classifier:  http://localhost:8002
echo.
echo Test with: curl http://localhost:8001/health
echo.
pause
