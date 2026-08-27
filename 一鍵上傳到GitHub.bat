@echo off
chcp 65001 >nul
title 民力科業務知識動態看板 - 一鍵上傳到 GitHub
cls
echo ======================================================================
echo    🚒 民力科業務知識動態看板 - GitHub 自動化上傳小精靈
echo ======================================================================
echo.
echo 說明：此工具會自動幫您打包專案並推送到您的 GitHub 儲存庫！
echo.
echo ----------------------------------------------------------------------
set /p repo_url="👉 請貼上您的 GitHub 儲存庫網址 (例如 https://github.com/xxx/yyy.git)："
echo ----------------------------------------------------------------------
echo.

if "%repo_url%"=="" (
    echo [錯誤] 您尚未輸入 GitHub 網址，請重新執行並輸入網址。
    pause
    exit /b
)

echo [1/5] 正在初始化 Git 儲存庫...
git init

echo [2/5] 正在加入所有看板程式碼與資料庫檔案...
git add .

echo [3/5] 正在建立初次版本封裝...
git commit -m "feat: 初次發布民力科業務知識動態看板"

echo [4/5] 正在設定主分支為 main...
git branch -M main

echo [5/5] 正在連線至您的 GitHub 並上傳...
git remote remove origin >nul 2>&1
git remote add origin %repo_url%
git push -u origin main --force

echo.
if %errorlevel% equ 0 (
    echo ======================================================================
    echo   🎉 恭喜！專案已成功 100%% 上傳到您的 GitHub！
    echo   現在您可以前往 GitHub 網頁查看您的看板專案了。
    echo ======================================================================
) else (
    echo ======================================================================
    echo   [提示] 若上傳未成功，請確認：
    echo   1. 電腦是否已安裝 Git (https://git-scm.com/download/win)
    echo   2. GitHub 網址是否正確
    echo   3. 是否已登入 GitHub 授權
    echo ======================================================================
)

pause
