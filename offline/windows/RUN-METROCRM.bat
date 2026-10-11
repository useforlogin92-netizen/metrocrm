@echo off
cd /d "%~dp0\..\.."
if not exist ".venv\Scripts\python.exe" (
  echo MetroCRM environment is not installed yet.
  echo Run offline\windows\SETUP-WINDOWS.ps1 first.
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m uvicorn app.main_portal:app --host 127.0.0.1 --port 8000 --reload
pause
