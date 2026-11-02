"""三個新上線系統的連結與操作手冊重點（來源：「民力科業務重點說明」文件）。

資料寫在程式裡而不是資料庫：承辦人在維護模式改業務卡片、或雲端備份還原後，這三個入口都不會被蓋掉。
要換網址或補充說明，直接改下面的 NEW_SYSTEMS 即可。
"""
import html

NEW_SYSTEMS = [
    {
        "key": "roster_cert",
        "icon": "🧑‍🚒",
        "name": "義消專長資料庫及新進人員服務證",
        "short": "義消專長資料庫＋服務證",
        "url": "https://claude.ai/artifact/Mw8XkNJLZpgMZtEM6mXa63",
        "link_label": "系統操作教學",
        "entry_url": "https://reurl.cc/gN66v7",
        "entry_label": "義消專長資料庫入口",
        "color": "#ea580c",
        "tint": "#fff7ed",
        "tab": "🚒 義消業務",
        "summary": "新進義消人員（含顧問）服務證製作辦理流程與注意事項",
        "steps": [
            "**核對名冊與發證日期**：各大隊確認近 2 年新進義消人員（含顧問）名冊及大隊核發派令日期，提供給所屬分隊。服務證發證日期＝派令核發日期。",
            "**分隊系統建檔與配號**：分隊登入系統「義消人員資料維護」新增基本資料，「加入日期」務必填派令生效日期。必填項目填完後勾選「立即配發下一個可用服務證號」並儲存，系統自動選號。已有資料但沒有證號者，到編輯區補齊後用同樣方式配號。",
            "**上傳大頭照**：檔名設為「姓名」（同名者加註單位，如：臺東分隊_王小明.jpg），上傳到指定的大頭照雲端資料夾。",
            "**大隊審核與資料匯出**：確認轄屬分隊完成建檔、取號、照片上傳後，進入「義消服務證管理」核對名冊，點「匯出資料」下載 Excel 清冊，並把大頭照插入「照片」欄位。",
            "**報局複核與製證**：大隊把貼妥照片的清冊列印、核章後陳報消防局複核，再進行服務證印製。",
        ],
        "note": "證號異常修正：分隊登入系統若收到證號格式錯誤提醒，請對照實際服務證修正。",
    },
    {
        "key": "assessment",
        "icon": "📝",
        "name": "義勇消防組織業務評核系統",
        "short": "義消業務評核系統",
        "url": "https://claude.ai/artifact/RVdUWGnPJyBM8Rm6mNcJW6#d2c397f6-7cc1",
        "link_label": "系統操作手冊",
        "entry_url": "",
        "entry_label": "",
        "color": "#7c3aed",
        "tint": "#f5f3ff",
        "tab": "🚒 義消業務",
        "summary": "本局預計 12 月底辦理義消業務評核",
        "steps": [
            "**辦理時程**：本局預計於 **12 月底** 辦理義消業務評核。",
            "**系統用途**：本系統提供各單位填寫「自評表」，在評核前先自我檢視。",
            "**操作方式**：請依系統操作手冊填寫，手冊連結在上方按鈕。",
        ],
        "note": "",
    },
    {
        "key": "subsidy_plan",
        "icon": "💰",
        "name": "補捐助案件計畫產生系統",
        "short": "補捐助計畫產生系統",
        "url": "https://claude.ai/artifact/8BaVrukXwZhCyqpJGR4fcw",
        "link_label": "系統操作",
        "entry_url": "",
        "entry_label": "",
        "color": "#0f766e",
        "tint": "#f0fdfa",
        "tab": "💰 補捐助業務",
        "summary": "被派任務寫議員補助款案件但沒有頭緒，就從這裡開始",
        "steps": [
            "**適用情境**：被指派辦理議員補助款案件，但不知道從哪裡下手。",
            "**怎麼用**：點上方按鈕進入系統，依畫面引導產生補捐助案件計畫。",
        ],
        "note": "",
    },
]

_BY_KEY = {s["key"]: s for s in NEW_SYSTEMS}


