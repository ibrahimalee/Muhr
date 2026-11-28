@echo off
cd /d "%~dp0"
echo Restarting MUHR Seller Services...
echo.

echo [1/4] Stopping old seller processes...
taskkill /F /FI "WINDOWTITLE eq MUHR Summarizer*" 2>nul
taskkill /F /FI "WINDOWTITLE eq MUHR Classifier*" 2>nul
taskkill /F /FI "WINDOWTITLE eq MUHR Urdu*" 2>nul
timeout /t 2 /nobreak >nul

echo [2/4] Starting Summarizer on port 8001...
start "MUHR Summarizer" cmd /k "set PYTHONPATH=%CD% && python -m uvicorn sellers.summarizer.app:app --port 8001"
timeout /t 3 /nobreak >nul

echo [3/4] Starting Classifier on port 8002...
start "MUHR Classifier" cmd /k "set PYTHONPATH=%CD% && python -m uvicorn sellers.classifier.app:app --port 8002"
timeout /t 3 /nobreak >nul

echo [4/4] Starting Urdu translator on port 8003...
start "MUHR Urdu" cmd /k "set PYTHONPATH=%CD% && python -m uvicorn sellers.urdu.app:app --port 8003"
timeout /t 2 /nobreak >nul

echo.
echo ✓ Sellers restarted with new environment!
echo.
echo Summarizer:  http://localhost:8001
echo Classifier:  http://localhost:8002
echo Urdu:        http://localhost:8003
echo.
echo API Keys loaded from .env file
echo.
pause
