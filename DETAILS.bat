@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
title Tareekh Ki Kahani - DETAILS
cd /d "%~dp0"
echo.
echo   STEP 1 (you): upload the video files in YouTube Studio by hand (keep the file name as the title).
echo   STEP 2 (this): fills in title, description, tags, thumbnail, Urdu + English subtitles and the schedule.
echo.
where python >nul 2>nul
if errorlevel 1 ( echo Python is not installed. & pause & exit /b 1 )
python -m pip install --user --quiet google-api-python-client google-auth-oauthlib google-auth-httplib2
python "%~dp0factory\yt_details.py" %*
echo.
pause
