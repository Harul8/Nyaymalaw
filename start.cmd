@echo off
rem The double-clickable start button.
rem
rem `start.ps1` does the work; this exists so the advocate can double-click it
rem in Explorer without knowing anything about execution policies.
rem
rem -ExecutionPolicy Bypass applies to THIS invocation only. It does not change
rem the machine's policy, and a script that told someone to run
rem `Set-ExecutionPolicy` would be asking them to lower a setting permanently
rem to start a dev server once.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 (
  echo.
  echo   It did not start. The message above says why.
  pause
)
