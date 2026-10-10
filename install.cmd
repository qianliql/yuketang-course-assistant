@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
echo Installing Course Assistant...
if exist ".venv\Scripts\python.exe" goto install_dependencies
py -3 -m venv .venv
if not errorlevel 1 goto install_dependencies
python -m venv .venv
if errorlevel 1 goto python_missing
:install_dependencies
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto install_failed
if not exist "local-config.json" copy /y "local-config.example.json" "local-config.json" >nul
if errorlevel 1 goto install_failed
echo.
echo Installation finished.
echo Edit local-config.json with your course URL, then double-click run-course.cmd.
pause
exit /b 0
:python_missing
echo Please install Python 3.11 or newer and enable its command-line launcher.
pause
exit /b 1
:install_failed
echo Installation failed. Check the error above and try again.
pause
exit /b 1
