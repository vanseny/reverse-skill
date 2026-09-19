@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "INPUT_ROOT=%~1"
set "LEASE_TOKEN=%~2"

if defined INPUT_ROOT (
  set "WMPF_ROOT_CANDIDATE=%INPUT_ROOT%"
  powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%wmpf-debugger-service.ps1" -Action Start -UseEnvironmentRoot -LeaseToken "%LEASE_TOKEN%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%wmpf-debugger-service.ps1" -Action Start -LeaseToken "%LEASE_TOKEN%"
)
set "SERVICE_EXIT=%ERRORLEVEL%"
set "WMPF_ROOT_CANDIDATE="
exit /b %SERVICE_EXIT%
