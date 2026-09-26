@echo off
setlocal
title linkreach - Bot (Backend)
cd /d "%~dp0"
set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" goto :missing_python
"%PYTHON_EXE%" -c "import sys" >nul 2>&1
if errorlevel 1 goto :broken_python

if not exist "%CD%\data" mkdir "%CD%\data"
set "SECRET_FILE=%CD%\data\.django_secret_key"
if not exist "%SECRET_FILE%" (
  "%PYTHON_EXE%" -c "import os,pathlib,secrets; p=pathlib.Path(r'%SECRET_FILE%'); p.write_text(secrets.token_urlsafe(64), encoding='utf-8'); os.chmod(p, 0o600)"
  if errorlevel 1 goto :secret_error
)
for /f "usebackq delims=" %%K in ("%SECRET_FILE%") do set "DJANGO_SECRET_KEY=%%K"
set linkreach_LOCAL_RELEASE=1
set linkreach_DEBUG=0
set PYTHONUTF8=1
set PLAYWRIGHT_BROWSERS_PATH=%CD%\.browsers
echo ============================================
echo   linkreach Bot starting...
echo   A Chrome window will open and log into LinkedIn.
echo   Do NOT close that Chrome window.
echo   Keep this window open. Press Ctrl+C to stop.
echo ============================================
echo.
"%PYTHON_EXE%" manage.py rundaemon
echo.
echo Bot stopped.
pause
exit /b %errorlevel%

:missing_python
echo Python environment not found at %PYTHON_EXE%.
echo Create it with: py -3.13 -m venv .venv
pause
exit /b 1

:broken_python
echo The project Python environment is present but cannot start.
echo Recreate .venv with an installed Python 3.13 runtime, then reinstall requirements/local.txt.
pause
exit /b 1

:secret_error
echo Could not create the local Django secret in data\.django_secret_key.
pause
exit /b 1
