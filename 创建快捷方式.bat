@echo off
chcp 65001 >nul
title 创建 ERP 快捷方式

echo 请输入服务器地址（例如 192.168.1.100:5000）：
set /p SERVER_IP=

if "%SERVER_IP%"=="" (
    echo 地址不能为空
    pause
    exit /b 1
)

set URL=http://%SERVER_IP%

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$sc = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\ERP系统.url');" ^
  "$sc.TargetPath = '%URL%';" ^
  "$sc.Save()"

echo.
echo 桌面已创建「ERP系统」快捷方式
echo 双击即可访问 %URL%
echo.
pause