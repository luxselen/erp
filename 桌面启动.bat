@echo off
chcp 65001 >nul
title ERP 系统 - 单机模式

cd /d "%~dp0"

:: 清除服务器模式变量（防止冲突）
set ERP_MODE=

if exist "ERP系统.exe" (
    start "" ERP系统.exe
) else if exist "dist\ERP系统.exe" (
    start "" dist\ERP系统.exe
) else (
    start "" python main.py
)

exit