def _bold(text):
    """把 **粗體** 轉成 <b>，其餘文字先跳脫，避免手冊內容裡的符號弄壞版面。"""
    parts = html.escape(text).split("**")
    return "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts))


def render_sidebar_new_systems(st):
    """側邊欄最上方：三個新系統連結，各自用不同顏色醒目標示。"""
    st.markdown("#### ⭐ 三大新系統手冊操作連結")
    for i, s in enumerate(NEW_SYSTEMS, start=1):
        st.markdown(
            f'<a href="{s["url"]}" target="_blank" rel="noopener" style="text-decoration:none; color:#fff;">'
            f'<div style="background:{s["color"]}; color:#fff; padding:0.55rem 0.8rem; border-radius:8px; '
            f'margin-bottom:0.45rem; font-weight:700; font-size:0.92rem; line-height:1.35; '
            f'box-shadow:0 2px 6px rgba(0,0,0,0.18);">'
            f'<span style="background:#fff; color:{s["color"]}; border-radius:4px; padding:0 6px; '
            f'font-size:0.72rem; margin-right:6px;">NEW {i}</span>'
            f'<span style="color:#fff;">{s["icon"]} {html.escape(s["short"])} ↗</span></div></a>',
            unsafe_allow_html=True,
        )
    st.caption("以上為新上線系統，操作重點在對應的業務分頁。")


def render_system_highlights(st, tab_label):
    """在對應的業務分頁最上方，顯示該分頁的新系統入口與操作手冊重點。"""
    for s in NEW_SYSTEMS:
        if s["tab"] != tab_label:
            continue
        links = (
            f'<a href="{s["url"]}" target="_blank" rel="noopener" style="background:{s["color"]}; color:#fff; '
            f'padding:6px 14px; border-radius:6px; font-weight:700; text-decoration:none; margin-right:8px; '
            f'display:inline-block;">🔗 開啟{html.escape(s["link_label"])}</a>'
        )
        if s["entry_url"]:
            links += (
                f'<a href="{s["entry_url"]}" target="_blank" rel="noopener" style="background:#fff; color:{s["color"]}; '
                f'border:1px solid {s["color"]}; padding:5px 14px; border-radius:6px; font-weight:700; '
                f'text-decoration:none; display:inline-block;">🔑 {html.escape(s["entry_label"])}</a>'
            )
        st.markdown(
            f'<div style="background:{s["tint"]}; border:1px solid {s["color"]}; border-left:8px solid {s["color"]}; '
            f'border-radius:10px; padding:0.9rem 1.2rem; margin:0.4rem 0 0.6rem 0;">'
            f'<span style="background:{s["color"]}; color:#fff; border-radius:4px; padding:1px 8px; font-size:0.78rem; '
            f'font-weight:700; margin-right:8px;">🆕 新系統</span>'
            f'<span style="font-size:1.15rem; font-weight:800; color:{s["color"]};">{s["icon"]} {html.escape(s["name"])}</span>'
            f'<div style="color:#475569; font-size:0.92rem; margin:0.35rem 0 0.6rem 0;">{html.escape(s["summary"])}</div>'
            f'{links}</div>',
            unsafe_allow_html=True,
        )
        with st.expander(f"📖 {s['name']}：操作手冊重點", expanded=True):
            for n, step in enumerate(s["steps"], start=1):
                st.markdown(
                    f'<div style="margin:0.25rem 0;"><span style="background:{s["color"]}; color:#fff; border-radius:50%; '
                    f'display:inline-block; width:1.5rem; height:1.5rem; text-align:center; line-height:1.5rem; '
                    f'font-size:0.8rem; font-weight:700; margin-right:0.5rem;">{n}</span>{_bold(step)}</div>',
                    unsafe_allow_html=True,
                )
            if s["note"]:
                st.markdown(
                    f'<div style="background:#fef3c7; border:1px solid #fde68a; color:#92400e; border-radius:6px; '
                    f'padding:0.5rem 0.8rem; margin-top:0.6rem; font-weight:600;">⚠️ {html.escape(s["note"])}</div>',
                    unsafe_allow_html=True,
                )
