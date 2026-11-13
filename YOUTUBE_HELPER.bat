@echo off
chcp 65001 >nul
title Tareekh Ki Kahani - YOUTUBE HELPER (keep this window open)
cd /d "%~dp0"
call "%~dp0factory\setup.bat" || goto :end
python "factory\yt_helper.py"
:end
pause
