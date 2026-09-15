"""
Streamlit Community Cloud 保活腳本
==================================
單純的 HTTP GET／一般連線監控服務（如 UptimeRobot、cron-job.org）對 Streamlit Community Cloud
的休眠機制無效：App 休眠時，這類請求只會收到一個靜態的 HTML 外殼並回應 200 OK，
背後真正的 Python 程式並未被啟動，休眠計時器也不會被重置。

這支腳本改用無頭瀏覽器（Playwright）像真人一樣造訪看板網址：等待頁面完整載入、
如果遇到休眠畫面就自動點擊「喚醒」按鈕，並確認畫面真的渲染出 App 內容後才視為成功。
由 .github/workflows/keep-awake.yml 排程每天自動執行一次。
"""
import sys
import time

from playwright.sync_api import sync_playwright

APP_URL = "https://civilianforcedashboard.streamlit.app/"
# Streamlit 休眠畫面上常見的喚醒按鈕文字（不同版本用字略有差異，全部嘗試一輪）
WAKE_BUTTON_TEXTS = ["Yes, get this app back up!", "get this app back up", "Wake up"]
# 側邊欄標題文字，畫面上出現代表 App 已經完整啟動、不再是休眠中
READY_TEXT = "民力看板控制台"
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 15


def try_wake_once(playwright) -> bool:
    browser = playwright.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        page.set_default_timeout(60_000)
        print(f"造訪 {APP_URL} ...")
        page.goto(APP_URL, wait_until="domcontentloaded")

        # App 休眠時，喚醒按鈕顯示在最外層的 Streamlit Cloud 外殼頁面（這時候
        # 實際執行中的 App iframe 根本還不存在）；若 App 本來就是醒著，這幾個
        # 按鈕都找不到，會直接跳過、往下等待畫面渲染完成即可。
        for btn_text in WAKE_BUTTON_TEXTS:
            try:
                page.locator(f"button:has-text('{btn_text}')").first.click(timeout=8_000)
                print(f"偵測到休眠喚醒按鈕「{btn_text}」，已點擊。")
                break
            except Exception:
                continue

        # 點擊喚醒後，Streamlit Cloud 才會開始啟動 App，啟動完成後才會把 App
        # 包進 <iframe src=".../~/+/">，因此要等到這個 iframe 出現、且裡面真的
        # 渲染出側邊欄標題文字，才代表 App 已經完整啟動、真正清醒。
        app_frame = page.frame_locator('iframe[src*="/~/+/"]')
        app_frame.get_by_text(READY_TEXT).first.wait_for(state="visible", timeout=90_000)
        print("✅ 確認 App 已經是清醒狀態（畫面已完整渲染）。")
        return True
    finally:
        browser.close()


def main() -> int:
    with sync_playwright() as playwright:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            print(f"--- 第 {attempt}/{MAX_ATTEMPTS} 次嘗試 ---")
            try:
                if try_wake_once(playwright):
                    return 0
            except Exception as e:
                print(f"⚠️ 本次嘗試失敗：{e}")
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)
        print("❌ 多次嘗試後仍無法確認 App 已喚醒，請人工檢查看板網址狀態。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
