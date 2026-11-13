@echo off
chcp 65001 >nul
title Tareekh Ki Kahani - VOICE SAMPLE
cd /d "%~dp0"
call "%~dp0factory\setup.bat" || goto :end
echo Making Hindi voice samples (needs internet)...
python "factory\voice_sample.py"
:end
pause
