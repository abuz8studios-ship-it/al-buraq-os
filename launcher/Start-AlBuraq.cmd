@echo off
title Al-Buraq Agent OS   (close this window to STOP)
cd /d "%~dp0\.."
echo ================================================================
echo    AL-BURAQ AGENT OS  -  sovereign, local-first, offline
echo    First run asks where to store your brain and data.
echo    Close this window to stop. Delete the app; your data stays.
echo ================================================================
where python >nul 2>nul
if errorlevel 1 (
  echo [Al-Buraq] Python not found on PATH. Install Python 3.10+ and retry.
  pause & exit /b 1
)
python -c "import fastapi,uvicorn,pydantic" 2>nul || python -m pip install fastapi "uvicorn[standard]" pydantic
python "launcher\provision.py"
