import json
# -*- coding: utf-8 -*-
"""
app.py - 臺東縣消防局民力訓練科 業務知識動態看板
Streamlit 主程式：
1. 專業義消承辦人情境導引 (僅精純呈現情境說明與SOP/系統連結，不顯示多餘卡片標籤)
2. 5大業務分類分頁與全域搜尋
3. 承辦人點選即列出業務清單，點擊業務 1 秒切換頁面並自動定位展開 SOP！
4. 最新異動紅字醒目提示
5. 我有話要說雙向回饋與回覆看板 (以臺東縣消防局四大外勤大隊與各分隊為選填範例)
6. 科內承辦人維護模式 (Excel批次編輯、單筆維護、導引維護、留言管理、CSV備份與還原)
"""

import streamlit as st
import pandas as pd
import re
from datetime import datetime
import database as db

# 頁面配置
st.set_page_config(
    page_title="臺東縣消防局民力訓練科 — 業務知識動態看板",
    page_icon="🚒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化資料庫
# 初始化資料庫
db.init_db()

# 若已綁定 Google 試算表，每次開啟/重整頁面自動即時同步最新資料！
if "has_auto_synced" not in st.session_state:
    try:
        db.auto_sync_from_gsheet()
        st.session_state["has_auto_synced"] = True
    except Exception:
        pass

# 安全查詢封裝函式 (防止任何雲端模組快取導致的 AttributeError)
def get_tasks_for_officer(officer_name):
    """安全取得指定承辦人負責之所有業務項目"""
    try:
        if hasattr(db, "get_tasks_for_officer"):
            return db.get_tasks_for_officer(officer_name)
    except Exception:
        pass
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        if not officer_name or officer_name == "全部承辦人":
            cursor.execute("SELECT id, category, subcategory, title, owner, status FROM TaskDatabase ORDER BY category, id")
        else:
            cursor.execute("SELECT id, category, subcategory, title, owner, status FROM TaskDatabase WHERE owner LIKE ? ORDER BY category, id", (f"%{officer_name}%",))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception:
        return []

def search_tasks_for_jump(query_str):
    """安全全文檢索業務項目清單"""
    try:
        if hasattr(db, "search_tasks_for_jump"):
            return db.search_tasks_for_jump(query_str)
    except Exception:
        pass
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        q = f"%{query_str.strip()}%"
        cursor.execute("""
            SELECT id, category, subcategory, title, owner, status 
            FROM TaskDatabase 
            WHERE title LIKE ? OR subcategory LIKE ? OR owner LIKE ? OR content_detail LIKE ? OR update_highlight LIKE ?
            ORDER BY category, id
        """, (q, q, q, q, q))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception:
        return []

# 初始化 Session State
if "is_admin" not in st.session_state:
    st.session_state["is_admin"] = False
if "flash_message" not in st.session_state:
    st.session_state["flash_message"] = None
if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = "🎖️ 專業義消承辦人"
if "target_task_title" not in st.session_state:
    st.session_state["target_task_title"] = None
if "selected_sidebar_owner" not in st.session_state:
    st.session_state["selected_sidebar_owner"] = "全部承辦人"
if "search_query" not in st.session_state:
    st.session_state["search_query"] = ""

def set_flash_message(text, msg_type="success", icon="💾"):
    """設定跨頁持久通知訊息並觸發右下角 Toast 提示"""
    st.session_state["flash_message"] = {"text": text, "type": msg_type}
    try:
        st.toast(text, icon=icon)
    except Exception:
        pass

def show_flash_message():
    """顯示並清除目前的通知訊息"""
    if st.session_state.get("flash_message"):
        msg = st.session_state["flash_message"]
        if msg["type"] == "success":
            st.success(msg["text"])
        elif msg["type"] == "warning":
            st.warning(msg["text"])
        elif msg["type"] == "error":
            st.error(msg["text"])
        else:
            st.info(msg["text"])
        st.session_state["flash_message"] = None

# 自訂樣式 (CSS)
st.markdown("""
<style>
    /* 全域字體與色彩 */
    .main-header {
        background: linear-gradient(135deg, #0f2b48 0%, #1e3a8a 50%, #2563eb 100%);
        color: white;
        padding: 1.4rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.2rem;
        box-shadow: 0 4px 12px rgba(30, 58, 138, 0.15);
    }
    .main-header h1 {
        color: white !important;
        font-size: 1.85rem;
        font-weight: 700;
        margin-bottom: 0.3rem;
    }
    .main-header p {
        color: #e0e7ff;
        font-size: 0.95rem;
        margin-bottom: 0;
    }

    /* 頂部現代導航標籤列樣式 */
    div[data-testid="stRadio"] > div[role="radiogroup"] {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        background: #f1f5f9;
        padding: 6px;
        border-radius: 10px;
        border: 1px solid #e2e8f0;
        margin-bottom: 1.5rem;
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] > label {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        padding: 8px 16px;
        border-radius: 8px;
        cursor: pointer;
        font-weight: 600;
        color: #334155;
        transition: all 0.2s ease;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] > label:hover {
        background: #eff6ff;
        border-color: #3b82f6;
        color: #1d4ed8;
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] > label[data-checked="true"],
    div[data-testid="stRadio"] > div[role="radiogroup"] > label:has(input:checked) {
        background: #2563eb !important;
        color: #ffffff !important;
        border-color: #1d4ed8 !important;
        box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3) !important;
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] > label div[data-testid="stMarkdownContainer"] p {
        font-size: 0.95rem;
        font-weight: 600;
        margin: 0;
    }

    /* 專業義消承辦人專屬精簡情境卡片 */
    .guide-clean-container {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.5rem 1.8rem;
        margin-bottom: 1.8rem;
        box-shadow: 0 3px 10px rgba(0, 0, 0, 0.04);
        border-left: 6px solid #2563eb;
    }
    .guide-clean-header {
        display: flex;
        align-items: center;
        margin-bottom: 0.8rem;
    }
    .guide-clean-title {
        font-size: 1.3rem;
        font-weight: 700;
        color: #1e3a8a;
    }
    .guide-clean-badge {
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        color: #1d4ed8;
        padding: 0.2rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.82rem;
        font-weight: 600;
        margin-left: 0.8rem;
    }
    .guide-desc-box {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-left: 4px solid #3b82f6;
        border-radius: 8px;
        padding: 0.9rem 1.2rem;
        color: #1e293b;
        font-size: 0.96rem;
        line-height: 1.6;
        margin-bottom: 0.8rem;
    }

    /* KPI 卡片 */
    .metric-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.03);
        border-top: 4px solid #3b82f6;
    }
    .metric-card-alert {
        border-top: 4px solid #dc2626;
        background: #fff5f5;
    }
    .metric-card-warning {
        border-top: 4px solid #f59e0b;
    }
    .metric-card-success {
        border-top: 4px solid #10b981;
    }
    .metric-title {
        color: #64748b;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        margin-bottom: 0.3rem;
    }
    .metric-value {
        color: #0f172a;
        font-size: 1.8rem;
        font-weight: 700;
    }

    /* 業務項目卡片 */
    .task-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 1.2rem 1.4rem;
        margin-bottom: 1.2rem;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .task-card:hover {
        box-shadow: 0 6px 16px rgba(0,0,0,0.08);
        border-color: #cbd5e1;
    }
    .task-card-highlighted {
        border-left: 6px solid #dc2626;
        background: linear-gradient(to right, #fffafa 0%, #ffffff 100%);
    }
    .task-card-target-focus {
        border: 2px solid #2563eb !important;
        border-left: 8px solid #2563eb !important;
        background: linear-gradient(to right, #eff6ff 0%, #ffffff 100%) !important;
        box-shadow: 0 4px 16px rgba(37, 99, 235, 0.2) !important;
    }

    /* 異動重點醒目紅字警告框 */
    .highlight-banner {
        background: #fee2e2;
        border: 1px solid #fca5a5;
        border-left: 5px solid #dc2626;
        color: #991b1b;
        padding: 0.75rem 1rem;
        border-radius: 6px;
        font-size: 0.95rem;
        font-weight: 600;
        margin: 0.7rem 0 1rem 0;
        box-shadow: 0 2px 4px rgba(220, 38, 38, 0.08);
        animation: pulse-border 2.5s infinite;
    }
    @keyframes pulse-border {
        0% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.3); }
        70% { box-shadow: 0 0 0 6px rgba(220, 38, 38, 0); }
        100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0); }
    }

    /* 狀態標籤 */
    .badge-status {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
        font-size: 0.78rem;
        font-weight: 600;
        margin-left: 0.5rem;
    }
    .badge-normal { background: #dcfce7; color: #15803d; border: 1px solid #86efac; }
    .badge-running { background: #dbeafe; color: #1d4ed8; border: 1px solid #93c5fd; }
    .badge-planning { background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }
    .badge-reimburse { background: #ffedd5; color: #c2410c; border: 1px solid #fdba74; }
    .badge-closed { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }

    .badge-subcat {
        background: #ede9fe;
        color: #5b21b6;
        padding: 0.2rem 0.55rem;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-right: 0.4rem;
    }

    /* 補捐助流程進度指示器 */
    .pipeline-step {
        display: inline-block;
        padding: 0.4rem 0.8rem;
        margin: 0.2rem 0.15rem;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
        border: 1px solid #e2e8f0;
    }
    .step-active { background: #2563eb; color: white; border-color: #1d4ed8; }
    .step-pending { background: #f8fafc; color: #64748b; }
    .step-done { background: #ecfdf5; color: #047857; border-color: #a7f3d0; }

    /* 連結藥丸標籤 */
    .link-box {
        display: inline-block;
        background: #f0fdfa;
        border: 1px solid #99f6e4;
        color: #0f766e;
        padding: 0.35rem 0.8rem;
        border-radius: 6px;
        font-size: 0.88rem;
        margin: 0.25rem 0.4rem 0.25rem 0;
        font-weight: 600;
    }
    .pending-box {
        display: inline-block;
        background: #f8fafc;
        border: 1px dashed #cbd5e1;
        color: #64748b;
        padding: 0.35rem 0.8rem;
        border-radius: 6px;
        font-size: 0.88rem;
        margin: 0.25rem 0.4rem 0.25rem 0;
    }

    /* 回饋留言卡片 */
    .feedback-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 1.2rem 1.4rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 6px rgba(0,0,0,0.03);
    }
    .feedback-reply-box {
        background: #f0fdf4;
        border: 1px solid #bbf7d0;
        border-left: 5px solid #10b981;
        padding: 0.8rem 1rem;
        border-radius: 6px;
        margin-top: 0.8rem;
        color: #166534;
        font-size: 0.92rem;
    }
</style>
""", unsafe_allow_html=True)

# 系統頂部橫幅
st.markdown("""
<div class="main-header">
    <div style="display: flex; align-items: center; justify-content: space-between;">
        <div>
            <h1>🚒 臺東縣消防局民力訓練科 — 業務知識動態看板</h1>
            <p>Taitung County Fire Bureau - Civilian & Volunteer Force Training Division | 專業義消承辦人導引 • 承辦人業務即選直達 • 我有話要說雙向回饋</p>
        </div>
        <div style="text-align: right; font-size: 0.85rem; opacity: 0.9;">
            📅 資料庫狀態：<strong>已連線</strong><br>
            🏢 臺東縣消防局 民力訓練科
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# 顯示任何跨頁通知提示
show_flash_message()

# 分類圖示對照
CATEGORY_ICON_MAP = {
    "義消業務": ("🚒 義消業務", "🚒"),
    "義消福利": ("🎁 義消福利", "🎁"),
    "補捐助業務": ("💰 補捐助業務", "💰"),
    "訓練業務": ("🎯 訓練業務", "🎯"),
    "其他推動業務": ("🌟 其他推動業務", "🌟")
}

# 側邊欄設計 (★ 依承辦人即時列出業務並支援點擊直達切換頁面)
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/fire-truck.png", width=60)
    st.title("民力看板控制台")
    st.caption("🏢 臺東縣消防局 民力訓練科")
    st.markdown("---")

    # 1. 👤 依承辦人快速查閱與點擊直達
    st.subheader("👤 依承辦人快速查閱與直達")
    all_owners = ["全部承辦人"] + db.get_owners_list()
    cur_owner_idx = all_owners.index(st.session_state["selected_sidebar_owner"]) if st.session_state["selected_sidebar_owner"] in all_owners else 0
    sel_owner = st.selectbox("請選擇科內承辦人", all_owners, index=cur_owner_idx, key="sidebar_owner_picker")
    st.session_state["selected_sidebar_owner"] = sel_owner

    # 即時顯示該承辦人負責的所有業務項目清單 (點擊直達該頁面)
    officer_tasks = get_tasks_for_officer(sel_owner)
    
    if sel_owner != "全部承辦人":
        st.markdown(f"**📋 【{sel_owner}】負責業務 ({len(officer_tasks)} 項，點擊直達)：**")
    else:
        st.markdown(f"**📋 全科列管業務清單 ({len(officer_tasks)} 項，點擊直達)：**")

    if not officer_tasks:
        st.caption("該承辦人目前無列管業務。")
    else:
        for ot in officer_tasks:
            target_tab_name = CATEGORY_ICON_MAP.get(ot["category"], (ot["category"], "📄"))[0]
            cat_icon = CATEGORY_ICON_MAP.get(ot["category"], ("", "📄"))[1]
            btn_label = f"{cat_icon} {ot['title']}"
            
            if st.button(btn_label, key=f"btn_jump_task_{ot['id']}", use_container_width=True):
                st.session_state["active_tab"] = target_tab_name
                st.session_state["target_task_title"] = ot["title"]
                set_flash_message(f"🚀 已切換至【{target_tab_name}】並為您定位【{ot['title']}】！", icon="🎯")
                st.rerun()

    st.markdown("---")

    # 2. 🔍 業務關鍵字搜尋與直達
    st.subheader("🔍 關鍵字搜尋與直達")
    with st.form("quick_search_form"):
        kw_input = st.text_input("輸入關鍵字 (業務名稱/SOP/法規)", value=st.session_state["search_query"], placeholder="例：健檢、消防衣、補捐助...")
        col_qs1, col_qs2 = st.columns([1, 1])
        with col_qs1:
            btn_kw_search = st.form_submit_button("🔍 搜尋", type="primary", use_container_width=True)
        with col_qs2:
            btn_kw_reset = st.form_submit_button("🔄 清除", use_container_width=True)

        if btn_kw_search:
            st.session_state["search_query"] = kw_input.strip()
            st.rerun()
        if btn_kw_reset:
            st.session_state["search_query"] = ""
            st.rerun()

    if st.session_state["search_query"]:
        search_results = search_tasks_for_jump(st.session_state["search_query"])
        st.markdown(f"**🔎 搜尋「{st.session_state['search_query']}」結果 ({len(search_results)} 項)：**")
        if not search_results:
            st.caption("無符合關鍵字的業務項目。")
        else:
            for s_task in search_results:
                target_tab_name = CATEGORY_ICON_MAP.get(s_task["category"], (s_task["category"], "📄"))[0]
                cat_icon = CATEGORY_ICON_MAP.get(s_task["category"], ("", "📄"))[1]
                if st.button(f"{cat_icon} {s_task['title']}", key=f"btn_search_jump_{s_task['id']}", use_container_width=True):
                    st.session_state["active_tab"] = target_tab_name
                    st.session_state["target_task_title"] = s_task["title"]
                    set_flash_message(f"🚀 已為您定位至【{s_task['title']}】！", icon="🎯")
                    st.rerun()

    st.markdown("---")

    # 3. 科內維護模式（管理員登入）
    st.subheader("🔐 科內維護模式")
    if not st.session_state["is_admin"]:
        admin_pass = st.text_input("請輸入管理密碼", type="password", help="預設科內維護密碼為：119")
        if st.button("🔓 啟用線上維護模式", use_container_width=True):
            if admin_pass in ["119", "admin119", "minli119"]:
                st.session_state["is_admin"] = True
                set_flash_message("✅ 已切換至科內維護模式！所有表格與設定均可即時線上編輯。", icon="🔓")
                st.rerun()
            else:
                st.error("❌ 密碼錯誤，請洽民力訓練科系統管理員。")
    else:
        st.success("🟢 已啟用維護權限（可即時編輯與回覆留言）")
        if st.button("🔒 鎖定 / 退出維護模式", use_container_width=True):
            st.session_state["is_admin"] = False
            set_flash_message("🔒 已退出維護模式。", msg_type="info", icon="🔒")
            st.rerun()

    st.markdown("---")

    # 4. 資料庫備份與匯出
    st.subheader("💾 資料庫備份與匯出")
    all_df = db.get_all_tasks_df()
    csv_data = all_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        label="📥 匯出完整 CSV 備份",
        data=csv_data,
        file_name=f"ttfd_minli_tasks_backup_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True
    )


# 全域 KPI 統計指標
stats = db.get_summary_stats()
col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)

with col_kpi1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">📋 列管業務總數</div>
        <div class="metric-value">{stats['total']} <span style="font-size:1rem;color:#64748b;">項</span></div>
    </div>
    """, unsafe_allow_html=True)

with col_kpi2:
    st.markdown(f"""
    <div class="metric-card metric-card-warning">
        <div class="metric-title">🚀 規劃與執行中案件</div>
        <div class="metric-value">{stats['in_progress']} <span style="font-size:1rem;color:#64748b;">項</span></div>
    </div>
    """, unsafe_allow_html=True)

with col_kpi3:
    st.markdown(f"""
    <div class="metric-card metric-card-alert">
        <div class="metric-title">⚠️ 最新異動宣導提醒</div>
        <div class="metric-value" style="color:#dc2626;">{stats['highlight']} <span style="font-size:1rem;color:#dc2626;">則</span></div>
    </div>
    """, unsafe_allow_html=True)

with col_kpi4:
    st.markdown(f"""
    <div class="metric-card metric-card-success">
        <div class="metric-title">💬 我有話要說回饋數</div>
        <div class="metric-value" style="color:#047857;">{stats['feedback_total']} <span style="font-size:1rem;color:#64748b;">則 ({stats['feedback_replied']}已覆)</span></div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# 輔助函式：取得狀態 Badge HTML
def get_status_badge(status):
    badge_map = {
        "常態辦理": ("badge-normal", "🟢 常態辦理"),
        "執行中": ("badge-running", "🔵 執行中"),
        "規劃中": ("badge-planning", "🟡 規劃中"),
        "待核銷": ("badge-reimburse", "🟠 待核銷"),
        "已結案": ("badge-closed", "⚪ 已結案")
    }
    css_class, label = badge_map.get(status, ("badge-normal", status))
    return f'<span class="badge-status {css_class}">{label}</span>'



# 輔助函式：將 Google Drive 連結轉換為可直連檢視的圖片網址
def format_gdrive_image_url(url):
    match = re.search(r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)', url)
    if match:
        f_id = match.group(1)
        return f"https://lh3.googleusercontent.com/d/{f_id}"
    return url


# 輔助函式：解析並渲染附件、表單與圖片 (自動判斷圖檔、文件或系統連結)
def render_doc_links(links_text):
    if not links_text or not links_text.strip():
        return
    
    lines = [line.strip() for line in links_text.splitlines() if line.strip()]
    
    images_list = []
    docs_list = []
    links_list = []
    
    for line in lines:
        if "(待補)" in line or "（待補）" in line:
            links_list.append(("pending", line, ""))
            continue
            
        urls = re.findall(r'https?://[^\s<>"\']+', line)
        if urls:
            url = urls[0]
            label = line.replace(url, "").strip(":： -•")
            if not label:
                label = "點擊開啟系統 / 文件連結"
            
            # 判斷是否為圖檔
            is_image = any(ext in url.lower() for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]) or                        any(k in label for k in ["圖", "流程圖", "示意圖", "照片", "架構圖", "海報", "範例圖", "截圖"])
            
            # 判斷是否為文件 / 表單下載
            is_doc = any(ext in url.lower() for ext in [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".odt", ".ods", ".zip", ".rar"]) or                      any(k in label for k in ["下載", "表單", "申請表", "附件", "公文", "要點", "手冊", "範本", "清冊", "簽呈"])
            
            if is_image:
                direct_img_url = format_gdrive_image_url(url)
                images_list.append((label, direct_img_url, url))
            elif is_doc:
                docs_list.append((label, url))
            else:
                links_list.append(("link", label, url))
        else:
            links_list.append(("text", line, ""))

    # 1. 渲染文件與表單下載區
    if docs_list:
        st.markdown("**📥 相關附件、申請表單與法規公文下載：**")
        for label, url in docs_list:
            # 判斷副檔名圖示
            icon = "📄"
            if any(ext in url.lower() for ext in [".pdf"]): icon = "📑"
            elif any(ext in url.lower() for ext in [".xls", ".xlsx", ".ods"]): icon = "📊"
            elif any(ext in url.lower() for ext in [".doc", ".docx", ".odt"]): icon = "📝"
            elif any(ext in url.lower() for ext in [".zip", ".rar"]): icon = "📦"
            
            st.markdown(
                f"<div style='display:inline-block; margin:4px 6px 4px 0;'>"
                f"<a href='{url}' target='_blank' style='text-decoration:none;'>"
                f"<span style='background:#eff6ff; border:1px solid #bfdbfe; color:#1d4ed8; padding:6px 12px; border-radius:6px; font-weight:600; font-size:0.9rem; display:inline-flex; align-items:center;'>"
                f"{icon} {label} &nbsp;⬇️"
                f"</span></a></div>",
                unsafe_allow_html=True
            )
        st.markdown("<br>", unsafe_allow_html=True)

    # 2. 渲染系統入口與外部連結區
    if links_list:
        st.markdown("**🌐 相關線上管制系統 / 外部連結：**")
        for item_type, label, url in links_list:
            if item_type == "pending":
                st.markdown(f"<div class='pending-box'>⏳ {label}</div>", unsafe_allow_html=True)
            elif item_type == "link":
                st.markdown(f"<div class='link-box'>🔗 <a href='{url}' target='_blank' style='text-decoration:none;color:#0f766e;'><strong>{label}</strong></a> &nbsp;<span style='font-size:0.8rem;color:#64748b;'>({url})</span></div>", unsafe_allow_html=True)
            else:
                st.markdown(f"- 📄 {label}")
        st.markdown("<br>", unsafe_allow_html=True)

    # 3. 渲染圖檔與流程示意圖區 (直接展開顯示清晰圖片)
    if images_list:
        st.markdown("**🖼️ 業務流程圖 / 作業示意圖表：**")
        for img_label, direct_url, orig_url in images_list:
            st.caption(f"📌 {img_label}")
            try:
                st.image(direct_url, caption=img_label, use_container_width=True)
            except Exception:
                st.markdown(f"<a href='{orig_url}' target='_blank'>🔗 點擊開啟圖片：{img_label}</a>", unsafe_allow_html=True)


# 輔助函式：渲染單張業務卡片 (支援被點擊直達時高亮與自動展開)
def render_task_card(task):
    is_targeted = bool(st.session_state.get("target_task_title") == task["title"])
    has_highlight = bool(task.get("update_highlight") and str(task["update_highlight"]).strip())
    
    if is_targeted:
        card_class = "task-card task-card-target-focus"
    elif has_highlight:
        card_class = "task-card task-card-highlighted"
    else:
        card_class = "task-card"
    
    status_html = get_status_badge(task['status'])
    subcat_html = f"<span class='badge-subcat'>📁 {task['subcategory']}</span>" if task.get('subcategory') else ""
    target_badge_html = "<span style='background:#2563eb;color:white;padding:2px 8px;border-radius:4px;font-size:0.8rem;font-weight:700;margin-left:0.5rem;'>🎯 目標業務已定位</span>" if is_targeted else ""

    owner_str = task['owner'] or '未指派'
    updated_str = task['last_updated']
    
    # 採用緊湊 HTML 避免 Markdown 4空格縮排誤判為代碼區塊
    card_html = (
        f'<div class="{card_class}">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;">'
        f'<div style="margin-bottom:0.4rem;">{subcat_html}<span style="font-size:1.15rem;font-weight:700;color:#1e293b;">{task["title"]}</span>{status_html}{target_badge_html}</div>'
        f'<div style="font-size:0.88rem;color:#475569;">👤 承辦人：<strong style="color:#0f172a;background:#f1f5f9;padding:2px 6px;border-radius:4px;">{owner_str}</strong> &nbsp;|&nbsp; 🕒 最後更新：{updated_str}</div>'
        f'</div>'
        f'</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)
    
    if has_highlight:
        highlight_html = f'<div class="highlight-banner">{task["update_highlight"]}</div>'
        st.markdown(highlight_html, unsafe_allow_html=True)

    # 若為點擊直達之業務，自動展開其 SOP！
    expander_expanded = is_targeted
    with st.expander("📖 查看完整 SOP 作業規範、工作內容細節與附件連結", expanded=expander_expanded):
        if task.get("content_detail") and task["content_detail"].strip():
            st.markdown(task["content_detail"])
        else:
            st.info("暫無詳細 SOP 內容，承辦人可於維護模式補充。")
        
        if task.get("doc_links"):
            st.markdown("---")
            render_doc_links(task["doc_links"])


# ==================== 頂部主導覽標籤列 (支援程式化切換與點選) ====================
tab_names = [
    "🎖️ 專業義消承辦人",
    "🚒 義消業務",
    "🎁 義消福利",
    "💰 補捐助業務",
    "🎯 訓練業務",
    "🌟 其他推動業務",
    "💬 我有話要說"
]

if st.session_state["is_admin"]:
    tab_names.append("⚙️ 科內線上維護 (Excel介面)")

if st.session_state["active_tab"] not in tab_names:
    st.session_state["active_tab"] = tab_names[0]

cur_tab_index = tab_names.index(st.session_state["active_tab"])

selected_tab = st.radio(
    "主頁導覽",
    tab_names,
    index=cur_tab_index,
    horizontal=True,
    label_visibility="collapsed",
    key="top_main_nav"
)
st.session_state["active_tab"] = selected_tab


# ==================== 各分頁內容呈現 ====================

# === 1. 專業義消承辦人 Tab ===
if selected_tab == "🎖️ 專業義消承辦人":
    st.markdown("""
    <div style="background: linear-gradient(to right, #eff6ff, #f8fafc); border: 1px solid #bfdbfe; border-radius: 10px; padding: 1.2rem 1.5rem; margin-bottom: 1.5rem;">
        <h3 style="color: #1e3a8a; margin-top: 0; margin-bottom: 0.4rem;">🎖️ 專業義消承辦人 — 四大實務情境作業導航</h3>
        <p style="color: #475569; font-size: 0.95rem; margin-bottom: 0;">
            專為臺東縣各外勤大隊、分隊義消承辦人量身打造之實務情境導引，依序呈現四大情境說明，點擊下拉選單即可展開完整 SOP 作業指引與系統連結。
        </p>
    </div>
    """, unsafe_allow_html=True)

    all_tasks = db.get_tasks_by_filter()
    all_tasks_dict = {t["title"]: t for t in all_tasks}
    guides = db.get_all_guides()

    for g in guides:
        badge_html = f"<span class='guide-clean-badge'>{g['target_badge']}</span>" if g.get('target_badge') else ""
        icon = g.get('icon') or "📌"

        # 頂部情境說明卡片
        st.markdown(f"""
        <div class="guide-clean-container">
            <div class="guide-clean-header">
                <span style="font-size: 1.5rem; margin-right: 0.6rem;">{icon}</span>
                <span class="guide-clean-title">{g['title']}</span>
                {badge_html}
            </div>
            <div class="guide-desc-box">
                <strong>📌 情境說明</strong>：<br>
                {g['description']}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 關聯業務 SOP 下拉展開選單
        linked_titles = [t.strip() for t in (g.get("linked_task_titles") or "").splitlines() if t.strip()]
        matched_tasks = []
        for l_title in linked_titles:
            matching_task = all_tasks_dict.get(l_title)
            if not matching_task:
                for k, v in all_tasks_dict.items():
                    if l_title in k or k in l_title:
                        matching_task = v
                        break
            if matching_task and matching_task not in matched_tasks:
                matched_tasks.append(matching_task)

        if matched_tasks:
            for mt in matched_tasks:
                with st.expander(f"📋 查看【{mt['title']}】SOP 作業規範與相關系統連結", expanded=False):
                    if mt.get("content_detail") and mt["content_detail"].strip():
                        st.markdown(mt["content_detail"])
                    else:
                        st.info("暫無詳細 SOP 內容。")

                    if mt.get("doc_links") and mt["doc_links"].strip():
                        st.markdown("---")
                        render_doc_links(mt["doc_links"])
        else:
            st.info("暫無關聯之 SOP 資料。")

        st.markdown("<br>", unsafe_allow_html=True)


# === 2. 義消業務 Tab ===
elif selected_tab == "🚒 義消業務":
    st.markdown("### 【🚒 義消業務】")
    st.caption("👤 **科內承辦人**：廖昱翔科員、林威宇小隊長")
    
    tasks_cat = db.get_tasks_by_filter(category="義消業務")
    st.write(f"本分類共有 **{len(tasks_cat)}** 項列管業務：")
    if not tasks_cat:
        st.info("目前【義消業務】無符合條件的項目。")
    else:
        for t in tasks_cat:
            render_task_card(t)


# === 3. 義消福利 Tab ===
elif selected_tab == "🎁 義消福利":
    st.markdown("### 【🎁 義消福利】")
    st.caption("👤 **科內承辦人**：陳怡忻分隊長")
    
    tasks_cat = db.get_tasks_by_filter(category="義消福利")
    st.write(f"本分類共有 **{len(tasks_cat)}** 項列管業務：")
    if not tasks_cat:
        st.info("目前【義消福利】無符合條件的項目。")
    else:
        for t in tasks_cat:
            render_task_card(t)


# === 4. 補捐助業務 Tab ===
elif selected_tab == "💰 補捐助業務":
    st.markdown("### 【💰 補捐助業務】")
    st.caption("👤 **科內承辦人**：廖昱翔科員、林威宇小隊長")
    
    st.markdown("""
    <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 1rem 1.2rem; margin-bottom: 1.2rem;">
        <h4 style="color: #166534; margin-top:0; margin-bottom: 0.5rem;">🎯 義消申請補縣府及各鄉鎮公所補捐助案件管理專區</h4>
        <div style="margin-top: 0.5rem;">
            <span class="pipeline-step step-done">1. 申請表單與系統登錄</span> ➔ 
            <span class="pipeline-step step-done">2. 資格初審與單據查核</span> ➔ 
            <span class="pipeline-step step-active">3. 依計畫執行採購/活動</span> ➔ 
            <span class="pipeline-step step-pending">4. 黏存單據送科核銷</span> ➔ 
            <span class="pipeline-step step-pending">5. 結案撥款</span>
        </div>
        <div style="margin-top: 0.8rem; font-size: 0.88rem; color: #15803d;">
            📌 <strong>申請範例更新提示</strong>：補捐助申請範例將隨時間動態更新，<span style="color:#dc2626;font-weight:700;">更新部分會以顏色做清楚區別</span>，請各分隊務必至系統下載最新版本填報。
        </div>
    </div>
    """, unsafe_allow_html=True)

    tasks_cat = db.get_tasks_by_filter(category="補捐助業務")
    st.write(f"本分類共有 **{len(tasks_cat)}** 項列管業務：")
    if not tasks_cat:
        st.info("目前【補捐助業務】無符合條件的項目。")
    else:
        for t in tasks_cat:
            render_task_card(t)


# === 5. 訓練業務 Tab ===
elif selected_tab == "🎯 訓練業務":
    st.markdown("### 【🎯 訓練業務】")
    st.caption("👤 **科內承辦人**：尤仁宏秘書")
    
    tasks_cat = db.get_tasks_by_filter(category="訓練業務")
    st.write(f"本分類共有 **{len(tasks_cat)}** 項列管業務：")
    if not tasks_cat:
        st.info("目前【訓練業務】無符合條件的項目。")
    else:
        for t in tasks_cat:
            render_task_card(t)


# === 6. 其他推動業務 Tab ===
elif selected_tab == "🌟 其他推動業務":
    st.markdown("### 【🌟 其他推動業務】")
    st.caption("👤 **科內承辦人**：民力訓練科全體同仁")
    
    tasks_cat = db.get_tasks_by_filter(category="其他推動業務")
    if not tasks_cat:
        st.info("ℹ️ 目前「其他推動業務」尚無列管項目。承辦人可開啟「科內維護模式」隨時新增其他專案與業務。")
    else:
        st.write(f"本分類共有 **{len(tasks_cat)}** 項列管業務：")
        for t in tasks_cat:
            render_task_card(t)


# === 7. 我有話要說 Tab ===
elif selected_tab == "💬 我有話要說":
    st.markdown("""
    <div style="background: linear-gradient(to right, #ecfdf5, #f0fdf4); border: 1px solid #a7f3d0; border-radius: 10px; padding: 1.2rem 1.5rem; margin-bottom: 1.5rem;">
        <h3 style="color: #065f46; margin-top: 0; margin-bottom: 0.4rem;">💬 我有話要說 — 臺東縣義消承辦人與分隊同仁雙向回饋專區</h3>
        <p style="color: #047857; font-size: 0.95rem; margin-bottom: 0;">
            開放臺東大隊、關山大隊、成功大隊、大武大隊各分隊義消承辦人及全體同仁提出實務執行問題、法規諮詢、作業建議或系統回饋。民力訓練科將定期彙整、專人查明並公開回覆！
        </p>
    </div>
    """, unsafe_allow_html=True)

    col_fb_form, col_fb_list = st.columns([4, 6])

    # 左側：填寫反映表單
    with col_fb_form:
        st.markdown("#### ✍️ 我要提問 / 反映問題")
        with st.form("add_feedback_form", clear_on_submit=True):
            fb_unit = st.selectbox("所屬單位 / 分隊 *", db.TAITUNG_UNITS)
            fb_submitter = st.text_input("提報人姓名 / 職稱 (選填，可匿名)", placeholder="例：林分隊長、王小隊長、陳隊員...")
            fb_category = st.selectbox("反映業務類別 *", db.FEEDBACK_CATEGORIES)
            fb_contact = st.text_input("聯絡電話 / 公務分機 / 信箱 (選填)", placeholder="方便科內承辦人與您直接聯繫說明")
            fb_content = st.text_area("反映內容 / 問題說明 / 具體建議 *", placeholder="請詳細描述您的問題、遇到的困難或改進建議...", height=160)
            
            fb_submitted = st.form_submit_button("🚀 確認送出意見", type="primary", use_container_width=True)
            if fb_submitted:
                if not fb_unit.strip() or not fb_content.strip():
                    st.error("請務必填寫「所屬單位/分隊」及「反映內容」！")
                else:
                    new_fb_id = db.add_feedback(fb_unit, fb_submitter, fb_category, fb_content, fb_contact)
                    set_flash_message(f"🎉 成功送出意見！留言編號 #{new_fb_id}【{fb_unit}】，民力訓練科將盡速查明查覆。", icon="💌")
                    st.rerun()

    # 右側：問題與民力訓練科回覆列表
    with col_fb_list:
        st.markdown("#### 📢 同仁意見與民力訓練科官方回覆看板")
        
        col_f1, col_f2 = st.columns([1, 1])
        with col_f1:
            fb_filter_cat = st.selectbox("依類別篩選", ["全部類別"] + db.FEEDBACK_CATEGORIES, key="fb_cat_filter")
        with col_f2:
            fb_filter_status = st.selectbox("依處理狀態", ["全部狀態"] + db.FEEDBACK_STATUSES, key="fb_status_filter")

        feedbacks = db.get_all_feedbacks(category_filter=fb_filter_cat, status_filter=fb_filter_status)
        st.caption(f"共計 **{len(feedbacks)}** 則回饋紀錄：")

        if not feedbacks:
            st.info("目前尚無任何回饋紀錄。")
        else:
            status_style_map = {
                "待處理": ("#fef3c7", "#b45309", "🟡 待處理"),
                "處理中": ("#dbeafe", "#1d4ed8", "🔵 處理中"),
                "已回覆": ("#dcfce7", "#15803d", "🟢 已回覆"),
                "列入參考": ("#f1f5f9", "#475569", "⚪ 列入參考")
            }

            for fb in feedbacks:
                bg_c, text_c, status_txt = status_style_map.get(fb["status"], ("#f1f5f9", "#475569", fb["status"]))
                
                st.markdown(f"""
                <div class="feedback-card">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
                        <div>
                            <span style="background:#ede9fe; color:#5b21b6; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.8rem;">{fb['category']}</span>
                            <strong style="margin-left:0.5rem; font-size:1rem; color:#1e293b;">🏢 {fb['unit_name']}</strong>
                            <span style="color:#64748b; font-size:0.85rem; margin-left:0.4rem;">({fb['submitter'] or '熱心同仁'})</span>
                        </div>
                        <div>
                            <span style="background:{bg_c}; color:{text_c}; padding:2px 8px; border-radius:9999px; font-size:0.78rem; font-weight:700;">{status_txt}</span>
                        </div>
                    </div>
                    <div style="font-size:0.95rem; color:#334155; line-height:1.5; margin-bottom:0.4rem;">
                        💬 <strong>反映內容</strong>：{fb['content']}
                    </div>
                    <div style="font-size:0.8rem; color:#94a3b8; text-align:right;">
                        🕒 提報時間：{fb['created_at']}
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if fb["admin_reply"] and fb["admin_reply"].strip():
                    st.markdown(f"""
                    <div class="feedback-reply-box" style="margin-top:-0.6rem; margin-bottom:1.2rem;">
                        <strong>📢 民力訓練科回覆 ({fb['replied_at'] or ''})：</strong><br>
                        {fb['admin_reply']}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div style="font-size:0.85rem; color:#94a3b8; margin-top:-0.4rem; margin-bottom:1.2rem; padding-left:0.5rem;">
                        ⏳ <em>民力訓練科正查明處理中，請稍候回覆...</em>
                    </div>
                    """, unsafe_allow_html=True)


# === 8. 科內維護模式 Tab (若已登入) ===
elif selected_tab == "⚙️ 科內線上維護 (Excel介面)":
    st.markdown("### ⚙️ 科內承辦人線上快速維護介面")
    st.info("💡 承辦人可直接在此處編輯各業務內容（自動連動首頁導航）、線上修改「專業義消承辦人」四大情境說明，或管理/回覆/刪除「我有話要說」同仁留言。所有儲存操作均具備明確完成提示。")

    subtab1, subtab2, subtab3, subtab4, subtab5, subtab6 = st.tabs([
        "📋 Excel 式線上即時編輯",
        "🎖️ 專業義消承辦人 - 導引維護",
        "💬 我有話要說 - 線上回覆與留言管理",
        "➕ 新增業務項目",
        "✏️ 單筆詳細維護 / 刪除",
        "💾 資料庫備份、還原與重設"
    ])

    # 子分頁 1: st.data_editor 批次編輯
    with subtab1:
        st.markdown("#### 📋 批次表格編輯器 (`st.data_editor`)")
        st.caption("可雙擊任一儲存格修改文字、承辦人、狀態或最新異動重點，修改完成後請點擊下方「💾 儲存所有表格修改」按鈕寫入資料庫。（※ 於此修改的業務內容會自動同步連動首頁「專業義消承辦人」中的對應 SOP 與連結！）")
        
        df_current = db.get_all_tasks_df()
        
        column_config = {
            "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "category": st.column_config.SelectboxColumn("業務分類", options=db.CATEGORIES, required=True, width="medium"),
            "subcategory": st.column_config.TextColumn("子項目", width="medium"),
            "title": st.column_config.TextColumn("業務項目名稱", required=True, width="large"),
            "owner": st.column_config.TextColumn("科內承辦人", width="medium"),
            "status": st.column_config.SelectboxColumn("執行狀態", options=db.STATUSES, required=True, width="medium"),
            "update_highlight": st.column_config.TextColumn("★ 最新異動重點 (紅字高亮)", width="large", help="輸入即在前台頂部醒目標示"),
            "content_detail": st.column_config.TextColumn("詳細 SOP (Markdown)", width="large"),
            "doc_links": st.column_config.TextColumn("表單 / 雲端連結", width="medium"),
            "last_updated": st.column_config.TextColumn("最後更新時間", disabled=True, width="medium")
        }
        
        edited_df = st.data_editor(
            df_current,
            column_config=column_config,
            use_container_width=True,
            num_rows="fixed",
            key="main_data_editor",
            height=450
        )

        col_btn1, col_btn2 = st.columns([2, 8])
        with col_btn1:
            if st.button("💾 儲存所有表格修改", type="primary", use_container_width=True):
                updated_cnt = db.batch_update_tasks_from_df(edited_df)
                set_flash_message(f"🎉 成功儲存！已同步寫入 {updated_cnt} 筆變更資料至 SQLite 資料庫，前台看板與各分頁已即時更新。", icon="💾")
                st.rerun()

    # 子分頁 2: 專業義消承辦人情境導引維護
    with subtab2:
        st.markdown("#### 🎖️ 「專業義消承辦人」四大情境說明與關聯業務維護")
        st.caption("您可以在此自由修改第一大項各情境的標題、圖示、情境說明文字，以及要附加顯示哪幾項業務的 SOP！")
        
        guides_list = db.get_all_guides()
        all_task_titles = [t["title"] for t in db.get_all_tasks_df().to_dict("records")]
        
        g_options = {f"情境 {g['scenario_num']}：{g['title']}": g['id'] for g in guides_list}
        sel_g_label = st.selectbox("請選擇要編輯的情境導航", list(g_options.keys()))
        sel_g_id = g_options[sel_g_label]
        cur_g = next(g for g in guides_list if g["id"] == sel_g_id)

        with st.form(f"edit_guide_form_{sel_g_id}"):
            col_g1, col_g2, col_g3 = st.columns([1, 4, 3])
            with col_g1:
                edit_g_icon = st.text_input("圖示 (Emoji)", value=cur_g["icon"] or "📌", key=f"g_icon_{sel_g_id}")
            with col_g2:
                edit_g_title = st.text_input("情境大標題 *", value=cur_g["title"] or "", key=f"g_title_{sel_g_id}")
            with col_g3:
                edit_g_badge = st.text_input("右上標籤文字", value=cur_g["target_badge"] or "", key=f"g_badge_{sel_g_id}")

            edit_g_desc = st.text_area("情境說明文字 (支援 Markdown)", value=cur_g["description"] or "", height=120, key=f"g_desc_{sel_g_id}")
            
            st.markdown("**🔗 關聯業務 SOP 設定 (在前台此情境下直接展示其 SOP 與系統連結)：**")
            default_linked = [t.strip() for t in (cur_g["linked_task_titles"] or "").splitlines() if t.strip()]
            valid_defaults = [t for t in default_linked if t in all_task_titles]
            
            selected_tasks = st.multiselect(
                "選擇要在此情境下展示 SOP 的業務項目",
                options=all_task_titles,
                default=valid_defaults,
                help="可複選多個業務，前台第一大項會直接呈現所選業務的最新 SOP 作業指引與連結按鈕。",
                key=f"g_tasks_{sel_g_id}"
            )

            submit_guide = st.form_submit_button("💾 儲存此情境導引設定", type="primary", use_container_width=True)
            if submit_guide:
                db.update_guide(
                    sel_g_id,
                    edit_g_icon,
                    edit_g_title,
                    edit_g_badge,
                    edit_g_desc,
                    "\n".join(selected_tasks)
                )
                set_flash_message(f"🎉 成功儲存！已更新情境【{edit_g_title}】，首頁「專業義消承辦人」已同步更新完成。", icon="🎖️")
                st.rerun()

    # 子分頁 3: 回覆我有話要說留言 & 留言管理
    with subtab3:
        st.markdown("#### 💬 我有話要說 — 同仁留言官方回覆與留言管理")
        all_fbs = db.get_all_feedbacks()
        
        col_top_l, col_top_r = st.columns([7, 3])
        with col_top_r:
            with st.expander("🧹 清空所有留言 (含示範留言)"):
                st.warning("⚠️ 此操作將永久刪除全部留言紀錄且無法復原。")
                confirm_clear = st.checkbox("確認清空所有留言", key="confirm_clear_all_fbs")
                if st.button("🚨 立即清空全部留言", type="secondary", disabled=not confirm_clear, use_container_width=True):
                    db.clear_all_feedbacks()
                    set_flash_message("✅ 已清空所有留言紀錄！資料庫已還原至乾淨狀態。", icon="🧹")
                    st.rerun()

        if not all_fbs:
            st.info("目前資料庫中尚無任何同仁回饋留言。")
        else:
            fb_options = {f"ID #{fb['id']} - [{fb['category']}] {fb['unit_name']} ({fb['submitter']}) - {fb['status']}": fb['id'] for fb in all_fbs}
            sel_fb_label = st.selectbox("請選擇要回覆或刪除的留言", list(fb_options.keys()))
            sel_fb_id = fb_options[sel_fb_label]
            cur_fb = next(f for f in all_fbs if f["id"] == sel_fb_id)

            st.markdown(f"""
            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:1rem; margin-bottom:1rem;">
                <strong>留言編號</strong>：ID #{cur_fb['id']}<br>
                <strong>提報單位</strong>：{cur_fb['unit_name']} ({cur_fb['submitter']})<br>
                <strong>業務類別</strong>：{cur_fb['category']}<br>
                <strong>聯絡方式</strong>：{cur_fb['contact_info'] or '無'}<br>
                <strong>反映時間</strong>：{cur_fb['created_at']}<br>
                <div style="margin-top:0.5rem; color:#1e293b;">
                    <strong>💬 反映內容</strong>：{cur_fb['content']}
                </div>
            </div>
            """, unsafe_allow_html=True)

            with st.form(f"reply_fb_form_{sel_fb_id}"):
                curr_status_idx = db.FEEDBACK_STATUSES.index(cur_fb["status"]) if cur_fb["status"] in db.FEEDBACK_STATUSES else 0
                reply_status = st.selectbox("處理狀態", db.FEEDBACK_STATUSES, index=curr_status_idx, key=f"fb_status_{sel_fb_id}")
                reply_content = st.text_area("民力訓練科官方回覆內容 (將公開於看板供同仁查閱)", value=cur_fb["admin_reply"] or "", height=140, key=f"fb_reply_{sel_fb_id}")
                
                rep_btn = st.form_submit_button("📢 發布 / 更新官方回覆", type="primary", use_container_width=True)

                if rep_btn:
                    db.reply_feedback(sel_fb_id, reply_status, reply_content)
                    set_flash_message(f"🎉 成功發布回覆！已更新留言 ID #{sel_fb_id}【{cur_fb['unit_name']}】為「{reply_status}」，前台看板已即時公開。", icon="📢")
                    st.rerun()

            # 單筆刪除區塊
            st.markdown("<br>", unsafe_allow_html=True)
            col_d1, col_d2 = st.columns([7, 3])
            with col_d2:
                if st.button(f"🗑️ 永久刪除此筆留言 (ID #{sel_fb_id})", type="secondary", use_container_width=True):
                    db.delete_feedback(sel_fb_id)
                    set_flash_message(f"✅ 已永久刪除留言 ID #{sel_fb_id}【{cur_fb['unit_name']}】！", icon="🗑️")
                    st.rerun()

    # 子分頁 4: 新增業務項目
    with subtab4:
        st.markdown("#### ➕ 新增業務項目表單")
        with st.form("add_task_form", clear_on_submit=True):
            col_a, col_b, col_c = st.columns([2, 2, 2])
            with col_a:
                new_category = st.selectbox("業務分類 *", db.CATEGORIES)
            with col_b:
                new_subcategory = st.text_input("子項目 (例：專長資料庫、保險互助、業務評核)")
            with col_c:
                new_owner = st.text_input("科內承辦人 (例：廖昱翔科員、林威宇小隊長、陳怡忻分隊長、尤仁宏秘書)")

            col_d, col_e = st.columns([4, 2])
            with col_d:
                new_title = st.text_input("業務項目名稱 *", placeholder="例如：115年度義消新式防護裝備規格審議")
            with col_e:
                new_status = st.selectbox("執行狀態 *", db.STATUSES, index=0)

            new_highlight = st.text_area(
                "★ 最新異動 / 宣導重點 (若無可留空)",
                placeholder="例如：⚠️ 115年度申請期限延長至 9 月 30 日止，各分隊請加強宣導。",
                help="此欄位若有內容，前台將以紅字高亮與醒目橫幅提示。"
            )

            new_content = st.text_area(
                "詳細工作內容、作業規範與 SOP 說明 (支援 Markdown 排版)",
                placeholder="### 作業流程\n1. 第一步...\n2. 第二步...\n\n#### 注意事項\n* 注意要點...",
                height=200
            )

            new_doc_links = st.text_area(
                "相關表單、公文法規或雲端硬碟連結 (每行一筆)",
                placeholder="申請表單下載: https://reurl.cc/...\n法規作業規定: https://law.nfa.gov.tw/...",
                height=90
            )

            submitted = st.form_submit_button("🚀 確認新增並儲存至資料庫", type="primary")
            if submitted:
                if not new_title.strip():
                    st.error("請輸入「業務項目名稱」！")
                else:
                    new_id = db.add_task(
                        new_category,
                        new_subcategory.strip(),
                        new_title.strip(),
                        new_owner.strip(),
                        new_status,
                        new_highlight.strip(),
                        new_content.strip(),
                        new_doc_links.strip()
                    )
                    set_flash_message(f"🎉 成功新增業務項目！編號：ID #{new_id}【{new_title}】已寫入資料庫並於前台發布。", icon="🎉")
                    st.rerun()

    # 子分頁 5: 單筆詳細編輯與刪除
    with subtab5:
        st.markdown("#### ✏️ 單筆業務詳細編輯與刪除")
        st.caption("您可以先透過「業務分類篩選」快速縮小清單範圍，再選取特定項目進行詳細內容或 SOP 修改。切換項目時下方欄位將即時自動同步載入最新內容！")
        
        df_edit = db.get_all_tasks_df()
        if df_edit.empty:
            st.info("目前資料庫中無任何資料。")
        else:
            col_sel_cat, col_sel_item = st.columns([3, 7])
            with col_sel_cat:
                filter_cat = st.selectbox(
                    "1. 先選業務分類篩選",
                    ["全部分類"] + db.CATEGORIES,
                    key="subtab5_cat_filter"
                )
            
            df_filtered_edit = df_edit if filter_cat == "全部分類" else df_edit[df_edit["category"] == filter_cat]
            
            if df_filtered_edit.empty:
                st.warning(f"目前分類「{filter_cat}」無任何業務項目。")
            else:
                with col_sel_item:
                    task_options = {f"ID #{row['id']} - [{row['category']}] {row['title']} ({row['owner'] or '未指派'})": row['id'] for _, row in df_filtered_edit.iterrows()}
                    selected_label = st.selectbox("2. 選擇要編輯的具體業務項目 *", list(task_options.keys()), key=f"subtab5_task_picker_{filter_cat}")
                    selected_id = task_options[selected_label]
                
                current_item = df_edit[df_edit["id"] == selected_id].iloc[0]

                st.markdown(f"""
                <div style="background:#eff6ff; border:1px solid #bfdbfe; border-left:4px solid #2563eb; border-radius:6px; padding:0.6rem 1rem; margin:0.8rem 0 1rem 0; font-size:0.92rem; color:#1e40af;">
                    📝 正在編輯：<strong>ID #{selected_id}【{current_item['title']}】</strong> &nbsp;|&nbsp; 
                    分類：<strong>{current_item['category']}</strong> &nbsp;|&nbsp; 
                    承辦人：<strong>{current_item['owner'] or '未指派'}</strong>
                </div>
                """, unsafe_allow_html=True)

                with st.form(f"edit_single_form_{selected_id}"):
                    col_e1, col_e2, col_e3 = st.columns([2, 2, 2])
                    with col_e1:
                        cat_idx = db.CATEGORIES.index(current_item["category"]) if current_item["category"] in db.CATEGORIES else 0
                        edit_category = st.selectbox("業務分類 *", db.CATEGORIES, index=cat_idx, key=f"edit_cat_{selected_id}")
                    with col_e2:
                        edit_subcategory = st.text_input("子項目", value=current_item["subcategory"] or "", key=f"edit_subcat_{selected_id}")
                    with col_e3:
                        edit_owner = st.text_input("承辦人", value=current_item["owner"] or "", key=f"edit_owner_{selected_id}")

                    col_e4, col_e5 = st.columns([4, 2])
                    with col_e4:
                        edit_title = st.text_input("業務項目名稱 *", value=current_item["title"] or "", key=f"edit_title_{selected_id}")
                    with col_e5:
                        status_idx = db.STATUSES.index(current_item["status"]) if current_item["status"] in db.STATUSES else 0
                        edit_status = st.selectbox("執行狀態 *", db.STATUSES, index=status_idx, key=f"edit_status_{selected_id}")

                    edit_highlight = st.text_area(
                        "★ 最新異動 / 宣導重點 (紅字醒目提示，若無可留空)",
                        value=current_item["update_highlight"] or "",
                        height=80,
                        key=f"edit_high_{selected_id}"
                    )
                    edit_content = st.text_area(
                        "詳細工作內容 / SOP 作業指引 (支援 Markdown 排版)",
                        value=current_item["content_detail"] or "",
                        height=250,
                        key=f"edit_content_{selected_id}"
                    )
                    edit_doc_links = st.text_area(
                        "相關表單與雲端連結 (每行一筆)",
                        value=current_item["doc_links"] or "",
                        height=100,
                        key=f"edit_links_{selected_id}"
                    )

                    save_btn = st.form_submit_button("💾 儲存此項目更新", type="primary", use_container_width=True)

                    if save_btn:
                        db.update_single_task(
                            selected_id,
                            edit_category,
                            edit_subcategory.strip(),
                            edit_title.strip(),
                            edit_owner.strip(),
                            edit_status,
                            edit_highlight.strip(),
                            edit_content.strip(),
                            edit_doc_links.strip()
                        )
                        set_flash_message(f"🎉 成功儲存！已更新 ID #{selected_id}【{edit_title}】最新內容，各分頁與首頁導航已即時同步更新。", icon="💾")
                        st.rerun()

                with st.expander(f"🗑️ 危險區域：刪除此業務項目 (ID #{selected_id})"):
                    confirm_del = st.checkbox(f"我確認要永久刪除 ID #{selected_id}【{current_item['title']}】", key=f"del_chk_{selected_id}")
                    if st.button("❌ 確認永久刪除", type="secondary", disabled=not confirm_del, key=f"del_btn_{selected_id}"):
                        db.delete_task(selected_id)
                        set_flash_message(f"✅ 已永久刪除 ID #{selected_id}【{current_item['title']}】！", msg_type="warning", icon="🗑️")
                        st.rerun()

    # 子分頁 6: 資料庫完整匯出、Google 試算表雲端連動與還原
    with subtab6:
        st.markdown("#### 💾 資料庫完整匯出、Google 試算表連動與備份還原")
        st.info("💡 **資料永續與多人協作方案**：您可以隨時將全系統所有資料表打包匯出，或直接綁定 **Google 試算表 (Google Sheets)**，科內承辦人只需在 Google 試算表填寫更新，看板點擊按鈕即可 1 秒同步！")

        # 區塊 1: Google 試算表 (Google Sheets) 雲端連動
        st.markdown("##### 🌐 1. 綁定 Google 試算表 (Google Sheets) 即時雲端連動")
        saved_gsheet_url, last_sync_time = db.get_gsheet_sync_info()
        
        with st.form("gsheet_sync_form"):
            st.caption("請將科內 Google 試算表的共用權限設為「**知道連結的使用者均可檢視**」，並將試算表網址貼在下方：")
            input_gsheet_url = st.text_input(
                "Google 試算表網址 (Google Sheets URL)",
                value=saved_gsheet_url,
                placeholder="例如：https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
            )
            col_gs1, col_gs2 = st.columns([1, 1])
            with col_gs1:
                btn_sync_now = st.form_submit_button("🔄 立即從 Google 試算表同步業務資料", type="primary", use_container_width=True)
            with col_gs2:
                st.caption(f"🕒 前次雲端同步時間：**{last_sync_time}**")

            if btn_sync_now:
                if not input_gsheet_url.strip():
                    st.error("請輸入 Google 試算表網址！")
                else:
                    success, s_count, s_msg = db.sync_tasks_from_google_sheet(input_gsheet_url)
                    if success:
                        set_flash_message(f"🎉 成功同步！已從 Google 試算表匯入 {s_count} 筆最新業務資料，看板已即時更新。", icon="🌐")
                        st.rerun()
                    else:
                        st.error(f"❌ {s_msg}")

        st.markdown("---")

        # 區塊 2: 全系統多資料表完整匯出
        st.markdown("##### 📦 2. 全系統完整資料匯出與打包備份")
        st.caption("此處提供「全系統完整整合資料包 (JSON)」以及個別資料表的完整 CSV 匯出（包含業務主表、承辦人導航情境表、我有話要說同仁留言表全部欄位）。")
        
        col_exp1, col_exp2, col_exp3, col_exp4 = st.columns(4)
        
        # 全系統 JSON 打包 (含所有資料表全部內容)
        full_sys_data = db.get_full_system_data()
        json_full_str = json.dumps(full_sys_data, ensure_ascii=False, indent=2).encode("utf-8")
        with col_exp1:
            st.download_button(
                label="📦 下載【全系統完整備份包】(JSON)",
                data=json_full_str,
                file_name=f"ttfd_minli_FULL_SYSTEM_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True,
                help="包含業務主表、4大情境導引設定、同仁留言與回覆全部資料"
            )

        # 業務主表 CSV
        all_tasks_df_exp = db.get_all_tasks_df()
        csv_tasks_bytes = all_tasks_df_exp.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        with col_exp2:
            st.download_button(
                label="📋 下載【業務清單主表】(CSV)",
                data=csv_tasks_bytes,
                file_name=f"ttfd_tasks_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        # 專業義消承辦人情境導引 CSV
        guides_df_exp = pd.DataFrame(db.get_all_guides())
        csv_guides_bytes = guides_df_exp.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        with col_exp3:
            st.download_button(
                label="🎖️ 下載【情境導引設定】(CSV)",
                data=csv_guides_bytes,
                file_name=f"ttfd_guides_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        # 我有話要說留言清單 CSV
        fbs_df_exp = pd.DataFrame(db.get_all_feedbacks())
        csv_fbs_bytes = fbs_df_exp.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        with col_exp4:
            st.download_button(
                label="💬 下載【我有話要說留言】(CSV)",
                data=csv_fbs_bytes,
                file_name=f"ttfd_feedbacks_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        st.markdown("---")

        # 區塊 3: 上傳 CSV 還原與初始重設
        st.markdown("##### 📤 3. 上傳 CSV 備份檔案進行還原 / 重設")
        col_res1, col_res2 = st.columns([1, 1])
        with col_res1:
            uploaded_csv = st.file_uploader("選取先前的業務主表 CSV 備份檔上傳還原", type=["csv"], key="csv_restore_uploader_v2")
            if uploaded_csv is not None:
                try:
                    import_df = pd.read_csv(uploaded_csv)
                    st.success(f"讀取成功！檔案內包含 {len(import_df)} 筆業務資料。")
                    if st.button("🚀 確認匯入並覆蓋還原資料庫", type="primary", use_container_width=True):
                        restored_cnt = db.import_tasks_from_df(import_df, replace_all=True)
                        set_flash_message(f"🎉 成功還原！已從備份檔匯入 {restored_cnt} 筆業務資料至資料庫。", icon="📤")
                        st.rerun()
                except Exception as e:
                    st.error(f"檔案解析失敗：{e}")

        with col_res2:
            st.warning("⚠️ **重設為官方標準清單**：將會清除目前所有修改並重新載入官方預設清單。")
            confirm_reseed = st.checkbox("確認要重設為初始官方標準業務清單", key="chk_reseed_final")
            if st.button("🔄 重新初始化資料庫", disabled=not confirm_reseed, type="secondary", use_container_width=True):
                db.init_db(force_reseed=True)
                set_flash_message("🎉 資料庫已成功重設為臺東縣消防局官方標準業務清單與預設資料！", icon="🔄")
                st.rerun()
