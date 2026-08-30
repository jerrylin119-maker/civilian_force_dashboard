# -*- coding: utf-8 -*-
"""
database.py - 民力科業務知識動態看板 資料庫模組
SQLite 資料庫操作：
1. 業務主表 (TaskDatabase)
2. 專業義消承辦人情境導引 (GuideDatabase) - 支援線上動態修改情境與關聯業務
3. 我有話要說回饋留言板 (FeedbackDatabase)
"""

import sqlite3
import pandas as pd
from datetime import datetime
import os

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "minli_tasks.db")

CATEGORIES = ["義消業務", "義消福利", "補捐助業務", "訓練業務", "其他推動業務"]
STATUSES = ["常態辦理", "規劃中", "執行中", "待核銷", "已結案"]

FEEDBACK_CATEGORIES = ["義消業務", "義消福利", "補捐助案件", "訓練業務", "系統建議", "其他問題"]
FEEDBACK_STATUSES = ["待處理", "處理中", "已回覆", "列入參考"]

# 精確符合科內同仁實際分工與業務項目 (包含 115年義消評核)
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
- **系統網址**：[義消專長資料庫入口](https://reurl.cc/gN66v7)
- **維護帳號表**：請查閱 [帳號維護對照清單](https://reurl.cc/RReedG)

#### 作業流程SOP
1. 依維護帳號清單登入「義消專長資料庫」。
2. 檢視並更新所屬分隊義消人員專長（救護、水域、山搜、無人機、火搶等）與證照效期。
3. 定期彙整異動名冊，確保救災協勤調度即時準確。""",
        "doc_links": "義消專長資料庫入口: https://reurl.cc/gN66v7\n維護帳號對照清單: https://reurl.cc/RReedG",
        "last_updated": "2026-08-28 08:00:00"
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
        "last_updated": "2026-08-28 08:00:00"
    },
    {
        "category": "義消業務",
        "subcategory": "業務評核",
        "title": "115年義消評核",
        "owner": "廖昱翔科員、林威宇小隊長",
        "status": "規劃中",
        "update_highlight": "★ 115年義消評核表、重點說明及各項指標資料已彙整，請各分隊依期程備妥佐證資料！",
        "content_detail": """### 115年度義消工作評核作業說明
- **評核目的**：檢視各義消大隊、中隊、分隊年度組織健全度、協勤成效、訓練出席率及各項業務推動成果。
- **評核項目與重點說明**：
  1. 組織編組與人事資料維護完整度
  2. 常年訓練與專業訓練參訓率
  3. 救災協勤出勤安全管制與紀錄
  4. 經費運用與裝備器材保管維護
- **各項資料連結**：評核評分表、佐證資料範本與評核日程表（待補）。""",
        "doc_links": "評核表及重點說明: (待補)\n各項評核資料連結: (待補)",
        "last_updated": "2026-08-28 08:00:00"
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
        "last_updated": "2026-08-28 08:00:00"
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
        "last_updated": "2026-08-28 08:00:00"
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
        "last_updated": "2026-08-28 08:00:00"
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
        "last_updated": "2026-08-28 08:00:00"
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
        "last_updated": "2026-08-28 08:00:00"
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
        "last_updated": "2026-08-28 08:00:00"
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
        "last_updated": "2026-08-28 08:00:00"
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
        "last_updated": "2026-08-28 08:00:00"
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
        "last_updated": "2026-08-28 08:00:00"
    }
]

# 專業義消承辦人 4 大實務情境預設導引資料 (可透過後台線上修改)
SAMPLE_GUIDES = [
    {
        "scenario_num": 1,
        "icon": "👥",
        "title": "1. 我的分隊義消是誰？",
        "target_badge": "連結業務：義消專長資料庫定期維護",
        "description": "📌 **情境說明**：新任承辦人或需要清查轄內分隊義消弟兄姊妹編組、專長分類（救護、水域、山搜、無人機、火搶）及證照效期時，請透過義消專長資料庫進行人員名冊查閱與定期維護。",
        "linked_task_titles": "義消專長資料庫定期維護"
    },
    {
        "scenario_num": 2,
        "icon": "🎁",
        "title": "2. 義消問我有什麼福利？",
        "target_badge": "連結業務：義消福利大項 (保險互助 / 出勤費 / 獎學金 / 健檢專案)",
        "description": "📌 **情境說明**：義消隊員詢問有哪些福利保障時，承辦人可依下列四大項福利政策向同仁說明並協助申辦：\n• **團體保險與福利互助**（傷病醫療、失能住院）：透過線上管制系統申辦\n• **協勤出勤費與誤餐費**：依救災派遣系統紀錄申領\n• **義消子女獎學金**：每學期依成績申請\n• **健康檢查補助**：★ 預計 116 年推動實施，每年提供 300 位名額",
        "linked_task_titles": "義消保險及福利互助申請\n義消出勤費申請作業\n消防義消子女獎學金申請\n義消健康檢查專案補助"
    },
    {
        "scenario_num": 3,
        "icon": "🚒",
        "title": "3. 義消出勤協助救災",
        "target_badge": "連結業務：義消裝備管理 及 義消出勤費申請",
        "description": "📌 **情境說明**：義消同仁出勤協勤救災前之個人防護裝備（PPE）配發管理，以及出勤後之出勤費申報作業：\n• **裝備配發**：本年度採購案針對尚未配發之火搶義消全面配發，預計 11 月完成驗收後發放。\n• **津貼申報**：出勤紀錄由救災派遣系統匯出簽核，並檢附印領清冊辦理核發。",
        "linked_task_titles": "本年度義消消防衣帽鞋採購與火搶義消配發\n義消出勤費申請作業"
    },
    {
        "scenario_num": 4,
        "icon": "🤝",
        "title": "4. 義消辦理團結活動",
        "target_badge": "連結業務：義消申請補縣府及各鄉鎮公所補捐助案件",
        "description": "📌 **情境說明**：各義消分隊規劃辦理常年訓練研習、自強團結活動或器材購置時，向縣府及各鄉鎮公所申請補捐助款之作業指引：\n• **線上系統**：請至補捐助系統下載表單並線上登錄。\n• **申請範例（顏色區別）**：申請範例會隨時間及相關規定更新，**更新部分會以顏色做清楚區別**，請務必參照最新版本填報！",
        "linked_task_titles": "義消申請補縣府及各鄉鎮公所補捐助案件"
    }
]

# 「我有話要說」範例留言初始資料
SAMPLE_FEEDBACKS = [
    {
        "unit_name": "海山分隊",
        "submitter": "蕭義消隊員",
        "category": "義消福利",
        "content": "請問 116 年預計推動的義消健康檢查專案，是否有規定入隊年資或年齡限制？名額如何分配給各分隊？",
        "contact_info": "公務分機 2119",
        "status": "已回覆",
        "admin_reply": "蕭同仁您好！116 年度健檢專案預計每年提供 300 位名額，規劃優先針對 40 歲以上且出勤率達標之現役義消同仁辦理，詳細名額分配與各特約醫療院所清冊預計於年底前函頒各大隊週知。",
        "created_at": "2026-08-28 09:30:00",
        "replied_at": "2026-08-28 11:00:00"
    },
    {
        "unit_name": "慈福分隊",
        "submitter": "分隊義消承辦人",
        "category": "補捐助案件",
        "content": "分隊向公所申請辦理常年研習活動補助款，發票黏存單如檢附電子發票證明聯，是否必須請店家登載機關統編？",
        "contact_info": "公務信箱 minli_cifu@ntpc.gov.tw",
        "status": "已回覆",
        "admin_reply": "承辦人您好！電子發票證明聯請務必請店家登載機關統一編號，若為熱感應紙建議影印一份併同正本黏存，以防字跡褪色影響審計核銷。",
        "created_at": "2026-08-28 10:15:00",
        "replied_at": "2026-08-28 13:20:00"
    },
    {
        "unit_name": "新莊義消分隊",
        "submitter": "林分隊長",
        "category": "義消業務",
        "content": "本年度火搶義消消防衣帽鞋配發進度，各分隊預計何時可以送交身材尺寸與型號對照清單？",
        "contact_info": "0912-345-678",
        "status": "處理中",
        "admin_reply": "林分隊長您好！廠商已備料並排定於 11 月辦理驗收，各分隊身材尺寸清冊已請各大隊彙整中，預計本月中旬由科內統一對焦名冊。",
        "created_at": "2026-08-28 14:00:00",
        "replied_at": "2026-08-28 14:45:00"
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

    # 1. 業務主表 TaskDatabase
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

    # 2. 專業義消承辦人情境導引表 GuideDatabase
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS GuideDatabase (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_num INTEGER NOT NULL,
            icon TEXT,
            title TEXT NOT NULL,
            target_badge TEXT,
            description TEXT,
            linked_task_titles TEXT
        )
    """)

    # 3. 我有話要說留言板 FeedbackDatabase
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS FeedbackDatabase (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_name TEXT NOT NULL,
            submitter TEXT,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            contact_info TEXT,
            status TEXT NOT NULL DEFAULT '待處理',
            admin_reply TEXT,
            created_at TEXT NOT NULL,
            replied_at TEXT
        )
    """)
    conn.commit()

    if force_reseed:
        cursor.execute("DELETE FROM TaskDatabase")
        cursor.execute("DELETE FROM GuideDatabase")
        cursor.execute("DELETE FROM FeedbackDatabase")
        conn.commit()

    # 檢查 TaskDatabase
    cursor.execute("SELECT COUNT(*) FROM TaskDatabase")
    if cursor.fetchone()[0] == 0:
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

    # 檢查 GuideDatabase
    cursor.execute("SELECT COUNT(*) FROM GuideDatabase")
    if cursor.fetchone()[0] == 0:
        for g in SAMPLE_GUIDES:
            cursor.execute("""
                INSERT INTO GuideDatabase (
                    scenario_num, icon, title, target_badge, description, linked_task_titles
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                g["scenario_num"],
                g["icon"],
                g["title"],
                g["target_badge"],
                g["description"],
                g["linked_task_titles"]
            ))
        conn.commit()

    # 檢查 FeedbackDatabase
    cursor.execute("SELECT COUNT(*) FROM FeedbackDatabase")
    if cursor.fetchone()[0] == 0:
        for fb in SAMPLE_FEEDBACKS:
            cursor.execute("""
                INSERT INTO FeedbackDatabase (
                    unit_name, submitter, category, content, contact_info,
                    status, admin_reply, created_at, replied_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fb["unit_name"],
                fb["submitter"],
                fb["category"],
                fb["content"],
                fb["contact_info"],
                fb["status"],
                fb["admin_reply"],
                fb["created_at"],
                fb["replied_at"]
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
    
    cursor.execute("SELECT COUNT(*) FROM FeedbackDatabase")
    feedback_total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM FeedbackDatabase WHERE status = '已回覆'")
    feedback_replied = cursor.fetchone()[0]

    conn.close()
    return {
        "total": total_count,
        "in_progress": in_progress_count,
        "pending_reimburse": pending_reimburse_count,
        "highlight": highlight_count,
        "feedback_total": feedback_total,
        "feedback_replied": feedback_replied
    }


# ==================== 專業義消承辦人 (Guide) CRUD 操作 ====================

def get_all_guides():
    """取得專業義消承辦人情境導引資料"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM GuideDatabase ORDER BY scenario_num ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_guide(guide_id, icon, title, target_badge, description, linked_task_titles):
    """更新專業義消承辦人特定情境設定"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE GuideDatabase SET
            icon = ?,
            title = ?,
            target_badge = ?,
            description = ?,
            linked_task_titles = ?
        WHERE id = ?
    """, (
        icon.strip(),
        title.strip(),
        target_badge.strip(),
        description.strip(),
        linked_task_titles.strip(),
        guide_id
    ))
    conn.commit()
    conn.close()


