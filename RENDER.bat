@echo off
chcp 65001 >nul
title Tareekh Ki Kahani - RENDER
cd /d "%~dp0"
call "%~dp0factory\setup.bat" || goto :end
echo.
echo Making videos... (AI voice needs internet)
python "factory\render.py"
:end
echo.
pause
