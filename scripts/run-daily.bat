@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 找一个真能用的 Python：商店里的占位 python.exe 会被 -c 验证挡掉
set "PYCMD="
if defined JD_PYTHON if exist "%JD_PYTHON%" set PYCMD="%JD_PYTHON%"

if not defined PYCMD (
  py -3 -c "import sys" >nul 2>nul && set "PYCMD=py -3"
)
if not defined PYCMD (
  python -c "import sys" >nul 2>nul && set "PYCMD=python"
)
if not defined PYCMD (
  for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%USERPROFILE%\.workbuddy\binaries\python\versions\*") do (
    if exist "%%D\python.exe" set PYCMD="%%D\python.exe"
  )
)

if not defined PYCMD (
  echo.
  echo 没找到可用的 Python，请先安装 Python 3.9 以上版本：
  echo https://www.python.org/downloads/
  echo 安装时记得勾上 Add Python to PATH。
  echo.
  pause
  exit /b 1
)

if not exist config.json (
  echo 第一次运行，正在生成配置文件...
  copy /y config.example.json config.json >nul
)

echo 开始执行今天的京东签到，请保持平板已解锁并连着数据线。
echo.
%PYCMD% jd_daily_run.py
echo.
pause
