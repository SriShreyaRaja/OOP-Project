@echo off
chcp 65001 >nul
REM Runs all tests. Installs pytest the first time (needs internet once).
cd /d %~dp0
set PY=python
where python >nul 2>nul || set PY=py
%PY% -m pip install --quiet -r requirements.txt
%PY% -m pytest -v
pause
