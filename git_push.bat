@echo off
chcp 65001 >nul
title Git 一鍵同步更新到 GitHub
set PATH=C:\Users\User\.gemini\antigravity\scratch\mingit\cmd;%PATH%
cls
echo ======================================================================
echo    🐙 民力科業務知識動態看板 - 一鍵同步推送到 GitHub
echo ======================================================================
echo.
git add .
set /p commit_msg="請輸入本次更新說明 (直接按 Enter 預設為 '更新民力科業務看板內容'): "
if "%commit_msg%"=="" set commit_msg=更新民力科業務看板內容

git commit -m "%commit_msg%"
echo.
echo 正在推送到 GitHub...
git push origin main
if %errorlevel% neq 0 (
    echo.
    echo 正在同步最新版本後推送...
    git pull origin main --rebase
    git push origin main
)

echo.
echo ======================================================================
echo   ✅ 同步處理完成！
echo ======================================================================
pause
