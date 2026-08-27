# -*- coding: utf-8 -*-
"""
database.py - 民力科業務知識動態看板 資料庫模組
SQLite 資料庫操作、資料表建立與民力科官方實際業務清單初始化
"""

import sqlite3
import pandas as pd
from datetime import datetime
import os

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "minli_tasks.db")

CATEGORIES = ["義消業務", "義消福利", "補捐助業務", "訓練業務", "其他推動業務"]
STATUSES = ["常態辦理", "規劃中", "執行中", "待核銷", "已結案"]

# 精確符合科內同仁實際分工與業務項目
SAMPLE_DATA = [
    # ==================== 1. 義消業務 ====================
    # 承辦人: 廖昱翔科員、林威宇小隊長
    {
        "category": "義消業務",
        "subcategory": "專長資料庫",
        "title": "義消專長資料庫定期維護",
        "owner": "廖昱翔科員、林威宇小隊長",
        "status": "常態辦理",
        "update_highlight": "★ 請各單位定期依維護帳號清單登入系統，維護更新義消人員最新專長資料。",
        "content_detail": """### 義消專長資料庫維護作業指引
- **系統網址**：[義消專長資料庫](https://reurl.cc/gN66v7)
- **維護帳號表**：請查閱 [帳號維護對照清單](https://reurl.cc/RReedG)

#### 作業流程SOP
1. 依維護帳號清單登入「義消專長資料庫」。
2. 檢視並更新所屬義消人員各項專長（救護、水域、山搜、無人機、火搶等）與證照效期。
3. 定期彙整異動名冊，確保救災協勤調度即時準確。""",
        "doc_links": "義消專長資料庫入口: https://reurl.cc/gN66v7\n維護帳號對照清單: https://reurl.cc/RReedG",
        "last_updated": "2026-08-27 10:00:00"
    },
    {
        "category": "義消業務",
        "subcategory": "中程計畫",
        "title": "韌性臺灣－強化各類型義消科技化訓練與精進裝備中程計畫",
        "owner": "廖昱翔科員、林威宇小隊長",
        "status": "執行中",
        "update_highlight": "⚠️ 115年計畫包含購置裝備訓練，相關核銷作業預計 9 月中函報消防署！",
        "content_detail": """### 計畫重點與執行期程
- **計畫概要**：115 年中程計畫重點包含「購置裝備」與「科技化模組訓練」。
- **訓練列表及執行狀況**：各梯次辦理進度及管制期限請參閱線上連結表單。
- **核銷期程管制**：相關核銷作業預計於 **9 月中旬** 函報內政部消防署辦理。""",
        "doc_links": "訓練部分列表及辦理執行狀況與期限: https://reurl.cc/AX22qd",
        "last_updated": "2026-08-27 11:30:00"
    },
    {
        "category": "義消業務",
        "subcategory": "裝備配發",
        "title": "本年度義消消防衣帽鞋採購與火搶義消配發",
        "owner": "廖昱翔科員、林威宇小隊長",
        "status": "執行中",
        "update_highlight": "⚠️ 本年度義消消防衣帽鞋採購將針對「尚未配發之火搶義消」完成配發，預計 11 月完成驗收後辦理配發！",
        "content_detail": """### 配發對象與預計時程
- **配發對象**：本年度採購案針對尚未配發個人防護裝備（PPE）之火搶義消同仁全面補足配發。
- **執行進度**：目前辦理採購履約中，預計 **11 月完成驗收** 並迅速依清冊配發。
- **配發清冊**：各分隊火搶義消裝備配發清冊造冊中（待補）。""",
        "doc_links": "義消消防衣及裝備配發清冊: (待補)",
        "last_updated": "2026-08-27 14:00:00"
    },
    {
        "category": "義消業務",
        "subcategory": "法規介紹",
        "title": "義消法規介紹與作業指引",
        "owner": "廖昱翔科員、林威宇小隊長",
        "status": "常態辦理",
        "update_highlight": "",
        "content_detail": """### 義消核心法規
- **義勇消防組織編組訓練演習服勤辦法**：
  涵蓋義勇消防編組架構、幹部遴聘資格、常年與專精訓練規範、演習及服勤協勤之法定權利與義務保障。
- 各單位辦理義消組訓與協勤請確依本辦法規範落實執行。""",
        "doc_links": "義勇消防組織編組訓練演習服勤辦法: https://law.nfa.gov.tw/MOBILE/law.aspx?LSID=FL005073",
        "last_updated": "2026-08-27 09:00:00"
    },

    # ==================== 2. 義消福利 ====================
    # 承辦人: 陳怡忻分隊長
    {
        "category": "義消福利",
        "subcategory": "保險與互助",
        "title": "義消保險及福利互助申請",
        "owner": "陳怡忻分隊長",
        "status": "常態辦理",
        "update_highlight": "★ 義消福利互助管制系統已整合上線，請各單位善用線上系統進行案件管制！",
        "content_detail": """### 保險與互助保障說明
- **保險保障內容**：意外保障、傷病住院、失能與互助金申領規定（保險保障表及申請SOP待補）。
- **線上管制系統**：請透過 [義消福利互助管制系統](https://reurl.cc/8YXX2b) 進行申請案線上列管與進度查詢。""",
        "doc_links": "義消福利互助管制系統: https://reurl.cc/8YXX2b\n保險保障項目及申請SOP: (待補)",
        "last_updated": "2026-08-27 10:30:00"
    },
    {
        "category": "義消福利",
        "subcategory": "出勤費申請",
        "title": "義消出勤費申請作業",
        "owner": "陳怡忻分隊長",
        "status": "常態辦理",
        "update_highlight": "",
        "content_detail": """### 出勤費申請說明
- **作業規定**：義勇消防人員協勤出勤津貼、誤餐費用之申報流程及核銷標準（申請流程及規定待補）。
- **注意事項**：出勤紀錄應確實由救災派遣系統簽到核銷，並檢附印領清冊送審。""",
        "doc_links": "出勤費申請流程及規定: (待補)",
        "last_updated": "2026-08-27 08:30:00"
    },
    {
        "category": "義消福利",
        "subcategory": "子女獎學金",
        "title": "消防義消子女獎學金申請",
        "owner": "陳怡忻分隊長",
        "status": "常態辦理",
        "update_highlight": "",
        "content_detail": """### 獎助學金作業說明
- **申請對象**：獎勵現役義勇消防人員在學子女成績優良獎助學金。
- **申辦文件**：申請表格、成績證明文件及審查程序（表格及程序待補，依各學期公告期程受理）。""",
        "doc_links": "獎學金申請表格及程序: (待補)",
        "last_updated": "2026-08-27 08:30:00"
    },
    {
        "category": "義消福利",
        "subcategory": "健康檢查",
        "title": "義消健康檢查專案補助",
        "owner": "陳怡忻分隊長",
        "status": "規劃中",
        "update_highlight": "★ 【重要宣導】義消健康檢查預計 116 年開始正式執行，每年提供 300 位名額！",
        "content_detail": """### 健檢專案規劃方案
- **實施期程**：預計 **116 年開始正式推動實行**。
- **每年名額**：**每年補助 300 位名額**，照顧第一線奉獻之義消同仁健康。
- **配套規劃**：健檢合約醫院清冊、健檢套餐項目與各單位名額分配辦法現正通盤規劃中。""",
        "doc_links": "健檢特約院所與分配要點: (規劃中待補)",
        "last_updated": "2026-08-27 15:00:00"
    },

    # ==================== 3. 補捐助業務 ====================
    # 承辦人: 廖昱翔科員、林威宇小隊長
    {
        "category": "補捐助業務",
        "subcategory": "補捐助案件管理",
        "title": "義消申請補縣府及各鄉鎮公所補捐助案件",
        "owner": "廖昱翔科員、林威宇小隊長",
        "status": "執行中",
        "update_highlight": "⚠️ 補捐助申請範例將隨時間動態更新，更新部分會以「顏色」區別標記，請各分隊參照最新範例辦理！",
        "content_detail": """### 申請流程規定與範例說明
- **申請表單及系統**：請進入 [補捐助申請表單及系統](https://reurl.cc/0kdd2M) 線上申辦與下載表件。
- **申請範例（顏色區別）**：申請範例會隨時間及相關規定更新，**更新部分會以顏色做清楚區別**，方便各分隊辨識調整。

#### 補捐助標準作業程序
1. **填表申請**：至線上系統下載最新表單填報補助企劃與經費表。
2. **初審查核**：承辦人查核自籌款比例、支用科目是否符合規範。
3. **核定執行**：通過後發函核定，受補助單位依計畫執行。
4. **核銷結案**：檢附發票收據、活動成果照片等黏存單送科核銷。""",
        "doc_links": "申請表單及系統: https://reurl.cc/0kdd2M\n申請範例(隨時間顏色更新版): https://reurl.cc/0kdd2M",
        "last_updated": "2026-08-27 16:00:00"
    },

    # ==================== 4. 訓練業務 ====================
    # 承辦人: 尤仁宏秘書
    {
        "category": "訓練業務",
        "subcategory": "教育訓練管理",
        "title": "教育訓練管理",
        "owner": "尤仁宏秘書",
        "status": "常態辦理",
        "update_highlight": "",
        "content_detail": """### 教育訓練管理作業
- **規範項目**：包含義消新進訓練、常年訓練、專精與幹部講習管理。
- **作業文件**：教育訓練程序書及相關表格規定（待補）。""",
        "doc_links": "教育訓練程序書及相關表格規定: (待補)",
        "last_updated": "2026-08-27 09:00:00"
    },
    {
        "category": "訓練業務",
        "subcategory": "鳳凰數位學習",
        "title": "鳳凰數位學習網管理與時數認證",
        "owner": "尤仁宏秘書",
        "status": "常態辦理",
        "update_highlight": "★ 鳳凰數位學習網專屬入口已建立，請同仁依規定登入並完成年度必修課程時數。",
        "content_detail": """### 鳳凰數位學習網使用說明
- **平台連結**：[消防署鳳凰數位學習網入口](https://sites.google.com/d/1KSikFOmeqiEngtUdU7ilsc2XOl6tuUkn/p/1DvhmzmB8E9JfwT5qALznUaHlGJMJkHsn/edit)
- 各單位請督導所屬義消人員於規定期限前完成線上課程學習與測驗認證。""",
        "doc_links": "鳳凰數位學習網入口: https://sites.google.com/d/1KSikFOmeqiEngtUdU7ilsc2XOl6tuUkn/p/1DvhmzmB8E9JfwT5qALznUaHlGJMJkHsn/edit",
        "last_updated": "2026-08-27 10:00:00"
    }
]


