@echo off
setlocal
cd /d "%~dp0"
title Tareekh Ki Kahani - UPLOAD
echo.
echo   AUTO UPLOADER - checks what is left, then uploads videos + Shorts with title, description,
echo   chapters, tags, thumbnail, Urdu + English subtitles and the schedule (settings: factory\upload_settings.txt)
echo.
set CHROME=
for %%P in ("%ProgramFiles%\Google\Chrome\Application\chrome.exe" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" "%LocalAppData%\Google\Chrome\Application\chrome.exe") do if exist %%P set CHROME=%%~P
if "%CHROME%"=="" (echo Chrome was not found. Install Google Chrome first. & pause & exit /b 1)
python -m pip install --user --quiet playwright
echo.
echo   Opening Chrome. FIRST TIME ONLY: sign in to Google in that window (the channel account).
start "" "%CHROME%" --remote-debugging-port=9222 --user-data-dir="%~dp0factory\yt_chrome" --no-first-run https://studio.youtube.com
timeout /t 8 >nul
python "%~dp0factory\yt_upload.py" %*
echo.
echo   Finished. If anything failed, run UPLOAD.bat again (finished files are skipped). Screenshots of problems: yt_debug
pause
