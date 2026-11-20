@echo off
chcp 65001 >nul
rem 符卡作业簿 · 答题浏览器（带调试端口，供「网页模式」使用）
rem 用独立配置目录，不影响你平时用的 Edge；第一次要在里面登录一次课程网站
setlocal
set "PORT=9222"
set "PROFILE=%LOCALAPPDATA%\SpellCardHomework\browser-profile"
set "URL=%~1"
if "%URL%"=="" set "URL=https://kysu.edu"

set "BROWSER=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%BROWSER%" set "BROWSER=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist "%BROWSER%" set "BROWSER=%ProgramFiles%\Microsoft\Edge Beta\Application\msedge.exe"
if not exist "%BROWSER%" set "BROWSER=%ProgramFiles(x86)%\Microsoft\Edge Beta\Application\msedge.exe"
if not exist "%BROWSER%" set "BROWSER=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%BROWSER%" set "BROWSER=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"

if not exist "%BROWSER%" (
  echo.
  echo   没找到 Edge / Chrome。
  echo   装好浏览器再试，或者手动执行：
  echo   msedge.exe --user-data-dir="%%LOCALAPPDATA%%\SpellCardHomework\browser-profile" --remote-debugging-port=9222
  echo.
  pause
  exit /b 1
)

echo 正在启动答题浏览器（调试端口 %PORT%）…
echo 第一次请在浏览器里用 kysu.edu 登录，之后会记住。
start "" "%BROWSER%" --user-data-dir="%PROFILE%" --remote-debugging-port=%PORT% --no-first-run --no-default-browser-check --disable-sync "%URL%"
exit /b 0

