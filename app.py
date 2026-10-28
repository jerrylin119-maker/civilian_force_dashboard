import json
# -*- coding: utf-8 -*-


import html
import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta, timezone
import importlib
import database as db
import case_pages
import case_registry
import subsidy_content as sc

# Streamlit Cloud 重新部署後只會重跑 app.py，已經載入記憶體的 database 模組可能還是舊版
# （缺少新函式，會造成 AttributeError）。偵測到缺函式時強制重新載入，不必手動 Reboot app。
if not hasattr(sc, "PACKS"):
    sc = importlib.reload(sc)
    if hasattr(db, "_sc"):
        db._sc = sc
if not all(hasattr(db, _n) for _n in ("ensure_compliance_data_initialized", "get_subsidy_banner", "steps_from_editor_records", "ensure_content_packs")):
    db = importlib.reload(db)

# 與上面同一個原因：重新部署後 sys.modules 裡的 plan_generator 可能還是舊版，
# normalize_items 沒有 subsidy 參數，計畫書產生器一載入就 TypeError。
_PLAN_GENERATOR_REVISION = 9


def load_plan_generator():
    """載入 plan_generator；若記憶體中是舊版就從磁碟重載。"""
    import inspect
    import plan_generator as pg
    import subsidy_check as chk

    finding_fields = getattr(chk.Finding, "__dataclass_fields__", {})
    if "suggestion" not in finding_fields or "where" not in finding_fields:
        chk = importlib.reload(chk)
        pg = importlib.reload(pg)

    def _is_current(mod):
        fn = getattr(mod, "normalize_items", None)
        try:
            params = tuple(inspect.signature(fn).parameters) if fn is not None else ()
        except (TypeError, ValueError):
            params = ()
        return (
            getattr(mod, "MODULE_REVISION", 0) == _PLAN_GENERATOR_REVISION
            and "subsidy" in params
            and hasattr(mod, "format_compliance_item")
            and hasattr(mod, "ALL_CLEAR_MESSAGE")
            and hasattr(mod, "case_list")
        )

    if not _is_current(pg):
        pg = importlib.reload(pg)
    return pg


load_plan_generator()

