@echo off
chcp 65001 >nul
title ERP系统 - 打包分发
cd /d "%~dp0"

echo ====================================
echo   ERP 系统 - 打包分发包
echo ====================================
echo.

:: ---------- 检查 exe ----------
if not exist "dist\ERP系统.exe" (
    echo [错误] 未找到 dist\ERP系统.exe
    echo.
    echo 请先运行 build.bat 打包
    echo.
    pause
    exit /b 1
)
echo [1/3] 找到 ERP系统.exe

:: ---------- 获取版本号 ----------
set /p VERSION="请输入版本号（如 1.0，直接回车用日期）: "
if "%VERSION%"=="" (
    for /f "tokens=1-3 delims=/- " %%a in ('date /t') do set VERSION=%%a%%b%%c
)

set "PKG_NAME=ERP系统_v%VERSION%"
set "PKG_DIR=packages\%PKG_NAME%"

echo.
echo [2/3] 准备分发包...
if exist "%PKG_DIR%" rmdir /s /q "%PKG_DIR%"
mkdir "%PKG_DIR%"

:: 复制 exe
copy "dist\ERP系统.exe" "%PKG_DIR%\" >nul

:: 生成安装.bat
(
echo @echo off
echo chcp 65001 ^>nul
echo title ERP系统 - 安装
echo cd /d "%%~dp0"
echo.
echo echo ====================================
echo echo   ERP 系统安装程序
echo echo ====================================
echo echo.
echo if not exist "%%~dp0ERP系统.exe" ^(
echo     echo [错误] 找不到 ERP系统.exe
echo     pause
echo     exit /b 1
echo ^)
echo echo [1/4] 找到 ERP系统.exe
echo echo.
echo echo [2/4] 检查运行环境...
echo reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" ^>nul 2^>^&1
echo if errorlevel 1 ^(
echo     echo [提示] 如无法启动，请安装 WebView2:
echo     echo https://go.microsoft.com/fwlink/p/?LinkId=2124703
echo ^)
echo echo.
echo echo [3/4] 创建快捷方式...
echo set "EXE_PATH=%%~dp0ERP系统.exe"
echo set "WORK_DIR=%%~dp0"
echo powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\ERP系统.lnk'); $sc.TargetPath = '%%EXE_PATH%%'; $sc.WorkingDirectory = '%%WORK_DIR%%'; $sc.IconLocation = '%%EXE_PATH%%,0'; $sc.Save()"
echo echo.
echo echo [4/4] 完成！
echo echo.
echo echo ====================================
echo echo   安装成功，桌面已创建快捷方式
echo echo   默认账号 admin / admin123
echo echo ====================================
echo echo.
echo set /p LAUNCH="现在启动？(Y/N): "
echo if /i "%%LAUNCH%%"=="Y" start "" "%%EXE_PATH%%"
echo exit /b 0
) > "%PKG_DIR%\安装.bat"

:: 生成使用说明.txt
(
echo ERP 企业资源管理系统 - 使用说明
echo ================================================
echo.
echo 【安装步骤】
echo   1. 把本文件夹解压到任意位置（建议 D:\ERP）
echo   2. 双击「安装.bat」
echo   3. 桌面会自动创建「ERP系统」图标
echo   4. 双击桌面图标即可启动
echo.
echo 【首次登录】
echo   账号：admin
echo   密码：admin123
echo   ★ 建议登录后立即修改密码
echo.
echo 【数据存储】
echo   所有数据保存在本文件夹的 erp.db 文件中
echo   ★ 请勿删除该文件，否则数据丢失
echo   ★ 建议定期备份 erp.db 到移动硬盘或云盘
echo.
echo 【备份与恢复】
echo   程序内：「备份恢复」菜单 → 一键导出/导入
echo   手动：直接复制 erp.db 文件
echo.
echo 【常见问题】
echo   Q: 双击无反应？
echo   A: 安装 WebView2:
echo      https://go.microsoft.com/fwlink/p/?LinkId=2124703
echo.
echo   Q: 杀毒软件报毒？
echo   A: 添加到信任列表（Python 打包程序常见误报）
echo.
echo   Q: 数据丢失了？
echo   A: 检查是否误删 erp.db，可用备份恢复
echo.
echo 【技术支持】
echo   联系人：__________
echo   电话：__________
echo   微信：__________
echo.
echo ================================================
echo 版本：%VERSION%
echo 打包时间：%date% %time%
) > "%PKG_DIR%\使用说明.txt" 2>nul

:: 生成卸载.bat
(
echo @echo off
echo chcp 65001 ^>nul
echo title ERP系统 - 卸载
echo echo 将删除桌面和开始菜单快捷方式
echo set /p CONFIRM="确认？(Y/N): "
echo if /i not "%%CONFIRM%%"=="Y" exit /b 0
echo set "DESKTOP=%%USERPROFILE%%\Desktop"
echo if exist "%%DESKTOP%%\ERP系统.lnk" del "%%DESKTOP%%\ERP系统.lnk"
echo set "STARTMENU=%%APPDATA%%\Microsoft\Windows\Start Menu\Programs"
echo if exist "%%STARTMENU%%\ERP系统.lnk" del "%%STARTMENU%%\ERP系统.lnk"
echo echo 卸载完成，程序本体和数据请手动删除
echo pause
) > "%PKG_DIR%\卸载.bat"

echo     文件已准备到：%PKG_DIR%

:: ---------- 压缩 ----------
echo.
echo [3/3] 压缩为 zip...
powershell -NoProfile -Command ^
  "Compress-Archive -Path '%PKG_DIR%\*' -DestinationPath 'packages\%PKG_NAME%.zip' -Force"

if errorlevel 1 (
    echo [错误] 压缩失败
    pause
    exit /b 1
)

echo     已生成：packages\%PKG_NAME%.zip
echo.
echo ====================================
echo   分发包生成成功！
echo ====================================
echo.
echo   文件位置：packages\%PKG_NAME%.zip
echo   直接发给同事，让对方解压后运行「安装.bat」
echo.

explorer packages
pause