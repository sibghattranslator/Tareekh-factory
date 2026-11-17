@echo off
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
python -m pip install --user --quiet google-api-python-client google-auth-oauthlib google-auth-httplib2
echo.
echo   TAREEKH KI KAHANI - daily publish
echo   Upload your video + its 3 Shorts in YouTube Studio first (file name = title).
echo   This sets titles, descriptions, tags, thumbnails, subtitles and the dates:
echo   1 video + 3 Shorts per day, same day if nothing is queued, else next free day.
echo.
python factory\yt_details.py --plan
echo.
set /p OK=  Type YES to apply: 
if /I not "%OK%"=="YES" goto end
python factory\yt_details.py
:end
pause
