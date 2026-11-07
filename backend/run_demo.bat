@echo off
chcp 65001 >nul
REM Runs the 3 video workflows. Needs Python 3.10+ (check with: python --version)
cd /d %~dp0
set PY=python
where python >nul 2>nul || set PY=py
%PY% -m itsm.demo
pause
