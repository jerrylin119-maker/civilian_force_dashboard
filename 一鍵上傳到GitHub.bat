@echo off
chcp 65001 >nul
title 民力科業務知識動態看板 - 一鍵上傳到 GitHub
set PATH=C:\Users\User\.gemini\antigravity\scratch\mingit\cmd;%PATH%
cls
echo ======================================================================
echo    🚒 民力科業務知識動態看板 - GitHub 自動化上傳小精靈
echo ======================================================================
echo.
echo [1/4] 正在檢查本機專案與 Git 狀態...
git init
git config user.name "jerrylin119-maker"
git config user.email "jerrylin119-maker@users.noreply.github.com"
git add .
git commit -m "feat: 初次發布民力科業務知識動態看板"
git branch -M main
git remote remove origin >nul 2>&1
git remote add origin https://github.com/jerrylin119-maker/civilian_force_dashboard.git

echo.
echo [2/4] 已綁定儲存庫： https://github.com/jerrylin119-maker/civilian_force_dashboard.git
echo [3/4] 正在連線至 GitHub 並推送上傳...
echo (※ 若跳出 GitHub 授權登入視窗，請點選瀏覽器登入授權即可)
echo.
git push -u origin main --force

echo.
if %errorlevel% equ 0 (
    echo ======================================================================
    echo   🎉 恭喜！專案已 100%% 成功上傳到您的 GitHub！
    echo   👉 您的儲存庫網址： https://github.com/jerrylin119-maker/civilian_force_dashboard
    echo ======================================================================
) else (
    echo ======================================================================
    echo   [提示] 若提示認證失敗，請依畫面指引登入 GitHub 授權即可完成上傳。
    echo ======================================================================
)
pause
