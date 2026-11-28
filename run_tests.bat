@echo off
REM MUHR test runner (Windows).
setlocal
pushd "%~dp0"

python -m pip install -q -r requirements-dev.txt

echo.
echo === Python tests ===
python -m pytest -q tests\
if errorlevel 1 goto :fail

echo.
echo === Frontend typecheck, tests and build ===
pushd front-end\muhr-nexus
call npm ci --no-audit --no-fund
call npx tsc -p tsconfig.app.json --noEmit || goto :failfe
call npm test || goto :failfe
call npm run build || goto :failfe
popd

echo.
echo Optional: with services running, python scripts\test_e2e_smoke.py
popd
endlocal
exit /b 0

:failfe
popd
:fail
popd
endlocal
exit /b 1
