@echo off
chcp 65001 >nul
title Tareekh Ki Kahani - VOICE RECORDER (keep this window open)
cd /d "%~dp0"
call "%~dp0factory\setup.bat" || goto :end
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*record_web.py*' -and $_.ProcessId -ne $PID } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
timeout /t 1 >nul
python "factory\record_web.py"
:end
pause
