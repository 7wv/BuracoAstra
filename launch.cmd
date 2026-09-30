@echo off
setlocal
cd /d "%~dp0"
set "BURACO_MODULE=buraco"
if /i "%~1"=="web" set "BURACO_MODULE=buraco.web"
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
    py -3 -m %BURACO_MODULE%
    goto finished
)
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
    python -m %BURACO_MODULE%
    goto finished
)
set "BURACO_BUNDLED_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%BURACO_BUNDLED_PYTHON%" (
    "%BURACO_BUNDLED_PYTHON%" -m %BURACO_MODULE%
    goto finished
)
echo Python 3.10 or newer is required. Install Python and run this launcher again.
:finished
if errorlevel 1 pause
endlocal
