@echo off
chcp 65001 >nul
title ERP系统 - 打包
cd /d "%~dp0"

echo ====================================
echo   ERP 系统打包程序
echo ====================================
echo.

echo [1/5] 检查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未安装 Python 或未添加到 PATH
    pause
    exit /b 1
)
echo     OK
echo.

echo [2/5] 安装依赖...
pip install Flask Werkzeug pywebview openpyxl -q
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)
pip install pyinstaller -q
echo     OK
echo.

echo [3/5] 清理旧的构建文件...
if exist build rmdir /s /q build 2>nul
if exist dist rmdir /s /q dist 2>nul
echo     OK
echo.

echo [4/5] 正在打包（约 1-3 分钟）...
pyinstaller --onefile --windowed ^
  --name "ERP系统" ^
  --add-data "templates;templates" ^
  --add-data "app/static;app/static" ^
  --hidden-import app ^
  --hidden-import app.config ^
  --hidden-import app.models ^
  --hidden-import app.security ^
  --hidden-import app.blueprints.auth ^
  --hidden-import app.blueprints.base ^
  --hidden-import app.blueprints.sales ^
  --hidden-import app.blueprints.purchase ^
  --hidden-import app.blueprints.finance ^
  --hidden-import app.blueprints.stock ^
  --hidden-import app.blueprints.report ^
  --hidden-import app.blueprints.invoice ^
  --hidden-import app.blueprints.voucher ^
  --hidden-import app.blueprints.advanced ^
  --hidden-import app.blueprints.ai ^
  --hidden-import app.blueprints.extras ^
  --hidden-import app.ai ^
  --hidden-import app.demo ^
  --hidden-import app.utils ^
  --hidden-import openpyxl ^
  --hidden-import openpyxl.workbook ^
  --hidden-import openpyxl.reader.excel ^
  --hidden-import webview ^
  --hidden-import webview.platforms.edgechromium ^
  --collect-all webview ^
  --collect-all openpyxl ^
  --exclude-module matplotlib ^
  --exclude-module numpy ^
  --exclude-module pandas ^
  --exclude-module tkinter ^
  --exclude-module PyQt5 ^
  --exclude-module PyQt6 ^
  --exclude-module PySide2 ^
  --exclude-module PySide6 ^
  main.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请检查上面的错误信息
    pause
    exit /b 1
)

echo.
echo [5/5] 完成！
echo.
echo ====================================
echo   打包成功
echo   输出目录: dist\ERP系统.exe
echo ====================================
echo.

:: 自动打开 dist 目录
explorer dist
pause