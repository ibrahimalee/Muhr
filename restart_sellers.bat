@echo off
cd /d "%~dp0"
echo Restarting MUHR Seller Services...
echo.

echo [1/3] Stopping old seller processes...
taskkill /F /FI "WINDOWTITLE eq MUHR Summarizer*" 2>nul
taskkill /F /FI "WINDOWTITLE eq MUHR Classifier*" 2>nul
timeout /t 2 /nobreak >nul

echo [2/3] Starting Summarizer on port 8001...
start "MUHR Summarizer" cmd /k "set PYTHONPATH=%CD% && python -m uvicorn sellers.summarizer.app:app --port 8001"
timeout /t 3 /nobreak >nul

echo [3/3] Starting Classifier on port 8002...
start "MUHR Classifier" cmd /k "set PYTHONPATH=%CD% && python -m uvicorn sellers.classifier.app:app --port 8002"
timeout /t 2 /nobreak >nul

echo.
echo ✓ Sellers restarted with new environment!
echo.
echo Summarizer:  http://localhost:8001
echo Classifier:  http://localhost:8002
echo.
echo API Keys loaded from .env file
echo.
pause
