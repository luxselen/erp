@echo off
chcp 65001 >nul
title ERP 服务器 - 请勿关闭

cd /d "%~dp0"

echo ============================================================
echo   ERP 企业资源管理系统 - 服务器模式
echo ============================================================
echo.
echo   即将启动服务，启动后请勿关闭本窗口
echo   关闭本窗口将导致所有同事无法使用
echo.
echo   按任意键开始启动...
pause >nul

:: 设置环境变量
set ERP_MODE=server
set ERP_PORT=5000

:: 启动（优先用 exe，没有则用 python）
if exist "ERP系统.exe" (
    ERP系统.exe
) else if exist "dist\ERP系统.exe" (
    dist\ERP系统.exe
) else (
    python main.py
)

echo.
echo 服务已停止
pause