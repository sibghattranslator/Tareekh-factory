@echo off
cd /d "%~dp0"
python -m pip install --user --quiet uharfbuzz fonttools brotli
echo Downloading pictures only - no rendering...
python factory\pics_only.py
pause