# ==================== 我有話要說 (Feedback) CRUD 操作 ====================

def get_all_feedbacks(category_filter=None, status_filter=None):
    """取得所有同仁回饋留言"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM FeedbackDatabase WHERE 1=1"
    params = []

    if category_filter and category_filter != "全部類別":
        query += " AND category = ?"
        params.append(category_filter)

    if status_filter and status_filter != "全部狀態":
        query += " AND status = ?"
        params.append(status_filter)

    query += " ORDER BY id DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def add_feedback(unit_name, submitter, category, content, contact_info):
    """新增一筆同仁回饋留言"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO FeedbackDatabase (
            unit_name, submitter, category, content, contact_info,
            status, admin_reply, created_at, replied_at
        ) VALUES (?, ?, ?, ?, ?, '待處理', '', ?, NULL)
    """, (
        unit_name.strip(),
        submitter.strip() if submitter else "熱心同仁",
        category,
        content.strip(),
        contact_info.strip() if contact_info else "",
        now_str
    ))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


def reply_feedback(feedback_id, status, admin_reply):
    """科內管理員回覆或更新回饋狀態"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        UPDATE FeedbackDatabase SET
            status = ?,
            admin_reply = ?,
            replied_at = ?
        WHERE id = ?
    """, (status, admin_reply.strip(), now_str, feedback_id))
    conn.commit()
    conn.close()


def delete_feedback(feedback_id):
    """刪除指定回饋留言"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM FeedbackDatabase WHERE id = ?", (feedback_id,))
    conn.commit()
    conn.close()
