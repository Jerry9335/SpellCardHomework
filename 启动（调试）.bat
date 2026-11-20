@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Shinichi の練習小工具（调试启动）===
where python >nul 2>nul
if errorlevel 1 (
  echo 没找到 python，请先安装 Python 3.10+ 并勾选 Add to PATH。
  pause
  exit /b 1
)
python app.pyw
if errorlevel 1 (
  echo.
  echo 程序异常退出，错误信息见上。
  pause
)