def get_db_connection():
    """取得 SQLite 資料庫連線"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(force_reseed=False):
    """初始化資料庫與資料表，若無資料則匯入範例種子資料"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS TaskDatabase (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            subcategory TEXT,
            title TEXT NOT NULL,
            owner TEXT,
            status TEXT NOT NULL DEFAULT '常態辦理',
            update_highlight TEXT,
            content_detail TEXT,
            doc_links TEXT,
            last_updated TEXT NOT NULL
        )
    """)
    conn.commit()

    if force_reseed:
        cursor.execute("DELETE FROM TaskDatabase")
        conn.commit()

    cursor.execute("SELECT COUNT(*) FROM TaskDatabase")
    count = cursor.fetchone()[0]

    if count == 0:
        for item in SAMPLE_DATA:
            cursor.execute("""
                INSERT INTO TaskDatabase (
                    category, subcategory, title, owner, status,
                    update_highlight, content_detail, doc_links, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item["category"],
                item["subcategory"],
                item["title"],
                item["owner"],
                item["status"],
                item["update_highlight"],
                item["content_detail"],
                item["doc_links"],
                item["last_updated"]
            ))
        conn.commit()

    conn.close()


def get_all_tasks_df() -> pd.DataFrame:
    """取得所有業務資料並轉換為 Pandas DataFrame"""
    init_db()
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM TaskDatabase ORDER BY id ASC", conn)
    conn.close()
    return df


