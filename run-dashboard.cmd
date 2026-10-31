@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Run setup-classroom.ps1 -FullClicky first. See CLASSROOM.md.
    pause
    exit /b 1
)
rem Preserve existing installation choices without copying any API keys into this repo.
if exist "%LOCALAPPDATA%\Programs\Clicky\.env" set "CLICKY_LEGACY_CONFIG=%LOCALAPPDATA%\Programs\Clicky\.env"
start "" ".venv\Scripts\pythonw.exe" "main.py" --dashboard
