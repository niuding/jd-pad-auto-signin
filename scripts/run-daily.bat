@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo 没有找到 Python，请先安装 Python 3.9 以上版本。
  echo https://www.python.org/downloads/
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
python jd_daily_run.py
echo.
pause
