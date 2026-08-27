@echo off
chcp 65001 >nul
title Git 一鍵從 GitHub 拉取更新
set PATH=C:\Users\User\.gemini\antigravity\scratch\mingit\cmd;%PATH%
cls
echo ======================================================================
echo    🐙 民力科業務知識動態看板 - 從 GitHub 下載最新版本
echo ======================================================================
echo.
git pull origin main
echo.
echo ======================================================================
echo   ✅ 同步完成！
echo ======================================================================
pause