# 頁面配置
# 補捐助專區（?view=subsidy）使用自己的分頁標題與圖示，這樣在瀏覽器歷史、書籤、分頁列
# 才分得出和主網站（業務知識動態看板）是不同的網頁。
_IS_SUBSIDY_VIEW = st.query_params.get("view", "") == "subsidy"
st.set_page_config(
    page_title=("民力運用及訓練科 — 補捐助專區" if _IS_SUBSIDY_VIEW
                else "臺東縣消防局民力運用及訓練科 — 業務知識動態看板"),
    page_icon="💰" if _IS_SUBSIDY_VIEW else "🚒",
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

def get_top_latest_highlights_safe(limit=3):
    """安全取得最新更新且具異動重點的前 N 項業務公告 (毫秒時間排序)"""
    try:
        if hasattr(db, "get_top_latest_highlights"):
            return db.get_top_latest_highlights(limit)
    except Exception:
        pass
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, category, subcategory, title, owner, status, update_highlight, last_updated FROM TaskDatabase WHERE update_highlight IS NOT NULL AND TRIM(update_highlight) != ''")
        rows = cursor.fetchall()
        conn.close()
        tasks = [dict(r) for r in rows]
        def p_dt(d):
            try:
                return pd.to_datetime(str(d).replace("/", "-").strip())
            except Exception:
                return datetime.min
        return sorted(tasks, key=lambda t: (p_dt(t.get("last_updated")), t.get("id", 0)), reverse=True)[:limit]
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

def get_valid_admin_passwords():
    """取得科內維護模式的合法密碼集合。

    優先讀取 Streamlit Secrets（App → Settings → Secrets 設定 admin_password = "..."），
    如尚未設定則回退為舊版預設密碼，避免尚未設定 Secrets 的環境（如本機開發）直接無法登入。
    正式環境請務必盡快設定 admin_password，換掉這裡的預設弱密碼。
    """
    try:
        configured = st.secrets.get("admin_password")
    except Exception:
        configured = None
    if configured:
        return {str(configured).strip()}
    return {"119", "admin119", "minli119"}


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
    .step-plain { background: #eff6ff; color: #1e40af; border-color: #bfdbfe; }
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

    /* 專業 Markdown / HTML 表格樣式 */
    table {
        width: 100% !important;
        border-collapse: collapse !important;
        margin: 1rem 0 !important;
        font-size: 0.92rem !important;
        border-radius: 8px !important;
        overflow: hidden !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04) !important;
    }
    th {
        background: #1e3a8a !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        text-align: left !important;
        padding: 10px 14px !important;
        border: 1px solid #1e3a8a !important;
    }
    td {
        padding: 9px 14px !important;
        border: 1px solid #e2e8f0 !important;
        color: #334155 !important;
    }
    tr:nth-child(even) {
        background-color: #f8fafc !important;
    }
    tr:hover {
        background-color: #eff6ff !important;
    }
</style>
""", unsafe_allow_html=True)

# ========== 啟動時自動從 GitHub 備份還原（若 DB 是空的）==========
if "auto_restore_checked" not in st.session_state:
    st.session_state["auto_restore_checked"] = True
    try:
        restored, restore_msg = db.auto_restore_on_startup()
        if restored:
            st.session_state["_startup_restored"] = True
    except Exception:
        pass

# ========== 「申請注意要點」「錯誤樣態案例」兩個頁面的資料初始化（每個 session 只檢查一次）==========
if "compliance_data_checked" not in st.session_state:
    st.session_state["compliance_data_checked"] = True
    try:
        db.ensure_compliance_data_initialized()
        db.ensure_content_packs()
    except Exception:
        import traceback
        traceback.print_exc()

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




def is_numbered_or_heading_line(line):
    """判斷該行是否為公文/作業條列項目 (編號項目絕不轉為表格)"""
    s = line.strip()
    if not s:
        return False
    # 中文大寫數字編號 (一、, 二、, 十、等)
    if re.match(r'^[一二三四五六七八九十百]+[、.．]', s):
        return True
    # 括弧編號 ((一), (二), (1), (2), （一）, （二）等)
    if re.match(r'^[\(（][一二三四五六七八九十0-9a-zA-Z]+[\)）]', s):
        return True
    # 阿拉伯數字編號 (1., 2., 10., 1、, 2、等)
    if re.match(r'^\d+[.、．]', s):
        return True
    # 英文字母編號 (A., B., a., b. 等)
    if re.match(r'^[A-Za-z][.、．]', s):
        return True
    # 條列符號 (*, -, •, ▪, ► 等)
    if re.match(r'^[•\*\-\–—▪▫►▶]\s*', s):
        return True
    # 公文標準段落標題 (主旨：, 說明：, 依據：, 辦法：, 備註：, 注意事項：, 辦理地點：, 比賽項目：等)
    if re.match(r'^(主旨|說明|依據|辦法|備註|注意事項|比賽項目|辦理地點|辦理時間|集訓規劃|賽事獎金)[：:\s]', s):
        return True
    return False

def clean_numbered_line(line):
    """將 Word 條列編號後的定位字元 (Tab) 轉為一般空格，保持乾淨排版"""
    s = line.strip()
    s = re.sub(r'^([一二三四五六七八九十百]+[、.．])\t+', r'\1 ', s)
    s = re.sub(r'^([\(（][一二三四五六七八九十0-9a-zA-Z]+[\)）])\t+', r'\1 ', s)
    s = re.sub(r'^(\d+[.、．])\t+', r'\1 ', s)
    s = re.sub(r'^([A-Za-z][.、．])\t+', r'\1 ', s)
    s = s.replace('\t', '  ')
    return s

def format_sop_content_smart(text):
    """智慧解析並排版 SOP 內容 (自動保護公文條列編號，僅將真實表格轉為專業樣式)"""
    if not text or not text.strip():
        return ""
    
    lines = text.splitlines()
    new_lines = []
    tsv_buffer = []
    
    def flush_tsv(buffer):
        if not buffer:
            return []
        # 僅當連續 2 行以上且每行欄位數 >= 2 時才視為真正表格
        if len(buffer) >= 2 and all(len(r) >= 2 for r in buffer):
            max_cols = max(len(row) for row in buffer)
            padded_rows = [row + [""] * (max_cols - len(row)) for row in buffer]
            header = "| " + " | ".join(padded_rows[0]) + " |"
            sep = "| " + " | ".join([":---"] * max_cols) + " |"
            table_md = [header, sep]
            for row in padded_rows[1:]:
                table_md.append("| " + " | ".join(row) + " |")
            return table_md
        else:
            return [" ".join(row) for row in buffer]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if tsv_buffer:
                new_lines.extend(flush_tsv(tsv_buffer))
                tsv_buffer = []
            new_lines.append("")
            continue
            
        # 若本行已有 Markdown 表格格式 (| 欄1 | 欄2 |)，直接保留
        if stripped.startswith("|") and stripped.endswith("|"):
            if tsv_buffer:
                new_lines.extend(flush_tsv(tsv_buffer))
                tsv_buffer = []
            new_lines.append(line)
            continue
            
        # 若為公文條列項目或編號 (例如 (一), (二), 1., 2., 主旨:, 說明:)，絕對不進表格
        if is_numbered_or_heading_line(stripped):
            if tsv_buffer:
                new_lines.extend(flush_tsv(tsv_buffer))
                tsv_buffer = []
            new_lines.append(clean_numbered_line(line))
            continue
            
        # 判斷是否為真實表格資料列 (由 Tab 分隔多欄)
        if "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
            if len(parts) >= 2:
                tsv_buffer.append(parts)
                continue
                
        if tsv_buffer:
            new_lines.extend(flush_tsv(tsv_buffer))
            tsv_buffer = []
            
        new_lines.append(line)
        
    if tsv_buffer:
        new_lines.extend(flush_tsv(tsv_buffer))

    # Markdown 規則是「單一換行不會換行、要連續兩個換行才會分段」，
    # 但貼上的公文/SOP 內容通常每一行（例如 一、二、三、...）都是各自獨立的一行，
    # 只用單一 \n 組合的話，在 st.markdown 渲染時會被擠成同一段、變成使用者看到的「全部黏在一起」。
    # 因此除了真正的空白行（維持真正的分段效果）之外，每一行結尾補上 Markdown 的「強制換行」
    # 語法（兩個半形空白 + 換行），讓每一行都能各自換行顯示，同時不會因為分段而產生過大的段落間距。
    processed_lines = [
        ln if (ln == "" or ln.endswith("  ")) else f"{ln}  "
        for ln in new_lines
    ]
    return "\n".join(processed_lines)


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


# 輔助函式：渲染單張業務卡片 (支援維護模式直接在卡片上編輯、點擊直達聚焦展開)
def render_task_card(task):
    is_targeted = bool(st.session_state.get("target_task_title") == task["title"])
    has_highlight = bool(task.get("update_highlight") and str(task["update_highlight"]).strip())
    is_admin_mode = bool(st.session_state.get("is_admin"))
    
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

    # 檢視狀態：查看完整 SOP 作業規範與附件
    expander_expanded = is_targeted
    with st.expander("📖 查看完整 SOP 作業規範、工作內容細節與附件連結", expanded=expander_expanded):
        if task.get("content_detail") and task["content_detail"].strip():
            st.markdown(format_sop_content_smart(task["content_detail"]))
        else:
            st.info("暫無詳細 SOP 內容，承辦人可於維護模式補充。")
        
        if task.get("doc_links"):
            st.markdown("---")
            render_doc_links(task["doc_links"])

    # ★ 維護模式專屬：直接在該業務卡片下方出現【✏️ 快速編輯此業務】
    if is_admin_mode:
        with st.expander(f"✏️ 【維護模式】直接修改此業務（ID #{task['id']} — {task['title']}）", expanded=False):
            with st.form(f"inline_edit_task_form_{task['id']}"):
                col_in1, col_in2, col_in3 = st.columns([2, 2, 2])
                with col_in1:
                    c_idx = db.CATEGORIES.index(task["category"]) if task["category"] in db.CATEGORIES else 0
                    in_cat = st.selectbox("業務分類 *", db.CATEGORIES, index=c_idx, key=f"in_cat_{task['id']}")
                with col_in2:
                    in_subcat = st.text_input("子項目", value=task["subcategory"] or "", key=f"in_subcat_{task['id']}")
                with col_in3:
                    cur_o = task["owner"] or ""
                    d_officers = getattr(db, "DEFAULT_OFFICERS", ["廖昱翔科員、林威宇小隊長", "廖昱翔科員", "林威宇小隊長", "陳怡忻分隊長", "尤仁宏秘書", "民力訓練科全體同仁"])
                    all_o_opts = list(dict.fromkeys(d_officers + ([cur_o] if cur_o else []) + ["➕ 自訂其他承辦人..."]))
                    o_idx = all_o_opts.index(cur_o) if cur_o in all_o_opts else 0
                    in_owner_sel = st.selectbox("承辦人 (下拉選單) *", all_o_opts, index=o_idx, key=f"in_own_sel_{task['id']}")

                in_custom_owner = ""
                if in_owner_sel == "➕ 自訂其他承辦人...":
                    in_custom_owner = st.text_input("請輸入自訂承辦人", value=cur_o, key=f"in_own_cust_{task['id']}")

                col_in4, col_in5 = st.columns([4, 2])
                with col_in4:
                    in_title = st.text_input("業務項目名稱 *", value=task["title"] or "", key=f"in_title_{task['id']}")
                with col_in5:
                    s_idx = db.STATUSES.index(task["status"]) if task["status"] in db.STATUSES else 0
                    in_status = st.selectbox("執行狀態 *", db.STATUSES, index=s_idx, key=f"in_status_{task['id']}")

                in_highlight = st.text_area(
                    "★ 最新異動 / 宣導重點 (紅字醒目提示，若無可留空)",
                    value=task["update_highlight"] or "",
                    height=70,
                    key=f"in_high_{task['id']}"
                )

                in_content = st.text_area(
                    "詳細工作內容 / SOP 作業指引 (支援直接貼上 Excel 表格與 Markdown 排版)",
                    value=task["content_detail"] or "",
                    height=220,
                    key=f"in_content_{task['id']}"
                )

                in_doc_links = st.text_area(
                    "相關表單、公文法規或雲端硬碟連結 (每行一筆)",
                    value=task["doc_links"] or "",
                    height=90,
                    key=f"in_links_{task['id']}"
                )

                btn_in_save = st.form_submit_button("💾 立即儲存此業務修改", type="primary", use_container_width=True)
                if btn_in_save:
                    final_in_owner = in_custom_owner.strip() if in_owner_sel == "➕ 自訂其他承辦人..." else in_owner_sel
                    db.update_single_task(
                        task['id'],
                        in_cat,
                        in_subcat.strip(),
                        in_title.strip(),
                        final_in_owner,
                        in_status,
                        in_highlight.strip(),
                        in_content.strip(),
                        in_doc_links.strip()
                    )
                    set_flash_message(f"🎉 成功更新！ID #{task['id']}【{in_title}】已完成儲存並同步至前台。", icon="💾")
                    st.rerun()


# ==================== 補捐助「申請案件注意要點」「錯誤樣態歷史案例」頁面 ====================
TW_TZ = timezone(timedelta(hours=8))


def _date_only(ts):
    """'2026-10-13 08:30:00' -> '2026-10-13'"""
    return str(ts or "")[:10]


def _is_recent(ts, days=14):
    """是否為最近 N 天內新增/更新（用來顯示 🆕 標記）"""
    try:
        dt = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TW_TZ)
    except Exception:
        return False
    return (datetime.now(TW_TZ) - dt).days < days


def _latest_update(rows):
    stamps = [r.get("updated_at") for r in rows if r.get("updated_at")]
    return _date_only(max(stamps)) if stamps else ""


def _new_badge(ts):
    if not _is_recent(ts):
        return ""
    return ("<span style='background:#fee2e2;color:#b91c1c;border:1px solid #fca5a5;border-radius:9999px;"
            "padding:1px 8px;font-size:0.75rem;font-weight:700;margin-left:0.5rem;'>🆕 近期更新</span>")


def render_application_notes_page():
    """📌 補捐助申請案件注意要點（活動費／設備費各自一組，承辦人可隨時新增，並顯示更新日期）"""
    is_admin_mode = bool(st.session_state.get("is_admin"))
    all_notes = db.get_application_notes()
    last_upd = _latest_update(all_notes)

    st.markdown(f"""
    <div style="background: linear-gradient(to right, #fffbeb, #fff7ed); border: 1px solid #fde68a; border-radius: 10px; padding: 1.2rem 1.5rem; margin-bottom: 1.2rem;">
        <h3 style="color:#92400e; margin-top:0; margin-bottom:0.4rem;">📌 補捐助申請案件注意要點</h3>
        <p style="color:#78350f; font-size:0.95rem; margin-bottom:0.6rem;">
            依申請類型（活動費、設備費）彙整計畫書、概算表及公文審查時的注意事項，會隨申請案件陸續補充，送件前請先逐項對照。
        </p>
        <span style="font-size:0.85rem; color:#92400e; background:#fef3c7; border:1px solid #fcd34d; border-radius:9999px; padding:2px 12px;">
            🕒 最後更新：<strong>{last_upd or '尚無資料'}</strong> &nbsp;|&nbsp; 共 {len(all_notes)} 項
        </span>
    </div>
    """, unsafe_allow_html=True)

    type_icons = {"活動費": "🎪", "設備費": "🛠️", "共通": "📋", "核銷": "🧾"}
    counts = {t: sum(1 for n in all_notes if n["app_type"] == t) for t in db.APPLICATION_NOTE_TYPES}
    selected_type = st.radio(
        "申請類型",
        db.APPLICATION_NOTE_TYPES,
        horizontal=True,
        key="notes_type_sel",
        format_func=lambda t: f"{type_icons.get(t, '')} {t}（{counts.get(t, 0)} 項）",
        label_visibility="collapsed",
    )

    type_notes = [n for n in all_notes if n["app_type"] == selected_type]
    cn_index = ["一", "二", "三", "四", "五"][min(db.APPLICATION_NOTE_TYPES.index(selected_type), 4)]
    st.markdown(f"#### {cn_index}、{db.APPLICATION_NOTE_TYPE_TITLES.get(selected_type, selected_type)}")
    st.caption(f"🕒 本類最後更新：{_latest_update(type_notes) or '—'}")

    if is_admin_mode:
        with st.expander(f"➕ 【維護模式】新增「{selected_type}」注意事項", expanded=False):
            with st.form(f"add_note_form_{selected_type}", clear_on_submit=True):
                new_title = st.text_input("注意事項標題 *", placeholder="例：品項名稱適法性（宣導品 vs. 贈品/獎品）")
                new_content = st.text_area(
                    "說明內容（每個重點一行，行首可用 * 當項目符號）",
                    height=180,
                    placeholder="* 第一個重點說明\n* 第二個重點說明",
                )
                new_sort = st.number_input("排序（0＝自動排在最後面）", min_value=0, max_value=999, value=0, step=1)
                if st.form_submit_button("➕ 新增注意事項", type="primary", use_container_width=True):
                    if not new_title.strip():
                        st.error("請輸入注意事項標題！")
                    else:
                        db.add_application_note(selected_type, new_title, new_content, sort_order=(new_sort or None))
                        set_flash_message(f"🎉 已新增「{selected_type}」注意事項【{new_title.strip()}】，更新日期已自動記錄。", icon="📌")
                        st.rerun()

    if not all_notes and not db.is_compliance_data_ready():
        st.warning("⚠️ 雲端備份資料暫時無法讀取，為避免覆蓋既有內容，目前先不顯示範例資料。請稍後重新整理頁面再試一次。")
    elif not type_notes:
        st.info(f"目前「{selected_type}」尚無注意事項。" + ("可使用上方【維護模式】表單新增。" if is_admin_mode else ""))

    for n_idx, note in enumerate(type_notes, start=1):
        with st.container(border=True):
            st.markdown(
                f"""
                <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.4rem;">
                    <div>
                        <span style="background:#2563eb;color:#fff;border-radius:6px;padding:1px 9px;font-weight:700;margin-right:0.5rem;">{n_idx}</span>
                        <span style="font-size:1.1rem;font-weight:700;color:#1e293b;">{html.escape(note['title'])}</span>{_new_badge(note['updated_at'])}
                    </div>
                    <div style="font-size:0.85rem;color:#64748b;">🕒 更新日期：<strong>{_date_only(note['updated_at'])}</strong></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if note.get("content") and note["content"].strip():
                st.markdown(format_sop_content_smart(note["content"]))
            else:
                st.caption("（尚無詳細說明）")

            if is_admin_mode:
                with st.expander(f"✏️ 【維護模式】編輯／刪除（ID #{note['id']}）", expanded=False):
                    with st.form(f"edit_note_form_{note['id']}"):
                        t_idx = db.APPLICATION_NOTE_TYPES.index(note["app_type"]) if note["app_type"] in db.APPLICATION_NOTE_TYPES else 0
                        e_type = st.selectbox("申請類型", db.APPLICATION_NOTE_TYPES, index=t_idx, key=f"note_type_{note['id']}")
                        e_title = st.text_input("標題 *", value=note["title"], key=f"note_title_{note['id']}")
                        e_content = st.text_area("說明內容", value=note["content"] or "", height=180, key=f"note_content_{note['id']}")
                        e_sort = st.number_input("排序（數字小的排前面）", min_value=0, max_value=999, value=int(note["sort_order"]), step=1, key=f"note_sort_{note['id']}")
                        if st.form_submit_button("💾 儲存修改（更新日期會同步更新）", type="primary", use_container_width=True):
                            if not e_title.strip():
                                st.error("標題不可為空白！")
                            else:
                                db.update_application_note(note["id"], e_type, e_title, e_content, e_sort)
                                set_flash_message(f"💾 已更新注意事項【{e_title.strip()}】。", icon="📌")
                                st.rerun()
                    confirm_del = st.checkbox("我確認要永久刪除這則注意事項", key=f"note_del_chk_{note['id']}")
                    if st.button("🗑️ 刪除這則注意事項", key=f"note_del_btn_{note['id']}", disabled=not confirm_del):
                        db.delete_application_note(note["id"])
                        set_flash_message(f"🗑️ 已刪除注意事項【{note['title']}】。", msg_type="warning", icon="🗑️")
                        st.rerun()


def render_error_cases_page():
    """⚠️ 補捐助錯誤樣態歷史案例（承辦人可隨時登打新案例，並顯示更新日期）"""
    is_admin_mode = bool(st.session_state.get("is_admin"))
    all_cases = db.get_error_cases()
    last_upd = _latest_update(all_cases)

    st.markdown(f"""
    <div style="background: linear-gradient(to right, #fef2f2, #fff1f2); border: 1px solid #fecaca; border-radius: 10px; padding: 1.2rem 1.5rem; margin-bottom: 1.2rem;">
        <h3 style="color:#991b1b; margin-top:0; margin-bottom:0.4rem;">⚠️ 補捐助錯誤樣態歷史案例</h3>
        <p style="color:#7f1d1d; font-size:0.95rem; margin-bottom:0.6rem;">
            彙整過去補捐助申請、審查、核銷曾發生的錯誤樣態與改善做法，供各分隊填報前比對，避免重複發生相同的退件或糾正。
        </p>
        <span style="font-size:0.85rem; color:#991b1b; background:#fee2e2; border:1px solid #fca5a5; border-radius:9999px; padding:2px 12px;">
            🕒 最後更新：<strong>{last_upd or '尚無資料'}</strong> &nbsp;|&nbsp; 共 {len(all_cases)} 則案例
        </span>
    </div>
    """, unsafe_allow_html=True)

    col_f1, col_f2 = st.columns([2, 3])
    with col_f1:
        f_type = st.selectbox("申請類型", ["全部類型"] + db.ERROR_CASE_TYPES, key="case_type_filter")
    with col_f2:
        f_kw = st.text_input("關鍵字搜尋", placeholder="標題、年度、錯誤說明、改善做法…", key="case_kw_filter")

    if is_admin_mode:
        with st.expander("➕ 【維護模式】新增錯誤樣態案例", expanded=False):
            with st.form("add_case_form", clear_on_submit=True):
                col_a1, col_a2, col_a3 = st.columns([4, 2, 2])
                with col_a1:
                    c_title = st.text_input("案例標題 / 錯誤樣態 *", placeholder="例：計畫書與概算表品項名稱不一致")
                with col_a2:
                    c_type = st.selectbox("申請類型 *", db.ERROR_CASE_TYPES)
                with col_a3:
                    c_year = st.text_input("發生年度（選填）", placeholder="例：114 年度")
                c_desc = st.text_area("❌ 錯誤樣態說明", height=110, placeholder="發生了什麼狀況？")
                c_cons = st.text_area("⚠️ 審查意見／造成的問題（選填）", height=80, placeholder="例：遭審核單位退件、要求補正…")
                c_fix = st.text_area("✅ 正確做法／改善建議", height=110, placeholder="下次應如何避免？")
                if st.form_submit_button("➕ 新增案例", type="primary", use_container_width=True):
                    if not c_title.strip():
                        st.error("請輸入案例標題！")
                    else:
                        db.add_error_case(c_type, c_title, c_year, c_desc, c_cons, c_fix)
                        set_flash_message(f"🎉 已新增錯誤樣態案例【{c_title.strip()}】，更新日期已自動記錄。", icon="⚠️")
                        st.rerun()

    cases = db.get_error_cases(app_type=None if f_type == "全部類型" else f_type, keyword=f_kw)
    st.caption(f"符合條件 **{len(cases)}** 則 / 全部 {len(all_cases)} 則（依更新日期由新到舊排列）")

    if not all_cases and not db.is_compliance_data_ready():
        st.warning("⚠️ 雲端備份資料暫時無法讀取，為避免覆蓋既有內容，目前先不顯示案例資料。請稍後重新整理頁面再試一次。")
    elif not all_cases:
        st.info("目前尚無錯誤樣態案例。" + ("可使用上方【維護模式】表單登打第一則案例。" if is_admin_mode else ""))
    elif not cases:
        st.info("沒有符合篩選條件的案例。")

    type_colors = {
        "活動費": ("#dbeafe", "#1d4ed8"),
        "設備費": ("#ffedd5", "#c2410c"),
        "共通／其他": ("#ede9fe", "#5b21b6"),
    }
    for case in cases:
        bg, fg = type_colors.get(case["app_type"], ("#f1f5f9", "#475569"))
        year_html = (f"<span style='background:#f1f5f9;color:#475569;border-radius:6px;padding:1px 8px;"
                     f"font-size:0.8rem;margin-right:0.4rem;'>📅 {html.escape(case['case_year'])}</span>") if case.get("case_year") else ""
        with st.container(border=True):
            st.markdown(
                f"""
                <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.4rem;">
                    <div>
                        <span style="background:{bg};color:{fg};border-radius:6px;padding:1px 9px;font-weight:700;font-size:0.82rem;margin-right:0.4rem;">{html.escape(case['app_type'])}</span>{year_html}
                        <span style="font-size:1.1rem;font-weight:700;color:#1e293b;">{html.escape(case['title'])}</span>{_new_badge(case['updated_at'])}
                    </div>
                    <div style="font-size:0.85rem;color:#64748b;">🕒 更新日期：<strong>{_date_only(case['updated_at'])}</strong></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if case.get("description") and case["description"].strip():
                st.markdown("**❌ 錯誤樣態**")
                st.markdown(format_sop_content_smart(case["description"]))
            if case.get("consequence") and case["consequence"].strip():
                st.markdown("**⚠️ 審查意見／造成的問題**")
                st.markdown(format_sop_content_smart(case["consequence"]))
            if case.get("correction") and case["correction"].strip():
                st.success("**✅ 正確做法／改善建議**\n\n" + format_sop_content_smart(case["correction"]))

            if is_admin_mode:
                with st.expander(f"✏️ 【維護模式】編輯／刪除（ID #{case['id']}）", expanded=False):
                    with st.form(f"edit_case_form_{case['id']}"):
                        col_e1, col_e2, col_e3 = st.columns([4, 2, 2])
                        with col_e1:
                            e_title = st.text_input("案例標題 *", value=case["title"], key=f"case_title_{case['id']}")
                        with col_e2:
                            t_idx = db.ERROR_CASE_TYPES.index(case["app_type"]) if case["app_type"] in db.ERROR_CASE_TYPES else 0
                            e_type = st.selectbox("申請類型", db.ERROR_CASE_TYPES, index=t_idx, key=f"case_type_{case['id']}")
                        with col_e3:
                            e_year = st.text_input("發生年度", value=case["case_year"] or "", key=f"case_year_{case['id']}")
                        e_desc = st.text_area("❌ 錯誤樣態說明", value=case["description"] or "", height=110, key=f"case_desc_{case['id']}")
                        e_cons = st.text_area("⚠️ 審查意見／造成的問題", value=case["consequence"] or "", height=80, key=f"case_cons_{case['id']}")
                        e_fix = st.text_area("✅ 正確做法／改善建議", value=case["correction"] or "", height=110, key=f"case_fix_{case['id']}")
                        if st.form_submit_button("💾 儲存修改（更新日期會同步更新）", type="primary", use_container_width=True):
                            if not e_title.strip():
                                st.error("案例標題不可為空白！")
                            else:
                                db.update_error_case(case["id"], e_type, e_title, e_year, e_desc, e_cons, e_fix)
                                set_flash_message(f"💾 已更新案例【{e_title.strip()}】。", icon="⚠️")
                                st.rerun()
                    confirm_del = st.checkbox("我確認要永久刪除這則案例", key=f"case_del_chk_{case['id']}")
                    if st.button("🗑️ 刪除這則案例", key=f"case_del_btn_{case['id']}", disabled=not confirm_del):
                        db.delete_error_case(case["id"])
                        set_flash_message(f"🗑️ 已刪除案例【{case['title']}】。", msg_type="warning", icon="🗑️")
                        st.rerun()


def _flow_markdown(lines):
    """流程步驟清單 -> Markdown：一般項目自動編號，以「　•」開頭的當成上一項的子項目"""
    out, n = [], 0
    for ln in lines:
        if ln.startswith("　•"):
            out.append("   - " + ln.lstrip("　• ").strip())
        else:
            n += 1
            out.append(f"{n}. {ln}")
    return "\n".join(out)


def render_subsidy_process_page():
    """🧭 申請與核銷流程：分隊／大隊／科室各做什麼、數字速查、陳報單範例句、科室對照、常見問答"""
    st.markdown("""
    <div style="background: linear-gradient(to right, #eff6ff, #f0f9ff); border: 1px solid #bfdbfe; border-radius: 10px; padding: 1.2rem 1.5rem; margin-bottom: 1.2rem;">
        <h3 style="color:#1e3a8a; margin-top:0; margin-bottom:0.4rem;">🧭 補捐助申請與核銷流程</h3>
        <p style="color:#1e40af; font-size:0.95rem; margin-bottom:0;">
            議員及代表建議補助款的申請、核銷作業，依「補助經費來源」選擇你的案件類型，就能看到分隊、大隊、承辦業務科室各自要做的事，以及發文單位與憑證去向。
        </p>
    </div>
    """, unsafe_allow_html=True)

    col_l1, col_l2 = st.columns(2)
    with col_l1:
        st.link_button("📲 申請單位：登錄案件基本資訊（QR Code）", sc.ONLINE_REGISTER_URL, use_container_width=True)
    with col_l2:
        st.link_button("📊 本局同仁：後台追蹤審核與撥款進度", sc.ONLINE_TRACK_URL, use_container_width=True)
    st.caption("陳報案件時須先完成線上登錄；同一案件有不同經費來源（縣府、公所…）時，要依來源分別登錄、分案填寫。"
               "未完成登錄的案件，大隊初審會直接退件，業務科室也會暫緩發文。")

    stage = st.radio(
        "流程階段", ["申請", "核銷"], horizontal=True, key="flow_stage", label_visibility="collapsed",
        format_func=lambda x: {"申請": "📝 申請階段", "核銷": "🧾 核銷階段"}[x],
    )
    combo = st.selectbox("這個案件的補助經費來源", sc.COMBOS, key="flow_combo")
    flow = sc.FLOW[stage][combo]
    st.info(f"📮 **發文單位**：{flow['發文']}")

    col_r1, col_r2, col_r3 = st.columns(3)
    for col, (label, key) in zip((col_r1, col_r2, col_r3),
                                 (("🧑‍🚒 分隊", "分隊"), ("🏢 大隊", "大隊"), ("🏛️ 局本部／承辦業務科室", "科室"))):
        with col:
            with st.container(border=True):
                st.markdown(f"**{label}**")
                st.markdown(_flow_markdown(flow[key]))

    st.markdown("---")
    st.markdown("#### 🔢 數字速查")
    for row_start in range(0, len(sc.QUICK_NUMBERS), 4):
        cols = st.columns(4)
        for col, (num, desc) in zip(cols, sc.QUICK_NUMBERS[row_start:row_start + 4]):
            with col:
                with st.container(border=True):
                    st.markdown(f"<div style='font-size:1.6rem;font-weight:800;color:#1d4ed8;'>{html.escape(num)}</div>"
                                f"<div style='font-size:0.85rem;color:#475569;'>{html.escape(desc)}</div>", unsafe_allow_html=True)

    st.markdown("#### 📝 陳報單範例句（點右上角圖示可複製，ＯＯＯ換成實際內容）")
    for label, text in sc.SAMPLE_SENTENCES.items():
        st.caption(label)
        try:
            st.code(text, language=None, wrap_lines=True)
        except TypeError:  # 舊版 Streamlit 沒有 wrap_lines 參數
            st.code(text, language=None)

    st.markdown("#### 🏢 業務科室承辦案件類別")
    st.dataframe(pd.DataFrame(sc.OFFICE_TABLE, columns=["科室名稱", "承辦案件類別"]), hide_index=True, use_container_width=True)

    st.markdown("#### ❓ 常見問答")
    for q, a in sc.FAQ:
        with st.expander(q):
            st.markdown(a)


def _banner_inline_markup(text):
    """提示文字：先跳脫 HTML（避免亂碼或惡意標籤），再把 **粗體**、==紅色粗體== 標記轉成樣式，換行轉成 <br>"""
    safe = html.escape(text or "")
    safe = re.sub(r"==(.+?)==", r'<span style="color:#dc2626;font-weight:700;">\1</span>', safe)
    safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)
    return safe.replace("\n", "<br>")


def render_subsidy_banner():
    """補捐助業務頁面最上方的流程說明區塊（標題、流程步驟、提示文字，承辦人可在網頁上修改）"""
    banner = db.get_subsidy_banner()
    status_class = {"一般": "step-plain", "已完成": "step-done", "進行中": "step-active", "未開始": "step-pending"}

    steps_html = ""
    if banner["steps"]:
        steps_html = " ➔ ".join(
            f'<span class="pipeline-step {status_class.get(stp["status"], "step-pending")}">{i}. {html.escape(stp["name"])}</span>'
            for i, stp in enumerate(banner["steps"], start=1)
        )
        steps_html = f'<div style="margin-top: 0.5rem;">{steps_html}</div>'
    hint_html = ""
    if banner["hint"].strip():
        hint_html = (f'<div style="margin-top: 0.8rem; font-size: 0.88rem; color: #15803d;">'
                     f'{_banner_inline_markup(banner["hint"])}</div>')
    updated_html = ""
    if banner["updated_at"]:
        updated_html = (f'<div style="margin-top:0.6rem;font-size:0.8rem;color:#64748b;text-align:right;">'
                        f'🕒 更新日期：{_date_only(banner["updated_at"])}</div>')

    st.markdown(
        f'''
        <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 1rem 1.2rem; margin-bottom: 1.2rem;">
            <h4 style="color: #166534; margin-top:0; margin-bottom: 0.5rem;">🎯 {html.escape(banner["title"])}</h4>
            {steps_html}{hint_html}{updated_html}
        </div>
        ''',
        unsafe_allow_html=True,
    )

    if not st.session_state.get("is_admin"):
        return

    with st.expander("✏️ 【維護模式】編輯這個說明區塊（標題、流程步驟、提示文字）", expanded=False):
        with st.form("subsidy_banner_form"):
            e_title = st.text_input("區塊標題", value=banner["title"])
            st.markdown("**流程步驟**　（直接點格子修改；表格最下面的空白列可新增步驟；"
                        "勾選列左邊的框後按鍵盤 Delete 可刪除；依「順序」由小到大排列）")
            steps_df = pd.DataFrame({
                "順序": list(range(1, len(banner["steps"]) + 1)),
                "步驟名稱": [x["name"] for x in banner["steps"]],
                "目前狀態": [x["status"] for x in banner["steps"]],
            })
            edited_steps = st.data_editor(
                steps_df,
                num_rows="dynamic",
                hide_index=True,
                use_container_width=True,
                key=f"subsidy_banner_steps_{banner['updated_at']}",
                column_config={
                    "順序": st.column_config.NumberColumn("順序", min_value=1, step=1, width="small"),
                    "步驟名稱": st.column_config.TextColumn("步驟名稱（會自動加上編號）", required=True, width="medium"),
                    "目前狀態": st.column_config.SelectboxColumn("目前狀態", options=db.SUBSIDY_STEP_STATUSES, required=True, default="未開始", width="small"),
                },
            )
            e_hint = st.text_area("提示文字（可留空）", value=banner["hint"], height=100)
            st.caption("標記寫法：`**文字**` ＝ 粗體；`==文字==` ＝ 紅色粗體；按 Enter 可換行。")
            if st.form_submit_button("💾 儲存（更新日期會同步更新）", type="primary", use_container_width=True):
                db.save_subsidy_banner(e_title, e_hint, db.steps_from_editor_records(edited_steps.to_dict("records")))
                set_flash_message("💾 已更新補捐助業務的流程說明區塊。", icon="🎯")
                st.rerun()

        if banner["updated_at"]:
            confirm_reset = st.checkbox("我確認要恢復為系統預設內容（目前自訂的內容會被清除）", key="subsidy_banner_reset_chk")
            if st.button("🔄 恢復為預設內容", key="subsidy_banner_reset_btn", disabled=not confirm_reset):
                db.reset_subsidy_banner()
                set_flash_message("🔄 已恢復為預設的流程說明內容。", icon="🎯")
                st.rerun()


def render_settlement_check_page():
    """✅ 核銷自我檢核：分隊在送大隊初審前，先自行檢查收支清單金額與核銷文件是否齊全。

    所有輸入只留在目前這個瀏覽器分頁的記憶體中，不寫入資料庫、不上傳。
    """
    import subsidy_check as chk

    st.markdown("""
    <div style="background: linear-gradient(to right, #f0fdf4, #ecfdf5); border: 1px solid #bbf7d0; border-radius: 10px; padding: 1.2rem 1.5rem; margin-bottom: 1.2rem;">
        <h3 style="color:#166534; margin-top:0; margin-bottom:0.4rem;">✅ 核銷自我檢核</h3>
        <p style="color:#14532d; font-size:0.95rem; margin-bottom:0.4rem;">
            送大隊初審前，先自己檢查一次：①收支清單的金額有沒有違反補助比例規定、②核銷文件有沒有備齊。
            規則與大隊「建議補助款【核銷案】初審檢核表」一致。
        </p>
        <span style="font-size:0.85rem; color:#166534; background:#dcfce7; border:1px solid #86efac; border-radius:9999px; padding:2px 12px;">
            🔒 輸入的資料只在這個網頁暫時計算，不會儲存或上傳
        </span>
    </div>
    """, unsafe_allow_html=True)

    # radio 離開頁面時 Streamlit 會清掉元件狀態，所以另外用一個普通的 session_state 記住選項，
    # 以 index 還原，避免畫面上顯示的選項和實際內容不一致。
    _modes = ["💰 收支清單金額檢核", "📋 核銷文件檢核"]
    mode = st.radio("檢核項目", _modes, horizontal=True, label_visibility="collapsed",
                    index=_modes.index(st.session_state.get("settle_mode_saved", _modes[0])),
                    key="settle_mode_widget")
    st.session_state["settle_mode_saved"] = mode

    if mode == "💰 收支清單金額檢核":
        sample_rows = [
            {"項目": "住宿", "類別": "住宿", "預算金額(A)": 50000, "實際金額(B)": 50000, "補助款支應": 50000, "自籌款支應": 0},
            {"項目": "中、晚餐", "類別": "餐費", "預算金額(A)": 40000, "實際金額(B)": 29200, "補助款支應": 10000, "自籌款支應": 19200},
            {"項目": "船資", "類別": "交通", "預算金額(A)": 48000, "實際金額(B)": 40500, "補助款支應": 0, "自籌款支應": 40500},
            {"項目": "租賃機車", "類別": "一般", "預算金額(A)": 4000, "實際金額(B)": 4000, "補助款支應": 0, "自籌款支應": 4000},
        ]
        blank_rows = [{"項目": "", "類別": "一般", "預算金額(A)": 0, "實際金額(B)": 0, "補助款支應": 0, "自籌款支應": 0}]
        if "settle_version" not in st.session_state:
            st.session_state["settle_version"] = 0
            st.session_state["settle_df"] = pd.DataFrame(blank_rows)
            st.session_state["settle_approved"] = 0

        col_b1, col_b2, _ = st.columns([1.2, 1.2, 4])
        with col_b1:
            if st.button("📝 載入範例", use_container_width=True, key="settle_load_sample"):
                st.session_state["settle_df"] = pd.DataFrame(sample_rows)
                st.session_state["settle_approved"] = 60000
                st.session_state["settle_version"] += 1
                st.rerun()
        with col_b2:
            if st.button("🗑️ 清空重填", use_container_width=True, key="settle_clear"):
                st.session_state["settle_df"] = pd.DataFrame(blank_rows)
                st.session_state["settle_approved"] = 0
                st.session_state["settle_version"] += 1
                st.rerun()

        ver = st.session_state["settle_version"]
        approved = st.number_input("縣府（公所）核定補助金額（元）", min_value=0, step=1000,
                                   value=int(st.session_state["settle_approved"]), key=f"settle_approved_in_{ver}")
        st.session_state["settle_approved"] = int(approved)
        st.caption("依收支清單逐項填寫：每一項的「實際金額」須等於「補助款支應」＋「自籌款支應」。"
                   "「類別」用來套用餐費／紀念品 50%、雜支 5% 等限制。範例為虛構數字。")
        edited = st.data_editor(
            st.session_state["settle_df"], num_rows="dynamic", use_container_width=True, key=f"settle_editor_{ver}",
            column_config={
                "項目": st.column_config.TextColumn("項目", width="medium"),
                "類別": st.column_config.SelectboxColumn("類別", options=chk.ITEM_KINDS, required=True),
                "預算金額(A)": st.column_config.NumberColumn("預算金額(A)", min_value=0, step=100, format="%d"),
                "實際金額(B)": st.column_config.NumberColumn("實際金額(B)", min_value=0, step=100, format="%d"),
                "補助款支應": st.column_config.NumberColumn("補助款支應", min_value=0, step=100, format="%d"),
                "自籌款支應": st.column_config.NumberColumn("自籌款支應", min_value=0, step=100, format="%d"),
            },
        )

        items = [
            {"name": r.get("項目"), "kind": r.get("類別"), "budget": r.get("預算金額(A)"),
             "actual": r.get("實際金額(B)"), "subsidy": r.get("補助款支應"), "self_fund": r.get("自籌款支應")}
            for r in edited.to_dict("records")
        ]
        findings = chk.check_settlement(approved, items)

        tot_a = float(pd.to_numeric(edited["預算金額(A)"], errors="coerce").fillna(0).sum())
        tot_b = float(pd.to_numeric(edited["實際金額(B)"], errors="coerce").fillna(0).sum())
        tot_s = float(pd.to_numeric(edited["補助款支應"], errors="coerce").fillna(0).sum())
        tot_f = float(pd.to_numeric(edited["自籌款支應"], errors="coerce").fillna(0).sum())
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("預算合計 (A)", f"{tot_a:,.0f}")
        m2.metric("實際合計 (B)", f"{tot_b:,.0f}")
        m3.metric("補助款合計", f"{tot_s:,.0f}", f"{tot_s / tot_b:.1%}" if tot_b else None, delta_color="off")
        m4.metric("自籌款合計", f"{tot_f:,.0f}", f"{tot_f / tot_b:.1%}" if tot_b else None, delta_color="off")

        n_err = sum(1 for f in findings if f.level == chk.ERROR)
        n_warn = sum(1 for f in findings if f.level == chk.WARN)
        if n_err:
            st.error(f"❌ 發現 {n_err} 項不符規定，請修正後再送大隊初審。")
        elif n_warn:
            st.warning(f"⚠️ 金額規定都符合，另有 {n_warn} 項提醒請對照附件。")
        else:
            st.success("✅ 金額檢核全部通過。")
        for f in findings:
            line = f"**{f.title}**" + (f"：{f.detail}" if f.detail else "")
            if f.level == chk.ERROR:
                st.error(line, icon="❌")
            elif f.level == chk.WARN:
                st.warning(line, icon="⚠️")
            else:
                st.success(line, icon="✅")
        st.caption("檢核結果僅供填報前自我提醒，最終以縣府核定函及大隊、會計室審查意見為準。")

    else:
        st.markdown("**先勾選這個案件的情況**（會決定哪些附件需要檢查）：")
        approved_amt = int(st.session_state.get("settle_approved") or 0)
        auto_over_20k = approved_amt > chk.SELF_FUND_THRESHOLD
        st.session_state["settle_cond_gov_over_20k"] = auto_over_20k
        selected_conds = []
        for code, label in chk.DOC_CONDITIONS.items():
            follows_amount = code == "gov_over_20k"
            if st.checkbox(label, key=f"settle_cond_{code}", disabled=follows_amount):
                selected_conds.append(code)
            if follows_amount:
                if auto_over_20k:
                    st.caption(f"已依收支清單的核定補助金額 {approved_amt:,} 元自動勾選（超過 2 萬元）。")
                else:
                    st.caption("此項跟著「收支清單金額檢核」的核定補助金額自動勾選；目前金額未超過 2 萬元。")
        todo = chk.applicable_documents(selected_conds)
        st.markdown("---")
        st.markdown("**逐項勾選已完成的項目：**")
        checked = set()
        last_group = None
        todo_set = set(todo)
        for i, (group, text, _cond) in enumerate(chk.DOC_CHECKLIST):
            if (group, text) not in todo_set:
                continue
            if group != last_group:
                st.markdown(f"##### {group}")
                last_group = group
            if st.checkbox(text, key=f"settle_doc_{i}"):
                checked.add(text)
        missing, total = chk.check_documents(checked, selected_conds)
        st.markdown("---")
        st.progress((total - len(missing)) / total if total else 0.0,
                    text=f"已完成 {total - len(missing)} / {total} 項")
        if missing:
            st.warning(f"⚠️ 還有 {len(missing)} 項未完成：")
            for g, t in missing:
                st.markdown(f"- 【{g}】{t}")
        else:
            st.success("✅ 全部項目都已完成，可以送大隊初審。")


def _apply_plan_preset(ver, preset, plan_type="training"):
    """把計畫書表單設成初始、空白、範例或歷史案例（preset="case:<key>"）。
    欄位寫進下一個版本的 widget key，避免清空後殘留。"""
    pg = load_plan_generator()
    from datetime import date, timedelta

    today = date.today()
    start_default = today + timedelta(days=45)
    texts = {"background": "", "purpose": "", "method": "", "rules": ""}
    if preset == "sample" or preset.startswith("case:"):
        data = pg.case_inputs(preset.split(":", 1)[1], today) if preset.startswith("case:") else pg.example_inputs(today)
        texts = {k: data.get(k, "") for k in texts}
        unit, name = data["unit"], data["name"]
        year, start, end = data["year"], data["start"], data["end"]
        place, audience = data["place"], data["audience"]
        headcount = data["headcount"]
        co, councilors = data["co_organizer"], data["councilors"]
        instructors, supervisor = data["instructors"], data["supervisor"]
        subsidy = data["subsidy"]
        sources = [
            {"類型": "代表" if sc["kind"] == "rep" else "議員", "姓名": sc["names"], "公所": sc["township"],
             "金額": int(sc["amount"])}
            for sc in pg.normalize_sources(data.get("sources"), councilors, subsidy)
        ]
        awards = [{"職務": a["role"], "人數": a["count"], "種類": a["kind"], "次數": a["times"]}
                  for a in pg.normalize_awards(data.get("awards"))]
        meet = data.get("meet", "")
        courses = [
            {"日期": c["date"], "時間": c["time"], "課程內容": c["content"], "教官／講師": c["teacher"]}
            for c in data["courses"]
        ]
        items = [
            {"項目": i["name"], "類別": i["kind"], "數量": i["qty"], "單位": i["unit"],
             "單價": i["price"], "用途說明": i["use"]}
            for i in data["items"]
        ]
    elif preset == "blank":
        unit = name = place = audience = co = councilors = instructors = supervisor = ""
        year, start, end = pg.roc_year(today), None, None
        headcount, subsidy = 0, 0
        sources = [{"類型": "議員", "姓名": "", "公所": "", "金額": 0}]
        awards, meet = [], ""
        courses = [{"日期": None, "時間": "", "課程內容": "", "教官／講師": ""}]
        items = [{"項目": "", "類別": "設備購置" if plan_type == "equipment" else "一般",
                  "數量": 0, "單位": "", "單價": 0, "用途說明": ""}]
    else:
        unit = name = place = audience = co = councilors = instructors = ""
        year, start, end = pg.roc_year(today), start_default, start_default
        headcount, subsidy = 30, 0
        supervisor = "本大隊大隊長、副大隊長隨時督導考核"
        courses = [
            {"日期": start, "時間": "08:10－09:00", "課程內容": "學員簽到", "教官／講師": ""},
            {"日期": start, "時間": "09:10－10:00", "課程內容": "", "教官／講師": ""},
            {"日期": start, "時間": "10:10－11:00", "課程內容": "", "教官／講師": ""},
            {"日期": start, "時間": "12:00－13:30", "課程內容": "午餐及休息", "教官／講師": ""},
        ]
        sources = [{"類型": "議員", "姓名": "", "公所": "", "金額": 0}]
        awards, meet = [], ""
        if plan_type == "activity":
            supervisor = ""
            courses = [{"日期": None, "時間": "", "課程內容": "", "教官／講師": ""}]
        if plan_type == "equipment":
            supervisor = ""
            start = end = None
            headcount = 0
            courses = [{"日期": None, "時間": "", "課程內容": "", "教官／講師": ""}]
        items = [{"項目": "", "類別": "設備購置" if plan_type == "equipment" else "一般",
                  "數量": 0, "單位": "", "單價": 0, "用途說明": ""}]

    acct = st.session_state.get("case_user")
    if acct is not None:
        unit = _default_squad_name(acct) or unit      # 已登入：申請單位用自己的單位，不用範例的
    st.session_state[f"plan_unit_{ver}"] = unit
    st.session_state[f"plan_name_{ver}"] = name
    st.session_state[f"plan_year_{ver}"] = int(year)
    st.session_state[f"plan_start_{ver}"] = start
    st.session_state[f"plan_end_{ver}"] = end
    st.session_state[f"plan_place_{ver}"] = place
    st.session_state[f"plan_aud_{ver}"] = audience
    st.session_state[f"plan_hc_{ver}"] = int(headcount)
    st.session_state[f"plan_co_{ver}"] = co
    st.session_state[f"plan_cl_{ver}"] = councilors
    st.session_state[f"plan_ins_{ver}"] = instructors
    st.session_state[f"plan_sup_{ver}"] = supervisor
    st.session_state[f"plan_sub_{ver}"] = int(subsidy)
    st.session_state[f"plan_bg_{ver}"] = texts["background"]
    st.session_state[f"plan_pu_{ver}"] = texts["purpose"]
    st.session_state[f"plan_me_{ver}"] = texts["method"]
    st.session_state[f"plan_ru_{ver}"] = texts["rules"]
    st.session_state["plan_items"] = pd.DataFrame(items)
    st.session_state["plan_sources"] = pd.DataFrame(sources)
    st.session_state["plan_awards"] = pd.DataFrame(awards, columns=["職務", "人數", "種類", "次數"])
    st.session_state[f"plan_meet_{ver}"] = meet
    st.session_state["plan_courses"] = pd.DataFrame(courses)
    st.session_state["plan_roster_base"] = pd.DataFrame([{"單位": "", "職稱": "", "姓名": ""}])


# 切到別的分頁再切回來時，Streamlit 會丟掉沒有顯示的欄位內容。這裡每次畫完表單就把內容備份一份，
# 回到產生器發現欄位被丟掉時再還原，避免同仁填到一半切去看別的頁就全部消失。
_PLAN_BUTTON_PREFIXES = ("plan_load_", "plan_clear", "plan_register_", "plan_item_del_", "plan_item_add_")
_PLAN_STATE_KEYS = {"plan_keep", "plan_ver", "plan_started", "plan_type_applied", "plan_items", "plan_sources",
                    "plan_courses", "plan_awards", "plan_item_rev", "plan_edit_rev", "plan_roster_base"}


def _snapshot_generator_state(ver, frames):
    import datetime as _dt
    widgets = {}
    for k, v in st.session_state.items():
        if not isinstance(k, str) or not k.startswith("plan_") or k in _PLAN_STATE_KEYS:
            continue
        if "editor" in k or k.startswith(_PLAN_BUTTON_PREFIXES):
            continue
        if not (k.endswith(f"_{ver}") or k in ("plan_type_sel", "plan_case_sel")):
            continue
        if isinstance(v, (str, int, float, bool, list, _dt.date, type(None))):
            widgets[k] = v
    st.session_state["plan_keep"] = {"ver": ver, "widgets": widgets,
                                     "frames": {k: df.copy() for k, df in frames.items()}}


def _restore_generator_state():
    keep = st.session_state.get("plan_keep")
    ver = st.session_state.get("plan_ver")
    if not keep or ver is None or keep.get("ver") != ver or not st.session_state.get("plan_started"):
        return
    if f"plan_unit_{ver}" in st.session_state:        # 表單還在，不用還原
        return
    for k, v in keep["widgets"].items():
        st.session_state[k] = v
    for k, df in keep["frames"].items():
        st.session_state[k] = df.copy()
    st.session_state["plan_edit_rev"] = st.session_state.get("plan_edit_rev", 0) + 1


def render_plan_generator_page():
    _restore_generator_state()
    _render_plan_generator_inner()


def _default_squad_name(acct):
    """申請單位預設值：分隊帳號「台東救護分隊」→「臺東救護義消分隊」；大隊帳號用大隊名稱。可再修改。"""
    if acct.role == "unit" and acct.unit:
        base = acct.unit.replace("台東", "臺東")
        return base if base.endswith("義消分隊") else base.replace("分隊", "義消分隊")
    if acct.role == "battalion":
        return acct.battalion.replace("台東", "臺東")
    return ""


def _step_heading(text):
    st.markdown(f'<h4 style="color:#dc2626; margin:1.5rem 0 0.3rem 0; font-weight:700;">{text}</h4>',
                unsafe_allow_html=True)


def _render_plan_generator_inner():
    """✏️ 計畫書產生器：選計畫類型、填必要資料，產出計畫書（Word）與概算表（Excel）草稿。

    先套用申請階段的規則檢查。輸入只留在目前瀏覽器分頁的記憶體中，不寫入資料庫、不上傳。
    """
    pg = load_plan_generator()

    st.markdown("""
    <div style="background: linear-gradient(to right, #eff6ff, #eef2ff); border: 1px solid #bfdbfe; border-radius: 10px; padding: 1.2rem 1.5rem; margin-bottom: 1.2rem;">
        <h3 style="color:#1e3a8a; margin-top:0; margin-bottom:0.4rem;">✏️ 計畫書與概算表產生器（草稿）</h3>
        <p style="color:#1e40af; font-size:0.95rem; margin-bottom:0.4rem;">
            選擇計畫類型、填入必要資料，系統用固定範本產出<strong>計畫書（Word）</strong>與<strong>經費概算表（Excel）</strong>草稿，
            並在產出前先檢查自籌款、餐費比例、用字、備註欄等規定。
        </p>
        <span style="font-size:0.85rem; color:#1e3a8a; background:#dbeafe; border:1px solid #93c5fd; border-radius:9999px; padding:2px 12px;">
            🔒 輸入的資料只在這個網頁暫時計算，不會儲存或上傳｜草稿仍須由承辦人確認後再送審
        </span>
    </div>
    """, unsafe_allow_html=True)

    enabled, acct = case_pages.login_gate()
    if enabled and acct is None:
        return
    if acct is not None:
        st.caption(f"登入：{acct.label}　申請單位會自動帶入您的單位，需要時仍可修改。")

    step_no = [0]

    def step(title):
        step_no[0] += 1
        _step_heading(f"步驟{'零一二三四五六七八九十'[step_no[0]]}：{title}")

    step("選擇計畫類型")
    type_keys = list(pg.PLAN_TYPES.keys())
    plan_type = st.selectbox("計畫類型", type_keys, format_func=lambda k: pg.PLAN_TYPES[k]["label"], key="plan_type_sel")
    info = pg.PLAN_TYPES[plan_type]
    is_equip = plan_type == "equipment"
    st.caption(info["desc"])

    if "plan_ver" not in st.session_state:
        st.session_state["plan_ver"] = 0
        st.session_state["plan_type_applied"] = plan_type
        _apply_plan_preset(0, "starter", plan_type)
    elif st.session_state.get("plan_type_applied") != plan_type:
        # 切換計畫類型：欄位名稱與範本不同，重置成該類型的初始表單
        new_ver = st.session_state["plan_ver"] + 1
        _apply_plan_preset(new_ver, "starter", plan_type)
        st.session_state["plan_ver"] = new_ver
        st.session_state["plan_type_applied"] = plan_type
        st.session_state["plan_started"] = False       # 換類型要重新選「載入案例」或「清空重填」

    step("載入歷史案例，或清空重填")
    st.caption("選一個和你案件最像的歷史案例，按「載入案例」後再依實際情形修改；也可以按「清空重填」從空白開始。"
               "按了其中一個，下面的填寫欄位才會出現。")
    c1, c2, _ = st.columns([1.3, 1.3, 4])
    with c1:
        if plan_type == "training" and st.button("📝 載入範例", use_container_width=True, key="plan_load_sample"):
            new_ver = st.session_state["plan_ver"] + 1
            _apply_plan_preset(new_ver, "sample", plan_type)
            st.session_state["plan_ver"] = new_ver
            st.session_state["plan_started"] = True
            st.rerun()
    with c2:
        if st.button("🗑️ 清空重填", use_container_width=True, key="plan_clear"):
            new_ver = st.session_state["plan_ver"] + 1
            _apply_plan_preset(new_ver, "blank", plan_type)
            st.session_state["plan_ver"] = new_ver
            st.session_state["plan_started"] = True
            st.rerun()
    cases = pg.case_list(plan_type)
    if cases:
        k1, k2 = st.columns([4, 1.3])
        labels = {key: label for key, label, _s in cases}
        case_key = k1.selectbox("歷史案例（已去識別化，載入後再依實際情形修改）", [key for key, _l, _s in cases],
                                format_func=lambda k: labels[k], key="plan_case_sel")
        k1.caption(next(s for key, _l, s in cases if key == case_key)
                   + " 載入後日期改為今天起 45 天，補助款依各項金額比例重新分配。")
        k2.markdown("<div style='height:1.9rem'></div>", unsafe_allow_html=True)
        if k2.button("📚 載入案例", use_container_width=True, key="plan_load_case"):
            new_ver = st.session_state["plan_ver"] + 1
            _apply_plan_preset(new_ver, f"case:{case_key}", plan_type)
            st.session_state["plan_ver"] = new_ver
            st.session_state["plan_started"] = True
            st.rerun()
    ver = st.session_state["plan_ver"]
    er = st.session_state.get("plan_edit_rev", 0)
    if not st.session_state.get("plan_started"):
        st.info("👆 請先按上面的「載入案例」或「清空重填」，接下來的填寫欄位才會出現。")
        return

    step("基本資料")
    a1, a2, a3 = st.columns([2, 2, 1])
    unit = a1.text_input("申請單位 *", placeholder="例：達仁義消分隊", key=f"plan_unit_{ver}")
    name = a2.text_input("活動名稱 *", placeholder="例：繩索救助訓練（不必寫年度與「計畫」）", key=f"plan_name_{ver}")
    year = a3.number_input("年度（民國）", min_value=100, max_value=200, step=1, key=f"plan_year_{ver}")
    b1, b2, b3 = st.columns([1.3, 1.3, 2.4])
    if is_equip:
        d_end = b1.date_input("預計完成日期（選填）", key=f"plan_end_{ver}")
        d_start = d_end
        place = b3.text_input("設置地點 *", placeholder="例：臺東分隊", key=f"plan_place_{ver}")
    else:
        d_start = b1.date_input("開始日期 *", key=f"plan_start_{ver}")
        d_end = b2.date_input("結束日期 *", key=f"plan_end_{ver}")
        place = b3.text_input("地點 *", placeholder="例：達仁分隊訓練廣場", key=f"plan_place_{ver}")
    d1, d2 = st.columns([3, 1])
    audience = d1.text_input(f"{info['audience_label']} *", placeholder="例：本大隊所屬達仁義消人員（含教官團）", key=f"plan_aud_{ver}")
    headcount = d2.number_input(info["headcount_label"], min_value=0, step=1, key=f"plan_hc_{ver}")
    co_org = st.text_input("協辦單位（選填）", placeholder="例：大武大隊達仁分隊", key=f"plan_co_{ver}")
    if info["show_instructors"]:
        instructors = st.text_input("訓練師資（選填）", placeholder="例：由本分隊具備陸域救助訓練教官或助教資格之人員組成", key=f"plan_ins_{ver}")
    else:
        instructors = ""
    supervisor = st.text_input("督導考核（選填）", placeholder="例：本大隊大隊長、副大隊長隨時督導考核", key=f"plan_sup_{ver}")

    if is_equip:
        courses_df = st.session_state["plan_courses"]
    else:
        step(info["schedule_label"])
        st.caption("每一列請選日期（須在開始日期與結束日期之間；沒填的列會先用開始日期）。"
                   "只填了時間、內容還是空白的列也會保留。產出時依日期、時間排序。"
                   + ("" if info["schedule_required"] else
                      "活動類若名稱不含「研習」「環境教育」「訓練」（例如表揚），可以不填，系統就不會產出流程表附件。"))
        date_bounds = {}
        if d_start and d_end and d_end >= d_start:
            date_bounds = {"min_value": d_start, "max_value": d_end}
        courses_df = st.data_editor(
            st.session_state["plan_courses"], num_rows="dynamic", use_container_width=True,
            key=f"plan_course_editor_{ver}_{er}",
            column_config={
                "日期": st.column_config.DateColumn("日期", format="YYYY-MM-DD", **date_bounds),
                "時間": st.column_config.TextColumn("時間", help="例：09:10－12:00"),
            },
        )

    step("經費概算")
    st.markdown("**補助來源**（可多筆）")
    st.caption("類型選「議員」是議員建議、縣府補助；選「代表」是鄉鎮市公所代表建議、公所補助，並填公所名稱。"
               "姓名可填多位（用「、」分開，不必加職稱）。每筆各填金額，補助總額為各筆加總。")
    sources_df = st.data_editor(
        st.session_state["plan_sources"], num_rows="dynamic", use_container_width=True, key=f"plan_src_editor_{ver}_{er}",
        column_config={
            "類型": st.column_config.SelectboxColumn("類型", options=["議員", "代表"], required=True),
            "姓名": st.column_config.TextColumn("姓名", help="例：王、李（空白會填「ＯＯ議員」或「ＯＯ代表」）"),
            "公所": st.column_config.TextColumn("公所", help="代表才填，例：卑南鄉公所"),
            "金額": st.column_config.NumberColumn("金額（元）", step=1000, format="%d"),
        },
    )
    src_list = pg.normalize_sources(
        [{"kind": r.get("類型"), "names": r.get("姓名"), "township": r.get("公所"), "amount": r.get("金額")}
         for r in sources_df.to_dict("records")])
    subsidy = sum(sc["amount"] for sc in src_list)
    councilors = "、".join(sc["names"] for sc in src_list if sc["kind"] == "councilor" and sc["names"])
    st.metric("補助款合計（各補助來源加總）", f"{subsidy:,.0f} 元")
    st.markdown("**經費概算表（全部項目）**")
    st.caption("這張表是完整的概算表：所有品項（含自籌款支應的）都填在這裡。補助款只是依各項金額比例分配到各項，"
               "其餘為自籌款，分配結果在下方「補助款分配計算預覽」。"
               "二代健保補充保費，以及品項名稱含「油資」「過路費」「停車費」的項目，縣府不予補助，不分配補助款、全數自籌。"
               "備註欄只放「用途說明」，不顯示補助款或自籌款金額；"
               "便當、飲品、耗材的數量如果超過人數所需，請在用途說明寫明數量來源（例：學員 30 人＋工作人員 10 人，午餐及晚餐）。")
    item_rev = st.session_state.get("plan_item_rev", 0)
    base_items = st.session_state["plan_items"].copy()
    if "刪除" not in base_items.columns:
        base_items.insert(0, "刪除", False)
    items_df = st.data_editor(
        base_items, num_rows="dynamic", use_container_width=True, key=f"plan_item_editor_{ver}_{item_rev}_{er}",
        column_config={
            "刪除": st.column_config.CheckboxColumn("刪除", help="勾選後按下方「刪除勾選列」；勾選的列不計入下面的合計"),
            "類別": st.column_config.SelectboxColumn("類別", options=pg.ITEM_KINDS, required=True),
            "數量": st.column_config.NumberColumn("數量", step=1, format="%d"),
            "單價": st.column_config.NumberColumn("單價", step=10, format="%d"),
        },
    )
    marked = items_df["刪除"].fillna(False).astype(bool)
    items_df_eff = items_df[~marked]
    qty_s = pd.to_numeric(items_df_eff["數量"], errors="coerce").fillna(0)
    price_s = pd.to_numeric(items_df_eff["單價"], errors="coerce").fillna(0)
    grand_total = float((qty_s * price_s).sum())
    n_items = int(((qty_s * price_s) > 0).sum())
    sum_line = f"**概算總計：{grand_total:,.0f} 元**（{n_items} 項）｜補助款 {subsidy:,.0f} 元｜自籌款 {max(grand_total - subsidy, 0):,.0f} 元"
    if subsidy > grand_total + 0.5:
        st.error(sum_line + "　⚠️ 補助款大於概算總計，請調整")
    else:
        st.markdown(sum_line)

    ex_all = pg.item_examples(plan_type)
    ex_pick = st.multiselect(
        "加入整列範例（取自歷史案例，加入後可再修改品名、數量、單價）", list(range(len(ex_all))),
        format_func=lambda i: f"{ex_all[i]['name']}（{ex_all[i]['kind']}，{ex_all[i]['unit']}，單價 {ex_all[i]['price']:,}）",
        key=f"plan_ex_pick_{ver}_{item_rev}")
    ba, bb, _bc = st.columns([1.3, 1.3, 4])

    def _blank_free(df):
        name_ok = df["項目"].fillna("").astype(str).str.strip() != ""
        qty_ok = pd.to_numeric(df["數量"], errors="coerce").fillna(0) != 0
        return df[name_ok | qty_ok]

    if bb.button("🗑️ 刪除勾選列", use_container_width=True, disabled=not bool(marked.any()), key=f"plan_item_del_{ver}"):
        kept = _blank_free(items_df_eff).drop(columns=["刪除"])
        if kept.empty:
            kept = pd.DataFrame([{"項目": "", "類別": "設備購置" if is_equip else "一般", "數量": 0, "單位": "",
                                  "單價": 0, "用途說明": ""}])
        st.session_state["plan_items"] = kept.reset_index(drop=True)
        st.session_state["plan_item_rev"] = item_rev + 1
        st.rerun()
    if ba.button("➕ 加入範例列", use_container_width=True, disabled=not ex_pick, key=f"plan_item_add_{ver}"):
        added = pd.DataFrame([
            {"項目": ex_all[i]["name"], "類別": ex_all[i]["kind"], "數量": ex_all[i]["qty"], "單位": ex_all[i]["unit"],
             "單價": ex_all[i]["price"], "用途說明": ex_all[i]["use"]} for i in ex_pick])
        merged = pd.concat([_blank_free(items_df_eff).drop(columns=["刪除"]), added], ignore_index=True)
        st.session_state["plan_items"] = merged
        st.session_state["plan_item_rev"] = item_rev + 1
        st.rerun()
    st.caption("不需要的列：勾選最左邊的「刪除」後按「刪除勾選列」（也可選取整列按 Delete）。")

    step("進階內容與陳報單設定（選填）")
    is_activity = plan_type == "activity"
    expander_title = ("進階：自訂緣由（需求原因）與目的（都可留空，系統會用範本）" if is_equip
                      else "進階：自訂目的、活動內容、注意事項，與參加人員名冊（目的可留空，系統會用簡短範本）" if is_activity
                      else "進階：自訂緣由、目的、訓練方式、規定事項，與參訓名冊（都可留空，系統會用範本）")
    with st.expander(expander_title, expanded=is_activity and bool(st.session_state.get(f"plan_pu_{ver}"))):
        if is_activity:
            bg = ""
        elif is_equip:
            bg = st.text_area("緣由／需求原因（留空則自動產生；陳報單第一點會用到）", key=f"plan_bg_{ver}", height=90)
        else:
            bg = st.text_area("緣由（留空則自動產生）", key=f"plan_bg_{ver}", height=90)
        pu = st.text_area("目的（留空則自動產生）", key=f"plan_pu_{ver}", height=90)
        if is_equip:
            me = ru = ""
        elif is_activity:
            me = st.text_area("活動內容（每行一項，留空則不產出此章）", key=f"plan_me_{ver}", height=110)
            ru = st.text_area("注意事項（每行一項，留空則不產出此章；敘獎事項請勿寫進計畫書）", key=f"plan_ru_{ver}", height=110)
        else:
            me = st.text_area("訓練方式（留空則使用範本）", key=f"plan_me_{ver}", height=90)
            ru = st.text_area("規定事項（每行一項，留空則使用範本）", key=f"plan_ru_{ver}", height=110)
        if is_equip:
            roster_df = pd.DataFrame([{"單位": "", "職稱": "", "姓名": ""}])
        else:
            st.caption("參加人員名冊（選填；輸入後才會產出名冊附件。名冊含個資，僅在本頁暫時使用）" if is_activity
                       else "參訓名冊（選填；輸入後才會產出附件三。名冊含個資，僅在本頁暫時使用）")
            roster_df = st.data_editor(
                st.session_state.get("plan_roster_base", pd.DataFrame([{"單位": "", "職稱": "", "姓名": ""}])),
                num_rows="dynamic", use_container_width=True, key=f"plan_roster_{ver}_{er}")

    with st.expander("陳報單設定：獎懲（第四點）、敬會單位", expanded=True):
        st.caption("獎懲只寫在陳報單，不寫進計畫書。依「消防專業人員平時考核獎懲標準」："
                   "金額依爭取建議補助款總額度；天數依活動辦理時程及支援勤務天數。有獎懲時，敬會單位會自動加上人事室。")
        award_basis = st.radio("獎懲依據", list(pg.AWARD_BASES), format_func=lambda k: pg.AWARD_BASES[k],
                               horizontal=True, key=f"plan_award_basis_{ver}")
        award_box = st.container()
        if award_basis == "custom":
            awards_df = st.data_editor(
                st.session_state["plan_awards"], num_rows="dynamic", use_container_width=True,
                key=f"plan_award_editor_{ver}_{er}",
                column_config={
                    "種類": st.column_config.SelectboxColumn("種類", options=list(pg.AWARD_KINDS), required=True),
                    "人數": st.column_config.NumberColumn("人數", step=1, format="%d"),
                    "次數": st.column_config.NumberColumn("次數", step=1, format="%d"),
                },
            )
        else:
            awards_df = st.session_state["plan_awards"].iloc[0:0]
        meet = st.text_input("敬會單位（留空則依計畫類型自動帶入）", key=f"plan_meet_{ver}",
                             placeholder="例：災害搶救科、民力運用及訓練科、人事室、會計室")

    def _rows(df, mapping):
        out = []
        for r in df.to_dict("records"):
            out.append({k: r.get(v) for k, v in mapping.items()})
        return out

    items = pg.normalize_items(
        _rows(items_df_eff, {"name": "項目", "kind": "類別", "qty": "數量", "unit": "單位", "price": "單價",
                        "use": "用途說明"}),
        subsidy=float(subsidy), source_label=pg.PLAN_TYPES[plan_type]["source_label"], sources=src_list)
    courses = _rows(courses_df, {"date": "日期", "time": "時間", "content": "課程內容", "teacher": "教官／講師"})
    roster = _rows(roster_df, {"unit": "單位", "title": "職稱", "name": "姓名"})
    ctx = pg.PlanContext(
        plan_type=plan_type, unit=unit, year=int(year), name=name, start=d_start, end=d_end, place=place,
        audience=audience, headcount=int(headcount), method=me, instructors=instructors, co_organizer=co_org,
        supervisor=supervisor, councilors=councilors, subsidy=float(subsidy), items=items, courses=courses,
        roster=roster, background=bg, purpose=pu, rules=ru, sources=src_list,
        awards=[{"role": r.get("職務"), "count": r.get("人數"), "kind": r.get("種類"), "times": r.get("次數")}
                for r in awards_df.to_dict("records")],
        meet=meet, award_basis=award_basis,
        case_no=(st.session_state.get(f"plan_regd_{ver}") or {}).get("case_no", ""),
        org_battalion=acct.battalion if acct is not None else "",
        org_unit=acct.unit if (acct is not None and acct.role == "unit") else "")
    _snapshot_generator_state(ver, {
        "plan_items": items_df_eff.drop(columns=["刪除"], errors="ignore").reset_index(drop=True),
        "plan_sources": sources_df.reset_index(drop=True),
        "plan_courses": courses_df.reset_index(drop=True),
        "plan_awards": awards_df.reset_index(drop=True),
        "plan_roster_base": roster_df.reset_index(drop=True)})
    with award_box:
        _award = pg.award_text(ctx)
        if award_basis == "none":
            st.caption("不敘獎：陳報單不會有第四點。")
        elif _award:
            st.info("陳報單第四點會寫：\n\n" + "四、獎懲：" + _award.replace("\n", "  \n"))
        elif award_basis == "amount":
            st.caption("爭取建議補助款未達兩萬元，標準裡沒有對應的獎勵額度，陳報單不會有第四點。")
        elif award_basis == "days":
            st.caption("需要有活動開始、結束日期才能依天數計算（設備類沒有活動日期）。")
        else:
            st.caption("尚未輸入敘獎額度。")

    if items:
        st.markdown("**補助款分配計算預覽（唯讀）**")
        st.caption("依各項金額比例自動計算，不能手動修改。自籌款不會顯示負數。")
        alloc_rows = []
        for item in items:
            self_show = int(round(item["self"])) if item["self"] > 0 else 0
            alloc_rows.append({
                "項目": item["name"],
                "類別": item["kind"],
                "合計": int(round(item["total"])),
                "補助款支應": int(round(item["subsidy"])) if item["subsidy"] > 0 else 0,
                "自籌款": self_show,
                "備註": item["remark"],
            })
        st.dataframe(pd.DataFrame(alloc_rows), use_container_width=True, hide_index=True)

    st.markdown("---")
    step("規定檢查")
    if items:
        m1, m2, m3 = st.columns(3)
        m1.metric("總經費", f"{ctx.total:,.0f}")
        m2.metric("補助款", f"{ctx.subsidy:,.0f}", f"{ctx.subsidy / ctx.total:.1%}" if ctx.total else None, delta_color="off")
        if ctx.self_fund < -0.5:
            m3.metric("自籌款", "0", "補助超過總經費", delta_color="off")
        else:
            m3.metric("自籌款", f"{ctx.self_fund:,.0f}",
                      f"{ctx.self_fund / ctx.total:.1%}" if ctx.total else None, delta_color="off")

    findings = pg.check_plan(ctx)
    kind, banner = pg.compliance_banner(findings)
    errors = [f for f in findings if f.level == pg.ERROR]
    warns = [f for f in findings if f.level == pg.WARN]
    oks = [f for f in findings if f.level == pg.OK]
    if kind == "pass":
        st.success(banner, icon="✅")
    elif kind == "error":
        st.error(f"❌ {banner}")
        for f in errors:
            st.error(pg.format_compliance_item(f))
        if warns:
            st.markdown("**提醒（不阻擋匯出）**")
            for f in warns:
                st.warning(pg.format_compliance_item(f))
    else:
        st.warning(f"⚠️ {banner}")
        for f in warns:
            st.warning(pg.format_compliance_item(f))
    if oks:
        with st.expander(f"已通過的檢查（{len(oks)} 項）", expanded=(kind == "pass")):
            for f in oks:
                line = f"**{f.title}**" + (f"：{f.detail}" if f.detail else "")
                st.markdown(line)

    ready = bool(unit.strip() and name.strip() and items)
    can_register = ready and not errors
    if case_pages.is_enabled():
        if can_register:
            st.session_state["case_handoff"] = case_registry.draft_from_plan(ctx)
        else:
            st.session_state.pop("case_handoff", None)
    if not ready:
        st.info("請先填入申請單位、活動名稱與至少一個概算項目，才能產出草稿。")
        return
    if enabled:
        step("定稿並登錄案件，取得案號")
        draft = case_registry.draft_from_plan(ctx)
        sig = [str(draft[k]) for k in ("plan_name", "total", "applied", "source_detail", "date_start", "date_end")]
        regd = st.session_state.get(f"plan_regd_{ver}")
        if regd:
            st.success("✅ 已登錄到案件管制系統，大隊與業務科可以開始審核。")
            st.markdown(f'<div style="font-size:2rem; font-weight:800; color:#dc2626;">案件編號：{regd["case_no"]}</div>',
                        unsafe_allow_html=True)
            st.caption("請把案號寫在紙本計畫與陳報單上。下面下載的計畫書、概算表、陳報單，每頁右上角已自動印上案號。")
            if regd["sig"] != sig:
                st.warning("登錄之後您又修改了計畫名稱、金額、日期或補助來源，和已登錄的案件資料不一致。"
                           "案件管制系統裡的資料不會跟著改，請先確認是否要重新登錄或通知大隊。")
        elif acct is None or acct.role not in ("unit", "battalion"):
            st.caption("科室帳號不能登錄新案件，請用分隊或大隊帳號登入。")
        elif not can_register:
            st.info("規定檢查還有紅字錯誤，修正到沒有紅字之後，才能定稿登錄。")
        else:
            st.caption("檢查沒有錯誤了。確認內容無誤後定稿：系統會寫進案件管制、產生案件編號，之後大隊與業務科在系統上審核。"
                       "登錄後再修改的內容不會同步到管制系統，所以請先確認好再按。")
            officer = st.text_input("承辦人姓名 *", key=f"plan_officer_{ver}")
            if st.button("✅ 定稿並登錄案件", type="primary", key=f"plan_register_{ver}"):
                if not officer.strip():
                    st.error("請填寫承辦人姓名")
                else:
                    case_no, err = case_pages.submit_draft(acct, dict(draft, officer=officer.strip()))
                    if err:
                        st.error(err)
                    else:
                        st.session_state[f"plan_regd_{ver}"] = {"case_no": case_no, "sig": sig}
                        st.session_state.pop("case_handoff", None)
                        st.rerun()
    step("預覽與下載")
    with st.expander("展開計畫書預覽", expanded=True):
        st.markdown(pg.markdown_preview(ctx))
        if ctx.courses or plan_type == "training":
            st.markdown(f"**{info['schedule_label']}（依日期、時間排序）**")
            st.dataframe(pd.DataFrame([
                {"日期": pg.roc_date(c["date"]) if c.get("date") else "（未填）",
                 "時間": c.get("time", ""), "課程內容": c.get("content", ""), "教官／講師": c.get("teacher", "")}
                for c in ctx.courses
            ]), use_container_width=True, hide_index=True)
        st.markdown(f"**{pg.budget_title(ctx)}**")
        st.dataframe(pd.DataFrame([
            {"項次": n + 1, "項目": i["name"], "數量": i["qty"], "單位": i["unit"], "單價": i["price"],
             "合計": i["total"], "補助款支應": int(round(i["subsidy"])) if i["subsidy"] > 0 else 0,
             "自籌款": int(round(i["self"])) if i["self"] > 0 else 0, "備註": i["remark"]}
            for n, i in enumerate(items)
        ]), use_container_width=True, hide_index=True)
        st.caption(pg.budget_note(ctx))
    with st.expander("展開陳報單預覽（送計畫時附上）", expanded=False):
        st.markdown(pg.submission_markdown(ctx))
        st.caption("活動、訓練、設備的陳報單句型相同，只有計畫名稱與檢陳文件不同。日期、字號請自行填寫。"
                   + pg.issuing_note(ctx)
                   + ("設備類須附廠商估價單與縣政府設備類審核表；核銷時另附財產增加單。" if is_equip else ""))
    base = f"{ctx.year}年{ctx.unit.strip()}{ctx.name_for_title}"
    d1_, d2_, d3_ = st.columns(3)
    d1_.download_button("📄 下載計畫書（Word）", data=pg.build_docx(ctx), file_name=f"{base}計畫書草稿.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True, type="primary")
    d2_.download_button("📊 下載概算表（Excel）", data=pg.build_xlsx(ctx), file_name=f"{base}概算表草稿.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True)
    d3_.download_button("📝 下載陳報單（Word）", data=pg.build_submission_docx(ctx), file_name=f"{base}陳報單草稿.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True)
    st.caption("草稿依固定範本產生，送審前請承辦人逐項確認內容、數字與核章；檢查結果僅供提醒，最終以縣府及局內審查為準。")


def _load_generator_manual():
    """讀 docs/計畫書產生器操作說明.md，依「## 」切成 (簡介, [(章節標題, 內容)])。讀不到就回傳 None。"""
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "計畫書產生器操作說明.md")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    parts = re.split(r"(?m)^## ", text)
    intro = re.sub(r"(?m)^# .*\n", "", parts[0]).replace("---", "").strip()
    sections = []
    for block in parts[1:]:
        title, _, body = block.partition("\n")
        sections.append((title.strip(), re.sub(r"(?m)^---\s*$", "", body).strip()))
    return intro, sections


def render_generator_manual():
    """操作說明：計畫書產生器怎麼用，附完整範例（內容在 docs 資料夾，可直接改檔）。"""
    manual = _load_generator_manual()
    if not manual:
        return
    intro, sections = manual
    st.markdown("#### 📖 計畫書產生器操作說明")
    st.caption("第一次使用請先看「二、最快的做法」與兩個完整範例；點章節標題展開。")
    if intro:
        st.markdown(intro)
    for title, body in sections:
        with st.expander(title):
            st.markdown(body)


def render_subsidy_guide():
    """🏠 補捐助專區使用導覽：依「我現在要做什麼」帶同仁走到正確的頁面。"""
    def _go_to_tab(tab_label):
        st.session_state["top_main_nav"] = tab_label

    st.markdown("""
    <div style="background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); border-radius: 12px; padding: 1.4rem 1.6rem; margin-bottom: 1.2rem; color: #fff;">
        <h2 style="margin:0 0 0.4rem 0; color:#fff; font-size:1.5rem;">👋 歡迎使用補捐助案件專區</h2>
        <p style="margin:0; font-size:1rem; color:#dbeafe;">
            這裡整理了義消向縣府及各鄉鎮公所申請補（捐）助、辦理核銷所需的流程、規定、案例與小工具。
            不知道從哪裡開始？先選下面三種情況之一，照步驟走就對了。
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### 🧭 你現在要做什麼？")
    _GUIDE_STEP_H = 240
    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.markdown("##### 🆕 我要申請補捐助")
            with st.container(height=_GUIDE_STEP_H, border=False):
              st.markdown(
                "1. 先看**申請流程**，了解誰要做什麼、送到哪裡\n"
                "2. 對照**申請注意要點**，確認經費比例與用字\n"
                "3. 用**計畫書產生器**做出計畫書與概算表草稿\n"
                "4. 完成**線上登錄**後，依流程送大隊"
            )
            st.button("➡️ 從申請流程開始", on_click=_go_to_tab, args=("🧭 申請與核銷流程",),
                      use_container_width=True, key="guide_apply_flow", type="primary")
            st.button("✏️ 直接產生計畫書", on_click=_go_to_tab, args=("✏️ 計畫書產生器",),
                      use_container_width=True, key="guide_apply_gen")
    with c2:
        with st.container(border=True):
            st.markdown("##### 🧾 我要辦理核銷")
            with st.container(height=_GUIDE_STEP_H, border=False):
              st.markdown(
                "1. 先看**核銷流程**與陳報單範例句\n"
                "2. 對照**核銷注意要點**備齊單據與附件\n"
                "3. 用**核銷自我檢核**檢查金額與文件\n"
                "4. 確認無誤後送大隊初審"
            )
            st.button("➡️ 開始核銷自我檢核", on_click=_go_to_tab, args=("✅ 核銷自我檢核",),
                      use_container_width=True, key="guide_settle_check", type="primary")
            st.button("📌 查核銷注意要點", on_click=_go_to_tab, args=("📌 申請注意要點",),
                      use_container_width=True, key="guide_settle_notes")
    with c3:
        with st.container(border=True):
            st.markdown("##### 🔍 避免被退件")
            with st.container(height=_GUIDE_STEP_H, border=False):
              st.markdown(
                "1. 看**錯誤樣態案例**，了解常見退件原因\n"
                "2. 對照自己的計畫書與概算表是否有同樣問題\n"
                "3. 送件前再用**自我檢核**工具確認一次"
            )
            st.button("➡️ 看錯誤樣態案例", on_click=_go_to_tab, args=("⚠️ 錯誤樣態案例",),
                      use_container_width=True, key="guide_cases", type="primary")
            st.button("📌 看申請注意要點", on_click=_go_to_tab, args=("📌 申請注意要點",),
                      use_container_width=True, key="guide_notes")

    st.markdown("#### 🗂️ 各頁面功能一覽")
    pages = [
        ("🧭 申請與核銷流程", "🧭 申請與核銷流程", "完整的申請、核銷流程，分隊／大隊／科室各步驟做什麼，附陳報單範例句與常見問答。"),
        ("📌 申請注意要點", "📌 申請注意要點", "活動費、設備費、共通與核銷的規定：用字、自籌款、餐費比例、單據與附件。"),
        ("⚠️ 錯誤樣態案例", "⚠️ 錯誤樣態案例", "過去常見的退件與缺失，含錯誤說明、造成的問題與正確做法。"),
        ("✏️ 計畫書產生器", "✏️ 計畫書產生器", "選計畫類型、填必要資料，產出計畫書（Word）、概算表（Excel）與陳報單（Word）草稿，並先檢查規定。"),
        ("✅ 核銷自我檢核", "✅ 核銷自我檢核", "送大隊初審前，自行檢查收支清單金額與核銷文件是否備齊。"),
    ]
    for label, target, desc in pages:
        cb, cd = st.columns([1.3, 4])
        with cb:
            st.button(label, on_click=_go_to_tab, args=(target,), use_container_width=True, key=f"guide_pg_{target}")
        with cd:
            st.markdown(f"<div style='padding-top:0.35rem; color:#475569;'>{html.escape(desc)}</div>", unsafe_allow_html=True)

    render_generator_manual()

    st.markdown("#### 🔢 先記住這幾個數字")
    chips = "".join(
        f'<div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:0.7rem 0.9rem;">'
        f'<div style="font-size:1.5rem; font-weight:800; color:#1d4ed8;">{html.escape(n)}</div>'
        f'<div style="font-size:0.85rem; color:#475569;">{html.escape(d)}</div></div>'
        for n, d in sc.QUICK_NUMBERS[:6]
    )
    st.markdown(f'<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:0.6rem; margin-bottom:1rem;">{chips}</div>', unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("##### ⚠️ 陳報前必做：線上登錄案件基本資訊")
        st.markdown("申請單位（分隊／大隊）陳報案件時須先完成線上登錄，**未完成登錄的案件，大隊初審會直接退件**，業務科室也會暫緩發文。")
        st.link_button("📝 前往線上登錄", sc.ONLINE_REGISTER_URL)

    st.caption("👤 **科內承辦人**：廖昱翔科員、林威宇小隊長　｜　輸入計畫書產生器、核銷自我檢核的資料只在網頁暫時計算，不會儲存或上傳。")


def render_subsidy_business_tab():
    """💰 補捐助業務頁面（主網站與補捐助專區共用）：使用導覽＋流程總覽。"""
    render_subsidy_guide()

    st.markdown("---")
    st.markdown("#### 📣 流程總覽與最新提醒")
    render_subsidy_banner()

    if st.session_state.get("is_admin"):
        st.markdown("---")
        with st.expander("🛠️ 承辦人維護：列管業務卡片與專區網址", expanded=False):
            tasks_cat = db.get_tasks_by_filter(category="補捐助業務")
            st.write(f"本分類共有 **{len(tasks_cat)}** 項列管業務：")
            for t in tasks_cat:
                render_task_card(t)
            st.caption("📎 **補捐助專區獨立網址**（只顯示導覽、流程、注意要點、錯誤樣態案例與兩個小工具，可直接轉給只需查看補捐助的同仁；僅承辦人維護模式看得到這段說明）：")
            st.code(SUBSIDY_VIEW_URL, language=None)


SUBSIDY_VIEW_URL = "https://civilianforcedashboard.streamlit.app/?view=subsidy"
SUBSIDY_VIEW_TABS = ["🏠 使用導覽", "🧭 申請與核銷流程", "📌 申請注意要點", "⚠️ 錯誤樣態案例", "✏️ 計畫書產生器", "✅ 核銷自我檢核"]
CASE_TAB = "📮 案件登錄"   # 只有 Secrets 有 case_registry 設定時才出現


def render_subsidy_view():
    """補捐助專區（獨立網址 ?view=subsidy）：只顯示補捐助相關三個頁面。

    沒有側邊欄、KPI、其他業務分頁與維護模式，資料和主網站共用同一份。
    這是給同仁方便查閱的精簡檢視，不是權限控管；維護請從主網址登入維護模式。
    """
    st.session_state["is_admin"] = False
    st.markdown("""
    <div class="main-header">
        <h1>💰 臺東縣消防局民力運用及訓練科 — 補捐助案件專區</h1>
        <p>義消申請補縣府及各鄉鎮公所補捐助案件 | 業務 SOP • 申請案件注意要點 • 錯誤樣態歷史案例 • 計畫書產生器 • 核銷自我檢核</p>
    </div>
    """, unsafe_allow_html=True)

    tabs = SUBSIDY_VIEW_TABS + ([CASE_TAB] if case_pages.is_enabled() else [])
    if st.session_state.get("top_main_nav") not in tabs:
        st.session_state["top_main_nav"] = tabs[0]
    selected = st.radio("專區導覽", tabs, horizontal=True,
                        label_visibility="collapsed", key="top_main_nav")

    if selected == "🧭 申請與核銷流程":
        render_subsidy_process_page()
    elif selected == "📌 申請注意要點":
        render_application_notes_page()
    elif selected == "⚠️ 錯誤樣態案例":
        render_error_cases_page()
    elif selected == "✏️ 計畫書產生器":
        render_plan_generator_page()
    elif selected == "✅ 核銷自我檢核":
        render_settlement_check_page()
    elif selected == CASE_TAB:
        case_pages.render_case_registry_page(load_plan_generator())
    else:
        render_subsidy_business_tab()

    st.caption("資料與「業務知識動態看板」主網站同步更新，內容由臺東縣消防局民力運用及訓練科維護。")


# ==================== 補捐助專區（獨立網址）====================
# 網址後面加上 ?view=subsidy 時，只顯示補捐助相關三個頁面，其餘內容（側邊欄、KPI、其他業務、維護模式）都不顯示。
if st.query_params.get("view", "") == "subsidy":
    render_subsidy_view()
    st.stop()

# 系統頂部橫幅
st.markdown("""
<div class="main-header">
    <div style="display: flex; align-items: center; justify-content: space-between;">
        <div>
            <h1>🚒 臺東縣消防局民力運用及訓練科 — 業務知識動態看板</h1>
            <p>Taitung County Fire Bureau - Civilian & Volunteer Force Training Division | 專業義消承辦人導引 • 承辦人業務即選直達 • 我有話要說雙向回饋</p>
        </div>
        <div style="text-align: right; font-size: 0.85rem; opacity: 0.9;">
            📅 資料庫狀態：<strong>已連線</strong><br>
            🏢 臺東縣消防局 民力運用及訓練科
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


def jump_to_task_view(target_category, target_title):
    """跨頁跳轉直達指定業務並自動定位展開 SOP"""
    tab_name = CATEGORY_ICON_MAP.get(target_category.strip(), (target_category.strip(), "📄"))[0]
    st.session_state["top_main_nav"] = tab_name
    st.session_state["active_tab"] = tab_name
    st.session_state["target_task_title"] = target_title
    set_flash_message(f"🚀 已切換至【{tab_name}】並為您定位展開【{target_title}】！", icon="🎯")
    st.rerun()


# 側邊欄設計 (★ 依承辦人即時列出業務並支援點擊直達切換頁面)
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/fire-truck.png", width=60)
    st.title("民力看板控制台")
    st.caption("🏢 臺東縣消防局 民力運用及訓練科")
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
                jump_to_task_view(ot["category"], ot["title"])

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
                    jump_to_task_view(s_task["category"], s_task["title"])

    st.markdown("---")

    # 3. 科內維護模式（管理員登入）
    st.subheader("🔐 科內維護模式")
    if not st.session_state["is_admin"]:
        try:
            _using_default_pw = not st.secrets.get("admin_password")
        except Exception:
            _using_default_pw = True
        if _using_default_pw:
            st.caption("⚠️ 尚未於 Streamlit Cloud 設定自訂管理密碼，目前為預設密碼，建議盡快至 App → Settings → Secrets 新增 `admin_password` 設定值。")
        admin_pass = st.text_input("請輸入管理密碼", type="password", help="尚未設定自訂密碼前，預設科內維護密碼為：119")
        if st.button("🔓 啟用線上維護模式", use_container_width=True):
            if admin_pass and admin_pass in get_valid_admin_passwords():
                st.session_state["is_admin"] = True
                st.session_state["top_main_nav"] = "⚙️ 科內線上維護 (Excel介面)"
                st.session_state["active_tab"] = "⚙️ 科內線上維護 (Excel介面)"
                set_flash_message("✅ 已切換至科內維護模式！已為您自動開啟【⚙️ 科內線上維護】分頁。", icon="🔓")
                st.rerun()
            else:
                st.error("❌ 密碼錯誤，請洽民力運用及訓練科系統管理員。")
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



# ==================== 📋 民力科近期交辦協助事項 (公告欄) ====================
assigned_items = db.get_all_assigned_tasks() if hasattr(db, "get_all_assigned_tasks") else []
pending_items = [t for t in assigned_items if not t["is_done"]]
done_items = [t for t in assigned_items if t["is_done"]]

if assigned_items:
    st.markdown("""
    <div style="background: linear-gradient(to right, #f0f9ff, #e0f2fe); border: 1px solid #bae6fd; border-left: 6px solid #0284c7; border-radius: 10px; padding: 0.8rem 1.3rem; margin-bottom: 0.5rem;">
        <span style="font-size: 1.1rem; font-weight: 700; color: #0c4a6e;">📋 民力科近期交辦協助事項</span>
        <span style="font-size: 0.82rem; color: #0369a1; margin-left: 0.8rem;">各外勤大隊、分隊請依下列項目確認辦理並於期限前回覆</span>
    </div>
    """, unsafe_allow_html=True)

    if pending_items:
        for at in pending_items:
            dl_badge = ""
            if at.get("deadline_note") and at["deadline_note"].strip():
                dl_badge = f'<span style="background:#fef3c7; color:#92400e; font-size:0.8rem; font-weight:700; padding:2px 8px; border-radius:4px; margin-left:0.6rem; border:1px solid #fde68a;">⏰ {at["deadline_note"]}</span>'
            st.markdown(f"""
            <div style="display:flex; align-items:center; padding: 0.55rem 1rem; margin-bottom:0.3rem; background:#fff; border:1px solid #e0f2fe; border-radius:7px; border-left:4px solid #0284c7;">
                <span style="font-size:1.1rem; margin-right:0.5rem;">🔵</span>
                <span style="font-size:0.97rem; color:#1e293b; font-weight:600; flex:1;">{at["item_content"]}</span>
                {dl_badge}
            </div>
            """, unsafe_allow_html=True)
    
    if done_items:
        with st.expander(f"✅ 已完成項目（{len(done_items)} 項）", expanded=False):
            for at in done_items:
                st.markdown(f"""
                <div style="display:flex; align-items:center; padding:0.45rem 1rem; margin-bottom:0.25rem; background:#f8fafc; border:1px solid #e2e8f0; border-radius:7px; opacity:0.65;">
                    <span style="font-size:1rem; margin-right:0.5rem;">✅</span>
                    <span style="font-size:0.92rem; color:#64748b; text-decoration:line-through; flex:1;">{at["item_content"]}</span>
                    <span style="font-size:0.8rem; color:#94a3b8; margin-left:0.5rem;">{at.get("deadline_note", "")}</span>
                </div>
                """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)


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

# ==================== 📢 最新業務異動與宣導重點 (Top 3 即時快訊專區) ====================
top_highlights = get_top_latest_highlights_safe(limit=3)

if top_highlights:
    st.markdown("""
    <div style="background: linear-gradient(to right, #fff1f2, #fff7ed); border: 1px solid #fecdd3; border-left: 6px solid #e11d48; border-radius: 10px; padding: 0.9rem 1.3rem; margin-bottom: 1.2rem; box-shadow: 0 2px 6px rgba(225, 29, 72, 0.06);">
        <div style="display: flex; align-items: center; justify-content: space-between;">
            <div>
                <span style="font-size: 1.15rem; font-weight: 700; color: #9f1239;">📢 民力運用及訓練科 — 最新業務異動與宣導重點 (Top 3 即時快訊)</span>
                <span style="font-size: 0.85rem; color: #be123c; margin-left: 0.6rem;">外勤大隊與分隊同仁請特別留意以下最新重要期程與規定：</span>
            </div>
            <span style="background: #ffe4e6; color: #9f1239; font-size: 0.78rem; font-weight: 700; padding: 2px 8px; border-radius: 9999px; border: 1px solid #fecdd3;">即時同步中</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    cols_hl = st.columns(len(top_highlights))
    for idx, (col_h, hl_item) in enumerate(zip(cols_hl, top_highlights)):
        with col_h:
            target_tab_name = CATEGORY_ICON_MAP.get(hl_item["category"], (hl_item["category"], "📄"))[0]
            cat_icon = CATEGORY_ICON_MAP.get(hl_item["category"], ("", "📄"))[1]
            
            st.markdown(f"""
            <div style="background: #ffffff; border: 1px solid #fed7aa; border-radius: 8px; padding: 0.9rem 1rem; height: 100%; box-shadow: 0 2px 4px rgba(0,0,0,0.03); border-top: 4px solid #f97316;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom: 0.3rem;">
                    <span style="background:#ffedd5; color:#9a3412; font-size:0.75rem; font-weight:700; padding:2px 6px; border-radius:4px;">{cat_icon} {hl_item['category']}</span>
                    <span style="font-size:0.78rem; color:#94a3b8;">🕒 {hl_item['last_updated'][:10] if hl_item.get('last_updated') else ''}</span>
                </div>
                <div style="font-size: 1rem; font-weight: 700; color: #1e293b; margin: 0.4rem 0 0.3rem 0; line-height: 1.3;">
                    {hl_item['title']}
                </div>
                <div style="font-size: 0.82rem; color: #64748b; margin-bottom: 0.5rem;">
                    👤 承辦人：<strong style="color:#0f172a;">{hl_item['owner'] or '未指派'}</strong>
                </div>
                <div style="background: #fff5f5; border: 1px dashed #fca5a5; border-radius: 6px; padding: 0.5rem 0.7rem; font-size: 0.88rem; color: #b91c1c; font-weight: 600; line-height: 1.4; margin-bottom: 0.6rem;">
                    {hl_item['update_highlight']}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"🚀 點擊直達【{hl_item['title']}】", key=f"btn_hl_jump_{hl_item['id']}", use_container_width=True):
                jump_to_task_view(hl_item["category"], hl_item["title"])
                
    st.markdown("<br>", unsafe_allow_html=True)



# ==================== 頂部主導覽標籤列 (支援程式化切換與點選) ====================
tab_names = [
    "🎖️ 專業義消承辦人",
    "🚒 義消業務",
    "🎁 義消福利",
    "💰 補捐助業務",
    "🧭 申請與核銷流程",
    "📌 申請注意要點",
    "⚠️ 錯誤樣態案例",
    "✏️ 計畫書產生器",
    "✅ 核銷自我檢核",
    "🎯 訓練業務",
    "🌟 其他推動業務",
    "💬 我有話要說"
]

if st.session_state["is_admin"]:
    tab_names.append("⚙️ 科內線上維護 (Excel介面)")

if "top_main_nav" not in st.session_state or st.session_state["top_main_nav"] not in tab_names:
    st.session_state["top_main_nav"] = st.session_state.get("active_tab", tab_names[0])
    if st.session_state["top_main_nav"] not in tab_names:
        st.session_state["top_main_nav"] = tab_names[0]

selected_tab = st.radio(
    "主頁導覽",
    tab_names,
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
                        st.markdown(format_sop_content_smart(mt["content_detail"]))
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
    render_subsidy_business_tab()

# === 4-0. 申請與核銷流程 Tab ===
elif selected_tab == "🧭 申請與核銷流程":
    render_subsidy_process_page()


# === 4-1. 申請注意要點 Tab ===
elif selected_tab == "📌 申請注意要點":
    render_application_notes_page()


# === 4-2. 錯誤樣態案例 Tab ===
elif selected_tab == "⚠️ 錯誤樣態案例":
    render_error_cases_page()


# === 4-2b. 計畫書產生器 Tab ===
elif selected_tab == "✏️ 計畫書產生器":
    render_plan_generator_page()


# === 4-3. 核銷自我檢核 Tab ===
elif selected_tab == "✅ 核銷自我檢核":
    render_settlement_check_page()


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
    st.caption("👤 **科內承辦人**：民力運用及訓練科全體同仁")
    
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
            開放臺東大隊、關山大隊、成功大隊、大武大隊各分隊義消承辦人及全體同仁提出實務執行問題、法規諮詢、作業建議或系統回饋。民力運用及訓練科將定期彙整、專人查明並公開回覆！
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
                    set_flash_message(f"🎉 成功送出意見！留言編號 #{new_fb_id}【{fb_unit}】，民力運用及訓練科將盡速查明查覆。", icon="💌")
                    st.rerun()

    # 右側：問題與民力運用及訓練科回覆列表
    with col_fb_list:
        st.markdown("#### 📢 同仁意見與民力運用及訓練科官方回覆看板")
        
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

                # 使用者自填欄位（單位/類別為下拉選單可信任，但姓名、內容、回覆為自由輸入文字，
                # 必須先跳脫 HTML 特殊字元再塞入頁面，避免被拿來注入 <script> 等惡意內容 (XSS)）
                safe_submitter = html.escape(fb['submitter']) if fb['submitter'] else ''
                safe_content = html.escape(fb['content'] or '').replace('\n', '<br>')
                safe_admin_reply = html.escape(fb['admin_reply'] or '').replace('\n', '<br>')

                st.markdown(f"""
                <div class="feedback-card">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
                        <div>
                            <span style="background:#ede9fe; color:#5b21b6; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.8rem;">{fb['category']}</span>
                            <strong style="margin-left:0.5rem; font-size:1rem; color:#1e293b;">🏢 {fb['unit_name']}</strong>
                            <span style="color:#64748b; font-size:0.85rem; margin-left:0.4rem;">({safe_submitter or '熱心同仁'})</span>
                        </div>
                        <div>
                            <span style="background:{bg_c}; color:{text_c}; padding:2px 8px; border-radius:9999px; font-size:0.78rem; font-weight:700;">{status_txt}</span>
                        </div>
                    </div>
                    <div style="font-size:0.95rem; color:#334155; line-height:1.5; margin-bottom:0.4rem;">
                        💬 <strong>反映內容</strong>：{safe_content}
                    </div>
                    <div style="font-size:0.8rem; color:#94a3b8; text-align:right;">
                        🕒 提報時間：{fb['created_at']}
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if fb["admin_reply"] and fb["admin_reply"].strip():
                    st.markdown(f"""
                    <div class="feedback-reply-box" style="margin-top:-0.6rem; margin-bottom:1.2rem;">
                        <strong>📢 民力運用及訓練科回覆 ({fb['replied_at'] or ''})：</strong><br>
                        {safe_admin_reply}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div style="font-size:0.85rem; color:#94a3b8; margin-top:-0.4rem; margin-bottom:1.2rem; padding-left:0.5rem;">
                        ⏳ <em>民力運用及訓練科正查明處理中，請稍候回覆...</em>
                    </div>
                    """, unsafe_allow_html=True)


# === 8. 科內維護模式 Tab (若已登入) ===
elif selected_tab == "⚙️ 科內線上維護 (Excel介面)":
    st.markdown("### ⚙️ 科內承辦人線上快速維護介面")
    st.info("💡 承辦人可直接在此處編輯各業務內容（自動連動首頁導航）、線上修改「專業義消承辦人」四大情境說明，或管理/回覆/刪除「我有話要說」同仁留言。所有儲存操作均具備明確完成提示。")

    # ⚠️ 這裡改用 session_state 綁定的 st.radio 而非 st.tabs：
    # st.tabs 沒有 key 參數、選中的分頁不會保存在 session_state，只要頁面因為任何其他元件
    # （例如子分頁6「勾選確認還原」的 checkbox）觸發 rerun，畫面就會被重置跳回第一個分頁，
    # 使用者會覺得「勾選後就跳出去了」。改用 st.radio(key=...) 才能讓選到的子分頁在 rerun 後維持不變。
    maintenance_subtabs = [
        "📋 Excel 式線上即時編輯",
        "🎖️ 專業義消承辦人 - 導引維護",
        "💬 我有話要說 - 線上回覆與留言管理",
        "➕ 新增業務項目",
        "✏️ 單筆詳細維護 / 刪除",
        "💾 資料庫備份、還原與重設",
        "📋 交辦協助事項管理"
    ]
    if "maintenance_subtab" not in st.session_state or st.session_state["maintenance_subtab"] not in maintenance_subtabs:
        st.session_state["maintenance_subtab"] = maintenance_subtabs[0]
    selected_subtab = st.radio(
        "維護子分頁",
        maintenance_subtabs,
        key="maintenance_subtab",
        horizontal=True,
        label_visibility="collapsed"
    )

    # 子分頁 1: st.data_editor 批次編輯
    if selected_subtab == maintenance_subtabs[0]:
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
    elif selected_subtab == maintenance_subtabs[1]:
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
    elif selected_subtab == maintenance_subtabs[2]:
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

            # 同上：提報人自由輸入欄位先跳脫 HTML，避免管理者查看留言時觸發 XSS
            safe_cur_submitter = html.escape(cur_fb['submitter']) if cur_fb['submitter'] else ''
            safe_cur_contact = html.escape(cur_fb['contact_info']) if cur_fb['contact_info'] else '無'
            safe_cur_content = html.escape(cur_fb['content'] or '').replace('\n', '<br>')

            st.markdown(f"""
            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:1rem; margin-bottom:1rem;">
                <strong>留言編號</strong>：ID #{cur_fb['id']}<br>
                <strong>提報單位</strong>：{cur_fb['unit_name']} ({safe_cur_submitter})<br>
                <strong>業務類別</strong>：{cur_fb['category']}<br>
                <strong>聯絡方式</strong>：{safe_cur_contact}<br>
                <strong>反映時間</strong>：{cur_fb['created_at']}<br>
                <div style="margin-top:0.5rem; color:#1e293b;">
                    <strong>💬 反映內容</strong>：{safe_cur_content}
                </div>
            </div>
            """, unsafe_allow_html=True)

            with st.form(f"reply_fb_form_{sel_fb_id}"):
                curr_status_idx = db.FEEDBACK_STATUSES.index(cur_fb["status"]) if cur_fb["status"] in db.FEEDBACK_STATUSES else 0
                reply_status = st.selectbox("處理狀態", db.FEEDBACK_STATUSES, index=curr_status_idx, key=f"fb_status_{sel_fb_id}")
                reply_content = st.text_area("民力運用及訓練科官方回覆內容 (將公開於看板供同仁查閱)", value=cur_fb["admin_reply"] or "", height=140, key=f"fb_reply_{sel_fb_id}")
                
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
    elif selected_subtab == maintenance_subtabs[3]:
        st.markdown("#### ➕ 新增業務項目表單")
        st.caption("承辦人可直接使用下拉選單快速指派，並支援加入 Google 雲端硬碟附件下載連結與流程圖檔。")
        
        with st.form("add_task_form", clear_on_submit=True):
            col_a, col_b, col_c = st.columns([2, 2, 2])
            with col_a:
                new_category = st.selectbox("業務分類 *", db.CATEGORIES)
            with col_b:
                new_subcategory = st.text_input("子項目 (例：專長資料庫、保險互助、業務評核)")
            with col_c:
                officer_opts = getattr(db, "DEFAULT_OFFICERS", ["廖昱翔科員、林威宇小隊長", "廖昱翔科員", "林威宇小隊長", "陳怡忻分隊長", "尤仁宏秘書", "民力訓練科全體同仁"]) + ["➕ 自訂其他承辦人..."]
                sel_owner_pick = st.selectbox("科內承辦人 (下拉選擇) *", officer_opts, index=0)

            col_custom_owner = st.container()
            new_owner_custom = ""
            if sel_owner_pick == "➕ 自訂其他承辦人...":
                new_owner_custom = st.text_input("請輸入自訂承辦人姓名/職稱", placeholder="例：林分隊長、王科員")

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
                height=180
            )

            st.markdown("##### 📎 業務附件、申請表單下載與流程圖檔連結")
            st.caption("💡 **雲端永久保存指南**：將公文 PDF、申請表 Word 或 SOP 流程圖上傳至 **Google 雲端硬碟**（共用權限設為「知道連結者可檢視」），並將分享連結貼在下方：\n- 📥 **表單/公文下載**：例如 `申請表單下載: https://drive.google.com/file/d/.../view`\n- 🖼️ **流程圖/示意圖**：例如 `業務作業流程圖: https://drive.google.com/file/d/.../view`")
            
            new_doc_links = st.text_area(
                "表單下載 / 流程圖檔 / 雲端硬碟連結 (每行一筆)",
                placeholder="申請表單下載: https://drive.google.com/file/d/...\n作業流程圖: https://drive.google.com/file/d/...\n系統入口: https://reurl.cc/...",
                height=90
            )

            submitted = st.form_submit_button("🚀 確認新增並儲存至資料庫", type="primary")
            if submitted:
                final_owner = new_owner_custom.strip() if sel_owner_pick == "➕ 自訂其他承辦人..." else sel_owner_pick
                if not new_title.strip():
                    st.error("請輸入「業務項目名稱」！")
                else:
                    new_id = db.add_task(
                        new_category,
                        new_subcategory.strip(),
                        new_title.strip(),
                        final_owner,
                        new_status,
                        new_highlight.strip(),
                        new_content.strip(),
                        new_doc_links.strip()
                    )
                    set_flash_message(f"🎉 成功新增業務項目！編號：ID #{new_id}【{new_title}】已寫入資料庫並於前台發布。", icon="🎉")
                    st.rerun()

    # 子分頁 5: 單筆詳細編輯與刪除
    elif selected_subtab == maintenance_subtabs[4]:
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
                        cur_own_val = current_item["owner"] or ""
                        default_officers = getattr(db, "DEFAULT_OFFICERS", ["廖昱翔科員、林威宇小隊長", "廖昱翔科員", "林威宇小隊長", "陳怡忻分隊長", "尤仁宏秘書", "民力訓練科全體同仁"])
                        all_officer_choices = list(dict.fromkeys(default_officers + ([cur_own_val] if cur_own_val else []) + ["➕ 自訂其他承辦人..."]))
                        
                        own_idx = all_officer_choices.index(cur_own_val) if cur_own_val in all_officer_choices else 0
                        edit_owner_sel = st.selectbox("承辦人 (下拉選單) *", all_officer_choices, index=own_idx, key=f"edit_owner_sel_{selected_id}")

                    custom_owner_input = ""
                    if edit_owner_sel == "➕ 自訂其他承辦人...":
                        custom_owner_input = st.text_input("請輸入自訂承辦人姓名/職稱", value=cur_own_val, key=f"edit_owner_cust_{selected_id}")

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
                        height=200,
                        key=f"edit_content_{selected_id}"
                    )

                    st.markdown("##### 📎 業務附件、表單下載按鈕與流程圖檔連結")
                    st.caption("💡 **雲端永久保存指南**：將公文 PDF、申請表 Word 或 SOP 流程圖上傳至 **Google 雲端硬碟**（設為知道連結者可檢視），並將分享連結貼在下方：\n- 📥 **表單/公文下載**：例如 `申請表單下載: https://drive.google.com/file/d/.../view`\n- 🖼️ **流程圖/示意圖**：例如 `業務作業流程圖: https://drive.google.com/file/d/.../view`")
                    
                    edit_doc_links = st.text_area(
                        "相關表單與雲端連結 (每行一筆)",
                        value=current_item["doc_links"] or "",
                        height=90,
                        key=f"edit_links_{selected_id}"
                    )

                    save_btn = st.form_submit_button("💾 儲存此項目更新", type="primary", use_container_width=True)

                    if save_btn:
                        final_edit_owner = custom_owner_input.strip() if edit_owner_sel == "➕ 自訂其他承辦人..." else edit_owner_sel
                        db.update_single_task(
                            selected_id,
                            edit_category,
                            edit_subcategory.strip(),
                            edit_title.strip(),
                            final_edit_owner,
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

    # 子分頁 6: 資料庫備份、雲端同步與還原
    elif selected_subtab == maintenance_subtabs[5]:
        st.markdown("#### 💾 資料庫備份、GitHub 雲端同步與還原")

        # 區塊 0: GitHub 雲端一鍵備份與還原
        st.markdown("##### ☁️ 0. GitHub 雲端一鍵備份與還原")
        st.caption("將全系統資料（業務、情境、留言、交辦事項、申請注意要點、錯誤樣態案例）推送至 GitHub 倉庫作為永久雲端備份。伺服器重啟後會**自動從雲端還原**。**新增或修改資料後，記得按一次「一鍵上傳至雲端備份」，資料才不會在重啟後遺失。**")

        GITHUB_OWNER = "jerrylin119-maker"
        GITHUB_REPO = "civilian_force_dashboard"

        # 從 GitHub 直接讀取備份資訊（不依賴 SQLite，重啟也不失效）
        if "cloud_backup_info" not in st.session_state:
            try:
                _ok, _bobj, _err = db.fetch_backup_public(GITHUB_OWNER, GITHUB_REPO)
                if _ok and _bobj:
                    _task_cnt = len(_bobj.get("tasks", []))
                    _at_cnt   = len(_bobj.get("assigned_tasks", []))
                    _g_cnt    = len(_bobj.get("guides", []))
                    _f_cnt    = len(_bobj.get("feedbacks", []))
                    _n_cnt    = len(_bobj.get("application_notes", []))
                    _c_cnt    = len(_bobj.get("error_cases", []))
                    st.session_state["cloud_backup_info"] = {
                        "time": _bobj.get("backup_created_at", "（時間不明）"),
                        "summary": f"{_task_cnt} 筆業務 | {_g_cnt} 情境 | {_f_cnt} 留言 | {_at_cnt} 交辦事項 | {_n_cnt} 注意要點 | {_c_cnt} 錯誤案例"
                    }
                else:
                    st.session_state["cloud_backup_info"] = None
            except Exception:
                st.session_state["cloud_backup_info"] = None

        cloud_info = st.session_state.get("cloud_backup_info")

        if cloud_info:
            st.markdown(f"""
            <div style="background: linear-gradient(to right, #f0fdf4, #dcfce7); border: 1px solid #86efac; border-left: 5px solid #16a34a; border-radius: 8px; padding: 0.7rem 1.2rem; margin-bottom: 0.8rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span style="font-weight:700; color:#15803d;">✅ 雲端備份就緒</span>
                    <span style="font-size:0.85rem; color:#16a34a; margin-left:0.5rem;">{cloud_info['summary']}</span>
                </div>
                <span style="font-size:0.82rem; color:#fff; background:#16a34a; padding:3px 12px; border-radius:12px;">🕒 {cloud_info['time']}</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("🔍 尚未偵測到 GitHub 雲端備份，請先執行「☁️ 一鍵上傳至雲端備份」建立首次備份。")

        # PAT 輸入（只有「上傳」才需要，還原不需要 PAT）
        saved_pat = db.get_github_pat() if hasattr(db, "get_github_pat") else ""
        col_cloud1, col_cloud2 = st.columns([3, 1])
        with col_cloud1:
            github_pat_input = st.text_input(
                "GitHub PAT（上傳時才需要，還原不需要）",
                value=saved_pat,
                type="password",
                placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxx",
                help="GitHub → Settings → Developer settings → Personal access tokens → 建立 Token（勾選 repo 權限）"
            )
        with col_cloud2:
            if st.button("💾 儲存 PAT", use_container_width=True, key="save_pat_btn"):
                if github_pat_input.strip():
                    db.save_github_pat(github_pat_input.strip())
                    set_flash_message("✅ GitHub PAT 已儲存！", icon="🔑")
                    st.rerun()

        col_push, col_restore = st.columns([1, 1])
        with col_push:
            if st.button("☁️ 一鍵上傳至雲端備份", type="primary", use_container_width=True, key="cloud_push_btn"):
                pat = github_pat_input.strip() or saved_pat
                if not pat:
                    st.error("請先輸入並儲存 GitHub PAT（上傳才需要）！")
                else:
                    with st.spinner("正在打包並推送至 GitHub 雲端..."):
                        ok, summary, err = db.push_full_backup_to_github(GITHUB_OWNER, GITHUB_REPO, pat)
                    if ok:
                        # 清除快取，下次讀取最新資訊
                        st.session_state.pop("cloud_backup_info", None)
                        set_flash_message(f"🎉 雲端備份成功！已上傳：{summary}", icon="☁️")
                        st.rerun()
                    else:
                        st.error(f"❌ 上傳失敗：{err}\n💡 請確認 PAT 正確且具有 repo 寫入權限。")

        with col_restore:
            restore_checked = st.checkbox(
                "⚠️ 勾選此處確認要還原（將覆蓋本機資料）",
                key="restore_confirm_check"
            )
            restore_btn_clicked = st.button(
                "🔄 從雲端還原備份",
                type="secondary",
                use_container_width=True,
                key="cloud_restore_btn",
                disabled=not restore_checked,
                help="請先勾選上方確認框，再按此鈕執行還原"
            )
            if restore_btn_clicked and restore_checked:
                bk_time = cloud_info["time"] if cloud_info else "（未知時間）"
                with st.spinner(f"正在從 GitHub 拉取備份（{bk_time}）..."):
                    ok, backup_obj, err = db.fetch_backup_public(GITHUB_OWNER, GITHUB_REPO)
                if ok:
                    ok2, msg2 = db.restore_from_github_backup(backup_obj)
                    st.session_state.pop("cloud_backup_info", None)
                    set_flash_message(f"🎉 雲端還原成功！{msg2}", icon="🔄")
                    st.rerun()
                else:
                    st.error(f"❌ 從雲端拉取失敗：{err}")


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

        col_exp5, col_exp6, _col_pad1, _col_pad2 = st.columns(4)
        with col_exp5:
            st.download_button(
                label="📌 下載【申請注意要點】(CSV)",
                data=pd.DataFrame(db.get_application_notes()).to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                file_name=f"ttfd_application_notes_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        with col_exp6:
            st.download_button(
                label="⚠️ 下載【錯誤樣態案例】(CSV)",
                data=pd.DataFrame(db.get_error_cases()).to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                file_name=f"ttfd_error_cases_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        st.markdown("---")

        # 區塊 3: 上傳備份檔案進行全系統還原 (支援 CSV 與 JSON 全系統備份包)
        st.markdown("##### 📤 3. 上傳備份檔案進行系統還原")
        st.caption("支援 **全系統完整備份包 (.json)** 以及 **業務主表 (.csv)**。系統會自動辨識檔案格式與中文編碼，一鍵精準復原！")
        col_res1, col_res2 = st.columns([1, 1])
        with col_res1:
            uploaded_backup = st.file_uploader(
                "選取先前下載的備份檔案 (.json 或 .csv)", 
                type=["json", "csv"], 
                key="unified_restore_uploader"
            )
            if uploaded_backup is not None:
                fname = uploaded_backup.name.lower()
                bytes_data = uploaded_backup.getvalue()
                
                # 模式 A: JSON 全系統完整備份包還原
                if fname.endswith(".json"):
                    try:
                        import json as py_json
                        json_data = py_json.loads(bytes_data.decode("utf-8"))
                        t_cnt = len(json_data.get("tasks", []))
                        g_cnt = len(json_data.get("guides", []))
                        f_cnt = len(json_data.get("feedbacks", []))
                        st.success(f"📦 識別到【全系統完整備份包】：包含 {t_cnt} 筆業務、{g_cnt} 筆情境導引、{f_cnt} 筆同仁留言。")
                        if st.button("🚀 確認一鍵全系統完整復原", type="primary", use_container_width=True):
                            success, r_msg = db.import_full_system_from_json(json_data)
                            if success:
                                if hasattr(db, "clear_gsheet_url"):
                                    db.clear_gsheet_url()
                                st.session_state["has_auto_synced"] = True
                                set_flash_message(f"🎉 {r_msg} 全系統已完美還原完成！", icon="📦")
                                st.rerun()
                            else:
                                st.error(r_msg)
                    except Exception as e:
                        st.error(f"❌ JSON 檔案解析失敗：{e}")
                
                # 模式 B: CSV 業務清單主表還原
                else:
                    import io
                    import_df = None
                    # 自動嘗試多種中文編碼 (徹底杜絕亂碼)
                    for enc in ["utf-8-sig", "utf-8", "cp950", "big5", "gbk"]:
                        try:
                            temp_df = pd.read_csv(io.BytesIO(bytes_data), encoding=enc)
                            if len(temp_df.columns) >= 2 and len(temp_df) > 0:
                                import_df = temp_df
                                break
                        except Exception:
                            continue
                            
                    if import_df is None:
                        try:
                            import_df = pd.read_csv(io.BytesIO(bytes_data))
                        except Exception as e:
                            st.error(f"❌ CSV 檔案讀取失敗：{e}")

                    if import_df is not None:
                        st.success(f"📋 識別到【業務清單 CSV】：共 {len(import_df)} 筆業務資料。")
                        if st.button("🚀 確認匯入並覆蓋還原業務資料庫", type="primary", use_container_width=True):
                            restored_cnt = db.import_tasks_from_df(import_df, replace_all=True)
                            if restored_cnt > 0:
                                if hasattr(db, "clear_gsheet_url"):
                                    db.clear_gsheet_url()
                                st.session_state["has_auto_synced"] = True
                                set_flash_message(f"🎉 成功還原！已完整還原 {restored_cnt} 筆業務資料，各分頁與內容已即時更新完成。", icon="📤")
                                st.rerun()
                            else:
                                st.error("❌ 無法識別出有效業務資料，請確認上傳的 CSV 檔案是否包含業務標題！")

        with col_res2:
            st.warning("⚠️ **重設為官方標準清單**：將會清除目前所有修改並重新載入官方預設清單。")
            confirm_reseed = st.checkbox("確認要重設為初始官方標準業務清單", key="chk_reseed_final")
            if st.button("🔄 重新初始化資料庫", disabled=not confirm_reseed, type="secondary", use_container_width=True):
                db.init_db(force_reseed=True)
                set_flash_message("🎉 資料庫已成功重設為臺東縣消防局官方標準業務清單與預設資料！", icon="🔄")
                st.rerun()

    # 子分頁 7: 民力科近期交辦協助事項管理
    elif selected_subtab == maintenance_subtabs[6]:
        st.markdown("#### 📋 民力科近期交辦協助事項管理")
        st.caption("在此新增、修改或勾選完成「民力科近期交辦協助事項」，各分頁頂部的公告欄將即時同步顯示給所有外勤大隊同仁查閱。")

        # 新增交辦事項表單
        with st.form("add_assigned_task_form", clear_on_submit=True):
            col_at1, col_at2, col_at3 = st.columns([5, 3, 1])
            with col_at1:
                new_at_content = st.text_input("交辦事項內容 *", placeholder="例如：請各大隊確認義消出勤費名冊後回傳科內")
            with col_at2:
                new_at_deadline = st.text_input("期限重點", placeholder="例如：9/30（三）前回傳")
            with col_at3:
                new_at_sort = st.number_input("排序", min_value=0, max_value=99, value=0, step=1)
            btn_add_at = st.form_submit_button("➕ 新增交辦事項", type="primary", use_container_width=True)
            if btn_add_at:
                if not new_at_content.strip():
                    st.error("請輸入交辦事項內容！")
                else:
                    new_at_id = db.add_assigned_task(new_at_content, new_at_deadline, new_at_sort)
                    set_flash_message(f"🎉 成功新增交辦事項！公告欄已即時更新。", icon="📋")
                    st.rerun()

        st.markdown("---")
        st.markdown("##### 📝 現有交辦事項清單（可直接修改、勾選完成或刪除）")

        all_at = db.get_all_assigned_tasks() if hasattr(db, "get_all_assigned_tasks") else []
        if not all_at:
            st.info("目前尚未新增任何交辦事項，請使用上方表單新增。")
        else:
            for at_item in all_at:
                col_a1, col_a2, col_a3, col_a4, col_a5 = st.columns([0.5, 4, 2.5, 0.7, 0.7])
                with col_a1:
                    at_done = st.checkbox("", value=bool(at_item["is_done"]), key=f"at_done_{at_item['id']}", label_visibility="collapsed")
                with col_a2:
                    at_content = st.text_input("內容", value=at_item["item_content"], key=f"at_content_{at_item['id']}", label_visibility="collapsed")
                with col_a3:
                    at_deadline = st.text_input("期限重點", value=at_item["deadline_note"] or "", key=f"at_deadline_{at_item['id']}", label_visibility="collapsed")
                with col_a4:
                    if st.button("💾", key=f"at_save_{at_item['id']}", use_container_width=True, help="儲存此列修改"):
                        db.update_assigned_task(at_item["id"], at_content, at_deadline, at_done, at_item["sort_order"])
                        set_flash_message(f"✅ 已更新交辦事項！公告欄即時同步。", icon="📋")
                        st.rerun()
                with col_a5:
                    if st.button("🗑️", key=f"at_del_{at_item['id']}", use_container_width=True, help="永久刪除此項"):
                        db.delete_assigned_task(at_item["id"])
                        set_flash_message(f"🗑️ 已刪除該交辦事項。", icon="🗑️")
                        st.rerun()

