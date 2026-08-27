@echo off
chcp 65001 >nul
title 民力科業務知識動態看板
cls
echo ======================================================================
echo    🚒 民力科業務知識動態看板 啟動中...
echo ======================================================================
echo.
echo [1/2] 正在檢查 Python 與 Streamlit 環境...
python -m streamlit --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [警告] 尚未安裝 streamlit 套件，正在自動安裝依賴項...
    pip install -r requirements.txt
)

echo [2/2] 正在啟動看板服務並開啟瀏覽器...
echo.
echo ----------------------------------------------------------------------
echo   🌐 看板網址： http://localhost:8501
echo   🔐 預設維護密碼： 119
echo   (如未自動開啟，請直接點擊上方網址或貼至 Chrome / Edge 瀏覽器)
echo ----------------------------------------------------------------------
echo.
echo ※ 請保持此視窗開啟，關閉此視窗將會停止系統運行。
echo.

start http://localhost:8501
python -m streamlit run app.py --server.port=8501

pause
