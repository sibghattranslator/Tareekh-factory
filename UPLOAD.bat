@echo off
setlocal
cd /d "%~dp0"
title Tareekh Ki Kahani - UPLOAD
echo.
echo   AUTO UPLOADER: uploads the video + Shorts, subtitles, thumbnail and schedules them.
echo   Times must end in :00 :15 :30 or :45
echo.
set /p EP=  Episode (for example tk004): 
set /p LONGAT=  Long video date and time (for example 2026-11-14 18:00): 
set /p SHAT=  First Short date and time (for example 2026-11-14 07:45): 
set /p GAP=  Minutes between Shorts (press Enter for 60): 
if "%GAP%"=="" set GAP=60

set CHROME=
for %%P in ("%ProgramFiles%\Google\Chrome\Application\chrome.exe" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" "%LocalAppData%\Google\Chrome\Application\chrome.exe") do if exist %%P set CHROME=%%~P
if "%CHROME%"=="" (echo Chrome was not found. Install Google Chrome first. & pause & exit /b 1)

python -m pip install --user --quiet playwright
echo.
echo   Opening Chrome. FIRST TIME ONLY: sign in to Google in that window (the channel account).
start "" "%CHROME%" --remote-debugging-port=9222 --user-data-dir="%~dp0factory\yt_chrome" --no-first-run https://studio.youtube.com
timeout /t 8 >nul
python "%~dp0factory\yt_upload.py" %EP% --long-at "%LONGAT%" --shorts-start "%SHAT%" --gap %GAP%
echo.
echo   Finished. If anything failed, run UPLOAD.bat again (finished files are skipped). Screenshots of problems: yt_debug
pause
