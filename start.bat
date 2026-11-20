@echo off
setlocal
title Drone Map
cd /d "%~dp0"

rem ---- find Python (the py launcher first)
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo Python is not installed. Get it from https://www.python.org/downloads/
  echo and tick "Add Python to PATH" during setup, then run this again.
  pause
  exit /b 1
)

rem ---- update to the latest version on the main branch
where git >nul 2>nul
if errorlevel 1 (
  echo git not found: starting without updating.
) else (
  echo Updating Drone Map...
  git fetch -q origin
  git checkout -q main 2>nul || git checkout -q -b main origin/main
  git pull -q --ff-only origin main || echo Could not update automatically, starting the version you have.
)

echo Checking packages...
%PY% -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo Could not install the packages, see the messages above.
  pause
  exit /b 1
)

echo Starting the map. Keep this window open; close it or press Ctrl+C to stop.
%PY% run.py %*
pause
