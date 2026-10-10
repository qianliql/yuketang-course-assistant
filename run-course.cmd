@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
title Course Assistant
echo Starting Course Assistant...
if not exist ".venv\Scripts\python.exe" (
    echo Python environment was not found. Keep this window open for troubleshooting.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -u "scripts\run_local_course.py" %*
set "COURSE_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%COURSE_EXIT_CODE%"=="0" echo Course Assistant stopped with code %COURSE_EXIT_CODE%.
pause
exit /b %COURSE_EXIT_CODE%
