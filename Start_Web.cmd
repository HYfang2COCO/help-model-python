@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto python
py -3 web_server.py --open
goto done
:python
python web_server.py --open
:done
if errorlevel 1 (
  echo Install Python 3.10 or newer, extract the whole ZIP, and try again.
  pause
)
