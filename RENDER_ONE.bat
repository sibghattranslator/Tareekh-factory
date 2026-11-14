@echo off
chcp 65001 >nul
title Tareekh Ki Kahani - RENDER ONE VIDEO
cd /d "%~dp0"
call "%~dp0factory\setup.bat" || goto :end
echo.
set /p NUM=Which video number? (example: 6) : 
python "factory\render.py" %NUM%
:end
echo.
pause
