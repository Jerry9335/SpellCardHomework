@echo off
chcp 65001 >nul
rem 符卡作业簿 · 答题浏览器（带调试端口，供「网页模式」使用）
rem 用独立配置目录，不影响你平时用的 Edge；第一次要在里面登录一次课程网站
rem 紫：这扇结界门由我来记门牌——不是自己开的门，我不会去关。
setlocal

set "PORT=%SCH_BARRIER_PORT%"
if "%PORT%"=="" set "PORT=9222"
set "PROFILE=%LOCALAPPDATA%\SpellCardHomework\browser-profile"

rem URL 改走环境变量。命令行参数里的 & 会被 cmd 当成命令分隔符，
rem 以前 https://x/?a=1&b=2 只会把 ?a 传进来，b=2 还会被当成一条命令执行。
set "URL=%SCH_START_URL%"
if "%URL%"=="" set "URL=%~1"
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
  exit /b 1
)

rem 记下门牌：告诉主程序「这个端口是我张开的」，关结界之前会核对。
if not exist "%LOCALAPPDATA%\SpellCardHomework" mkdir "%LOCALAPPDATA%\SpellCardHomework" >nul 2>nul
> "%LOCALAPPDATA%\SpellCardHomework\barrier.port" echo %PORT%

echo 正在启动答题浏览器（调试端口 %PORT%）…
start "" "%BROWSER%" --user-data-dir="%PROFILE%" --remote-debugging-port=%PORT% --no-first-run --no-default-browser-check --disable-sync "%URL%"
exit /b 0
