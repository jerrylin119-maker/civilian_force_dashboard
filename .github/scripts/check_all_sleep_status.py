"""
每日巡檢：檢查使用者所有已部署的 Streamlit Community Cloud App 目前是否處於休眠狀態。

純唯讀監控 —— 不會點擊任何「喚醒」按鈕，也不會對任何 App 做任何修改；
只是像真人一樣打開每個網址、看實際渲染出來的內容，判斷目前是清醒還是休眠中，
最後輸出一份 Markdown 報告（供 workflow 發布成 GitHub Issue 留言）。

判斷邏輯（跟 civilian_force_dashboard 的 keep_awake.py 相同）：
新版 Streamlit Community Cloud 會把真正執行中的 App 包在一個
<iframe src=".../~/+/"> 裡面。休眠時這個 iframe 還不存在（或存在但是空的）；
清醒時，這個 iframe 裡面能讀到 App 真正渲染出來的畫面文字。
"""
import sys
from datetime import datetime, timezone, timedelta

from playwright.sync_api import sync_playwright

APPS = [
    ("civilian_force_dashboard", "https://civilianforcedashboard.streamlit.app/"),
    ("civil-force-dashboard", "https://civil-force-dashboard-6da5ftr3vhh47lldtwosna.streamlit.app/"),
    ("vocab700-app", "https://timmy-vocab700-app.streamlit.app/"),
    ("ttfd-scholarship", "https://ttfd-scholarship.streamlit.app/"),
    ("fire_safety_training", "https://firesafetytraining-ttfd.streamlit.app/"),
]

NAV_TIMEOUT_MS = 30_000
# 我們的檢查造訪本身就會觸發 Streamlit Cloud 開始喚醒該 App（跟人真的打開網址一樣），
# 所以逾時要給夠長，等它真的有機會完整開機完成，避免把「正在甦醒中」誤判成「持續休眠」。
IFRAME_WAIT_MS = 90_000


def check_one(playwright, url: str):
    """回傳 (status_emoji_text, note)。

    我們的檢查造訪本身就等於一次真人造訪，會觸發 Streamlit Cloud 開始喚醒該 App。
    所以要分兩階段判斷，才能同時回答「造訪當下是不是休眠」跟「這次有沒有順利醒過來」：
    1. 先用短逾時看造訪當下是不是已經醒著（沒有休眠問題）
    2. 如果不是，耐心多等一下，看這次造訪是否成功把它喚醒（代表原本確實睡著了）
    """
    browser = playwright.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        page.set_default_timeout(NAV_TIMEOUT_MS)
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            return "⚠️ 無法連線", str(e).splitlines()[0][:120]

        page.wait_for_timeout(3_000)  # 給外殼頁面一點時間決定要不要建立 App iframe
        app_frame = page.frame_locator('iframe[src*="/~/+/"]')

        # 階段 1：短逾時，看造訪當下是不是已經是醒著的
        try:
            body_text = app_frame.locator("body").inner_text(timeout=5_000)
            if body_text and body_text.strip():
                return "🟢 清醒", ""
        except Exception:
            pass

        # 階段 2：造訪當下是休眠狀態，耐心多等，看這次造訪能不能把它喚醒
        try:
            body_text = app_frame.locator("body").inner_text(timeout=IFRAME_WAIT_MS)
            if body_text and body_text.strip():
                return "🟡 原本休眠，已自動喚醒", "本次造訪時偵測到休眠，已成功喚醒"
        except Exception:
            pass
        return "😴 休眠中", "多次嘗試後仍無法確認已喚醒，可能需要人工檢查"
    finally:
        browser.close()


def main() -> int:
    taiwan_now = datetime.now(timezone.utc) + timedelta(hours=8)
    lines = [
        f"### 📅 {taiwan_now.strftime('%Y-%m-%d %H:%M')}（台灣時間）",
        "",
        "| App | 狀態 | 備註 | 網址 |",
        "|---|---|---|---|",
    ]

    any_problem = False
    with sync_playwright() as playwright:
        for name, url in APPS:
            status, note = check_one(playwright, url)
            if "休眠" in status or "連線" in status:
                any_problem = True
            print(f"{name}: {status} {note}")
            lines.append(f"| {name} | {status} | {note} | {url} |")

    lines.append("")
    if any_problem:
        lines.append("⚠️ 有 App 目前處於休眠或無法連線狀態，可能需要人工檢查。")
    else:
        lines.append("✅ 全部 App 目前都是清醒狀態。")

    report = "\n".join(lines)
    print("\n--- 報告內容 ---\n" + report)

    # 同時寫到 status/ 目錄（會被 workflow commit 回 repo）：這是刻意設計成可以被
    # 「git clone」讀取的持久化檔案，讓另一個雲端排程即使連不到一般外部網站/GitHub API
    # （這個雲端環境的網路政策會擋住這些），也能透過 git clone 這條被允許的管道讀到最新報告，
    # 進而把結果轉成一則真正的推播通知。
    import os

    os.makedirs("status", exist_ok=True)
    with open("status/latest_sleep_report.md", "w", encoding="utf-8") as f:
        f.write(report)

    with open("sleep_report.md", "w", encoding="utf-8") as f:
        f.write(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
