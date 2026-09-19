@echo off
setlocal EnableExtensions

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0wmpf-debugger-service.ps1" -Action Stop -LeaseToken "%~1"
exit /b %ERRORLEVEL%
