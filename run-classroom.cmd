@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Run setup-classroom.ps1 first. See CLASSROOM.md.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "classroom_app.py"