def get_tasks_by_filter(category=None, owner=None, status=None, search_query=None, only_highlight=False):
    """依條件查詢任務清單"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM TaskDatabase WHERE 1=1"
    params = []

    if category and category != "全部業務":
        query += " AND category = ?"
        params.append(category)

    if owner and owner != "全部承辦人":
        query += " AND owner = ?"
        params.append(owner)

    if status and status != "全部狀態":
        query += " AND status = ?"
        params.append(status)

    if only_highlight:
        query += " AND update_highlight IS NOT NULL AND TRIM(update_highlight) != ''"

    if search_query and search_query.strip():
        q = f"%{search_query.strip()}%"
        query += """ AND (
            title LIKE ? OR 
            subcategory LIKE ? OR 
            owner LIKE ? OR 
            update_highlight LIKE ? OR 
            content_detail LIKE ?
        )"""
        params.extend([q, q, q, q, q])

    query += " ORDER BY id ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def add_task(category, subcategory, title, owner, status, update_highlight, content_detail, doc_links):
    """新增一筆業務資料"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO TaskDatabase (
            category, subcategory, title, owner, status,
            update_highlight, content_detail, doc_links, last_updated
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        category, subcategory, title, owner, status,
        update_highlight, content_detail, doc_links, now_str
    ))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


