@echo off
setlocal

if "%1"=="install" goto install
if "%1"=="lint" goto lint
if "%1"=="test" goto test
if "%1"=="build" goto build
if "%1"=="dev-dashboard" goto dev

echo Usage: dev.cmd [install^|lint^|test^|build^|dev-dashboard]
exit /b 1

:install
echo Installing backend dependencies...
cd backend
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install ruff
cd ..
echo Installing dashboard dependencies...
cd dashboard
call npm install
cd ..
goto end

:lint
echo Linting backend...
cd backend
ruff check .
cd ..
goto end

:test
echo Testing backend...
cd backend
python -m tests.test_oneway
cd ..
goto end

:build
echo Compiling backend...
cd backend
python -m compileall -q .
cd ..
echo Building dashboard...
cd dashboard
call npm run build
cd ..
goto end

:dev
echo Starting dashboard dev server...
cd dashboard
call npm run dev
cd ..
goto end

:end
