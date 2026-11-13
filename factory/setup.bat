@echo off
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Python is not installed. Install it from https://www.python.org/downloads/
  echo  IMPORTANT: tick "Add python.exe to PATH" during install, then run this again.
  exit /b 1
)
if exist "%~dp0.ready3" exit /b 0
echo First run: installing tools (one time only, needs internet)...
python -m pip install --user --quiet edge-tts pillow imageio-ffmpeg sounddevice soundfile numpy arabic-reshaper python-bidi uharfbuzz fonttools brotli
if errorlevel 1 ( echo Install failed - check internet and try again. & exit /b 1 )
echo ok> "%~dp0.ready3"
exit /b 0