def update_single_task(task_id, category, subcategory, title, owner, status, update_highlight, content_detail, doc_links):
    """更新單筆業務項目"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        UPDATE TaskDatabase SET
            category = ?,
            subcategory = ?,
            title = ?,
            owner = ?,
            status = ?,
            update_highlight = ?,
            content_detail = ?,
            doc_links = ?,
            last_updated = ?
        WHERE id = ?
    """, (
        category, subcategory, title, owner, status,
        update_highlight, content_detail, doc_links, now_str, task_id
    ))
    conn.commit()
    conn.close()


def batch_update_tasks_from_df(edited_df: pd.DataFrame):
    """從 st.data_editor 修改後的 DataFrame 批次更新回 SQLite 資料庫"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    existing_df = pd.read_sql_query("SELECT * FROM TaskDatabase", conn)
    existing_dict = existing_df.set_index("id").to_dict("index")

    updated_count = 0
    for _, row in edited_df.iterrows():
        row_id = int(row["id"])
        
        if row_id in existing_dict:
            orig = existing_dict[row_id]
            is_changed = False
            for col in ["category", "subcategory", "title", "owner", "status", "update_highlight", "content_detail", "doc_links"]:
                val_new = str(row[col]) if pd.notna(row[col]) else ""
                val_orig = str(orig[col]) if pd.notna(orig[col]) else ""
                if val_new != val_orig:
                    is_changed = True
                    break
            
            if is_changed:
                cursor.execute("""
                    UPDATE TaskDatabase SET
                        category = ?,
                        subcategory = ?,
                        title = ?,
                        owner = ?,
                        status = ?,
                        update_highlight = ?,
                        content_detail = ?,
                        doc_links = ?,
                        last_updated = ?
                    WHERE id = ?
                """, (
                    str(row["category"]) if pd.notna(row["category"]) else "",
                    str(row["subcategory"]) if pd.notna(row["subcategory"]) else "",
                    str(row["title"]) if pd.notna(row["title"]) else "",
                    str(row["owner"]) if pd.notna(row["owner"]) else "",
                    str(row["status"]) if pd.notna(row["status"]) else "常態辦理",
                    str(row["update_highlight"]) if pd.notna(row["update_highlight"]) else "",
                    str(row["content_detail"]) if pd.notna(row["content_detail"]) else "",
                    str(row["doc_links"]) if pd.notna(row["doc_links"]) else "",
                    now_str,
                    row_id
                ))
                updated_count += 1

    conn.commit()
    conn.close()
    return updated_count


def delete_task(task_id):
    """刪除指定業務項目"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM TaskDatabase WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()


def get_owners_list():
    """取得所有承辦人清單"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT owner FROM TaskDatabase WHERE owner IS NOT NULL AND TRIM(owner) != '' ORDER BY owner")
    owners = [row[0] for row in cursor.fetchall()]
    conn.close()
    return owners


def get_summary_stats():
    """取得全域彙整統計數字"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM TaskDatabase")
    total_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM TaskDatabase WHERE status IN ('執行中', '規劃中')")
    in_progress_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM TaskDatabase WHERE status = '待核銷'")
    pending_reimburse_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM TaskDatabase WHERE update_highlight IS NOT NULL AND TRIM(update_highlight) != ''")
    highlight_count = cursor.fetchone()[0]
    
    conn.close()
    return {
        "total": total_count,
        "in_progress": in_progress_count,
        "pending_reimburse": pending_reimburse_count,
        "highlight": highlight_count
    }
