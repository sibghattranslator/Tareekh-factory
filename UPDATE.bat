@echo off
chcp 65001 >nul
title Tareekh Ki Kahani - UPDATE
cd /d "%~dp0"
where git >nul 2>nul
if errorlevel 1 ( echo Git is not installed: https://git-scm.com/download/win & pause & exit /b 1 )
if not exist ".git" (
  git init -q
  git remote add origin https://github.com/sibghattranslator/Tareekh-factory.git
)
echo Getting the newest factory files from GitHub ...
git fetch origin main
if errorlevel 1 ( echo Could not reach GitHub. Check internet / sign-in. & pause & exit /b 1 )
git checkout -f -B main origin/main
del "factory\.ready3" 2>nul
call "%~dp0factory\setup.bat"
echo.
echo UPDATED. Your pictures, recordings and finished videos were not touched.
pause
