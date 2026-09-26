@echo off
setlocal EnableExtensions EnableDelayedExpansion
title linkreach - Fresh Start (one-time setup)

REM ============================================================
REM   fresh-start.bat — one-time bootstrap for a fresh download.
REM
REM   What this does:
REM     1. Checks Python 3.12+ is available
REM     2. Creates .venv\ if missing
REM     3. Installs requirements/local.txt
REM     4. Installs the Playwright Chromium browser
REM     5. Creates data\ and a Django secret key if missing
REM     6. Runs database migrations
REM     7. Bootstraps the CRM (default site)
REM     8. Creates an admin superuser (interactive)
REM
REM   Re-running this script is safe — every step is idempotent.
REM
REM   After it completes, run Start-Bot.bat to launch the daemon,
REM   or Start-Dashboard.bat to launch the web UI.
REM ============================================================

cd /d "%~dp0"

echo.
echo ============================================
echo   linkreach - Fresh Start
echo   One-time setup for a fresh download.
echo ============================================
echo.

REM ---- 1. Python check ----------------------------------------------------
where py >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python launcher 'py' not found on PATH.
    echo   Install Python 3.12 or newer from https://www.python.org/downloads/
    echo   and tick "Add Python to PATH" during install.
    pause
    exit /b 1
)

REM Resolve a 3.12+ interpreter. py -3.13 is preferred (matches Start-Bot.bat).
set "PY_LAUNCHER=py -3.13"
%PY_LAUNCHER% -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
if errorlevel 1 (
    %PY_LAUNCHER% -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
)
if errorlevel 1 (
    echo [ERROR] Python 3.12 or newer is required.
    echo   Install from https://www.python.org/downloads/ (3.12+).
    pause
    exit /b 1
)

for /f "usebackq delims=" %%V in (`%PY_LAUNCHER% -c "import sys; print(sys.version.split()[0])"`) do set "PY_VERSION=%%V"
echo [OK] Found Python %PY_VERSION%
echo.

REM ---- 2. venv ------------------------------------------------------------
set "VENV=%CD%\.venv"
set "PYTHON_EXE=%VENV%\Scripts\python.exe"

if not exist "%VENV%\Scripts\python.exe" (
    echo [1/7] Creating Python virtual environment at .venv\ ...
    %PY_LAUNCHER% -m venv "%VENV%"
    if errorlevel 1 goto :venv_error
) else (
    echo [1/7] Reusing existing .venv\ ...
)
echo [OK] Virtual environment ready.
echo.

REM ---- 3. Upgrade pip + install uv (used by the rest of the project) ------
echo [2/7] Upgrading pip and installing uv ...
"%PYTHON_EXE%" -m pip install --upgrade pip wheel >nul
if errorlevel 1 goto :pip_error
"%PYTHON_EXE%" -m pip install --upgrade uv >nul
if errorlevel 1 goto :pip_error
echo [OK] pip and uv upgraded.
echo.

REM ---- 4. Install dependencies --------------------------------------------
echo [3/7] Installing requirements/local.txt ...
"%PYTHON_EXE%" -m uv pip install -r requirements/local.txt
if errorlevel 1 goto :deps_error
echo [OK] Python dependencies installed.
echo.

REM ---- 5. Playwright browser ----------------------------------------------
echo [4/7] Installing Playwright Chromium browser ...
set "PLAYWRIGHT_BROWSERS_PATH=%CD%\.browsers"
"%PYTHON_EXE%" -m playwright install --with-deps chromium
if errorlevel 1 (
    echo [WARN] Playwright install failed or was interrupted.
    echo   Run Start-Bot.bat — it will retry the browser install on first launch.
)
echo [OK] Playwright browser install attempted.
echo.

REM ---- 6. data\ dir + Django secret key -----------------------------------
echo [5/7] Preparing data\ directory ...
if not exist "%CD%\data" mkdir "%CD%\data"
set "SECRET_FILE=%CD%\data\.django_secret_key"
if not exist "%SECRET_FILE%" (
    "%PYTHON_EXE%" -c "import os,pathlib,secrets; p=pathlib.Path(r'%SECRET_FILE%'); p.write_text(secrets.token_urlsafe(64), encoding='utf-8'); os.chmod(p, 0o600)"
    if errorlevel 1 goto :secret_error
)
echo [OK] data\ ready.
echo.

REM ---- 7. Database migrations + CRM bootstrap -----------------------------
set "linkreach_LOCAL_RELEASE=1"
set "linkreach_DEBUG=0"
set "PYTHONUTF8=1"

echo [6/7] Running database migrations ...
"%PYTHON_EXE%" manage.py migrate --no-input
if errorlevel 1 goto :migrate_error
echo [OK] Migrations applied.

echo.
echo Bootstrap CRM (default site) ...
"%PYTHON_EXE%" manage.py setup_crm
if errorlevel 1 goto :crm_error
echo [OK] CRM bootstrapped.
echo.

REM ---- 8. Superuser --------------------------------------------------------
echo [7/7] Create an admin account for /admin/ and /dashboard/
echo   (skip if you've done this before)
echo.
set /p MAKE_USER=Create admin superuser now? [Y/n]
if /I "%MAKE_USER%"=="n" (
    echo [SKIP] You can create one later with: manage.py createsuperuser
) else (
    "%PYTHON_EXE%" manage.py createsuperuser
    if errorlevel 1 (
        echo [WARN] Superuser creation cancelled or failed.
        echo   Re-run later with: manage.py createsuperuser
    )
)

echo.
echo ============================================
echo   linkreach setup complete.
echo.
echo   Next steps:
echo     - Run Start-Bot.bat to launch the daemon
echo       and walk through first-run onboarding.
echo     - Run Start-Dashboard.bat to launch the web UI
echo       (default: http://127.0.0.1:8000/dashboard/).
echo.
echo   Re-run this script any time — every step is idempotent.
echo ============================================
echo.
pause
exit /b 0

REM ---- error labels -------------------------------------------------------
:venv_error
echo [ERROR] Failed to create .venv. Make sure py -3.13 is a working Python install.
pause
exit /b 1

:pip_error
echo [ERROR] Failed to upgrade pip / install uv.
pause
exit /b 1

:deps_error
echo [ERROR] Failed to install requirements/local.txt.
echo   Check the error above; common cause: conflicting package versions on this Python.
pause
exit /b 1

:secret_error
echo [ERROR] Could not create the local Django secret in data\.django_secret_key.
pause
exit /b 1

:migrate_error
echo [ERROR] Database migration failed. Check the trace above.
pause
exit /b 1

:crm_error
echo [ERROR] CRM bootstrap (setup_crm) failed. Check the trace above.
pause
exit /b 1
