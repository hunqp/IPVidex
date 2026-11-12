@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\Build.ps1" %*
exit /b %errorlevel%
