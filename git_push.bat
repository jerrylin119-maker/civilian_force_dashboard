@echo off
chcp 65001 >nul
title Git 一鍵同步更新到 GitHub
cls
echo ======================================================================
echo    🐙 民力科業務知識動態看板 - 一鍵推送到 GitHub
echo ======================================================================
echo.
echo 正在檢查變更並準備提交...
git add .
set /p commit_msg="請輸入本次更新說明 (直接按 Enter 預設為 '更新民力科業務看板內容'): "
if "%commit_msg%"=="" set commit_msg=更新民力科業務看板內容

git commit -m "%commit_msg%"
echo.
echo 正在推送到 GitHub 遠端儲存庫...
git push origin main
if %errorlevel% neq 0 (
    echo.
    echo 嘗試推送到預設分支...
    git push
)

echo.
echo ======================================================================
echo   ✅ 同步完成！
echo ======================================================================
pause
