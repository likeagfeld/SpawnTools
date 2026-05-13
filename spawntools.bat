@echo off
REM ============================================================
REM  SpawnTools — Windows launcher
REM
REM  Double-click this file to start the GUI.
REM  • Finds Python automatically (tries 'py' then 'python')
REM  • Installs Pillow + numpy on first run if they're missing
REM  • Launches `python -m spawntools`
REM
REM  No path config needed — the codec library and Spawn preset
REM  ship inside the package.
REM ============================================================
setlocal EnableDelayedExpansion

cd /d "%~dp0"

REM --- 1. Find a working Python ---
set "PY="
where py >nul 2>&1
if !errorlevel! == 0 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if !errorlevel! == 0 set "PY=py -3"
)
if "!PY!" == "" (
    where python >nul 2>&1
    if !errorlevel! == 0 (
        python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
        if !errorlevel! == 0 set "PY=python"
    )
)
if "!PY!" == "" (
    echo.
    echo ============================================================
    echo  Python 3.10 or newer is required but was not found.
    echo  Download it from https://www.python.org/downloads/
    echo  ^(check "Add Python to PATH" during install^).
    echo ============================================================
    echo.
    pause
    exit /b 1
)

REM --- 2. Ensure dependencies installed (Pillow + numpy) ---
!PY! -c "import PIL, numpy" >nul 2>&1
if !errorlevel! neq 0 (
    echo Installing dependencies on first run, please wait...
    !PY! -m pip install --user -r requirements.txt
    if !errorlevel! neq 0 (
        echo.
        echo Dependency installation failed.
        echo Try running:  !PY! -m pip install --user Pillow numpy
        pause
        exit /b 1
    )
)

REM --- 3. Launch the GUI ---
!PY! -m spawntools
set "RC=!errorlevel!"
if !RC! neq 0 (
    echo.
    echo SpawnTools exited with code !RC!.
    pause
)
endlocal
