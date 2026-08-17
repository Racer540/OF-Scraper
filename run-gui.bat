@echo off
setlocal
rem Always run from the folder this .bat lives in, so config/paths resolve
cd /d "%~dp0"

if exist ".venv\Scripts\ofscraper-gui.exe" (
    ".venv\Scripts\ofscraper-gui.exe" %*
) else (
    echo [ERROR] .venv\Scripts\ofscraper-gui.exe not found.
    echo Run "uv sync" first to create the virtualenv.
    pause
    exit /b 1
)

rem Keep the window open if the GUI exited with an error, so it can be read
if errorlevel 1 pause
endlocal
