@echo off
echo ========================================================
echo  Iniciando Next.js Clinic Dashboard (http://localhost:3000)
echo ========================================================

REM Asegurar que la ruta de Node.js recien instalada este en el PATH
set "NODE_DIR=%LOCALAPPDATA%\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.19.0-win-x64"
if exist "%NODE_DIR%" (
    set "PATH=%NODE_DIR%;%PATH%"
)

cd /d "%~dp0clinic-dashboard"
call npm run dev
pause
