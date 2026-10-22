@echo off
setlocal EnableDelayedExpansion

:: 设置路径
set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%主脚本.ps1"

:: 检查主脚本是否存在
if not exist "%PS_SCRIPT%" (
    echo 错误: 找不到 PowerShell 脚本 "%PS_SCRIPT%"
    echo 请确保"主脚本.ps1"存在于同一目录下
    pause
    exit /b 1
)

echo 正在尝试以管理员权限启动主脚本...
echo.

:: 方法1: 使用Start-Process的默认方式
echo [方法1] 通过PowerShell请求管理员权限...
powershell -Command "try { Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -File \"%PS_SCRIPT%\"' -Verb RunAs -ErrorAction Stop; exit 0 } catch { exit 1 }" 2>nul

if !errorlevel! == 0 (
    echo 方法1成功 - 管理员权限已获取
    goto :success
) else (
    echo 方法1未成功，尝试方法2...
    echo.
)

:: 方法2: 使用mshta和VBScript的混合方法（改进版，不会关闭窗口）
echo [方法2] 通过混合方法请求管理员权限...
set "HTA_SCRIPT=%TEMP%\elevate_temp_%random%.hta"

:: 创建HTA文件，使用更安全的方式
echo ^<!DOCTYPE html^> > "%HTA_SCRIPT%"
echo ^<html^> >> "%HTA_SCRIPT%"
echo ^<head^> >> "%HTA_SCRIPT%"
echo ^<title^>请求管理员权限^</title^> >> "%HTA_SCRIPT%"
echo ^<HTA:APPLICATION ID="oApp" APPLICATIONNAME="Elevate" SHOWINTASKBAR="no" SYSMENU="no" CAPTION="no" WINDOWSTATE="minimize"^> >> "%HTA_SCRIPT%"
echo ^<script language="VBScript"^> >> "%HTA_SCRIPT%"
echo   On Error Resume Next >> "%HTA_SCRIPT%"
echo   Set shell = CreateObject("Shell.Application") >> "%HTA_SCRIPT%"
echo   shell.ShellExecute "powershell", "-ExecutionPolicy Bypass -File ""%PS_SCRIPT%""", "", "runas", 1 >> "%HTA_SCRIPT%"
echo   If Err.Number ^<^> 0 Then >> "%HTA_SCRIPT%"
echo     ' 如果出错，什么也不做 >> "%HTA_SCRIPT%"
echo   End If >> "%HTA_SCRIPT%"
echo   window.close >> "%HTA_SCRIPT%"
echo ^</script^> >> "%HTA_SCRIPT%"
echo ^</head^> >> "%HTA_SCRIPT%"
echo ^<body^> >> "%HTA_SCRIPT%"
echo ^</body^> >> "%HTA_SCRIPT%"
echo ^</html^> >> "%HTA_SCRIPT%"

:: 静默执行HTA，不等待完成
start /b "" mshta "%HTA_SCRIPT%"

:: 等待一段时间让UAC对话框出现
timeout /t 3 /nobreak >nul

:: 检查是否成功（通过检测PowerShell进程）
tasklist /fi "imagename eq powershell.exe" /fo csv | findstr /i "powershell" >nul
if !errorlevel! == 0 (
    echo 方法2成功 - 管理员权限已获取
) else (
    echo.
    echo 所有方法都未能成功获取管理员权限
    echo.
    echo 可能的原因：
    echo 1. 用户多次取消了UAC提示
    echo 2. 系统UAC被禁用或设置为最低级别
    echo 3. 当前用户没有管理员权限
    echo.
    echo 解决方案：
    echo 1. 重新运行此脚本并同意UAC提示
    echo 2. 手动右键点击"以管理员身份运行"
    echo 3. 联系系统管理员检查权限设置
    echo.
    pause
)

:success
:: 清理临时文件
if exist "%HTA_SCRIPT%" (
    timeout /t 2 /nobreak >nul
    del "%HTA_SCRIPT%" >nul 2>&1
)

echo.
echo 启动过程完成，当前窗口可以安全关闭
exit /b 0