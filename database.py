# -*- coding: utf-8 -*-
"""
database.py - 臺東縣消防局民力訓練科 業務知識動態看板 資料庫模組
依據「臺東縣消防局組織架構」完整納入四大外勤大隊與所屬分隊：
- 臺東大隊：臺東、臺東救護、豐田、大豐、南王、特種搜救、科技救災、搜救犬、卑南、知本、綠島、蘭嶼
- 關山大隊：關山、池上、海端、鹿野、延平、利稻
- 成功大隊：成功、長濱、都蘭、泰源、東河
- 大武大隊：大武、太麻里、金峰、大溪、達仁
"""

import sqlite3
import pandas as pd
from datetime import datetime
import os
import re

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "minli_tasks.db")

CATEGORIES = ["義消業務", "義消福利", "補捐助業務", "訓練業務", "其他推動業務"]
STATUSES = ["常態辦理", "規劃中", "執行中", "待核銷", "已結案"]
DEFAULT_OFFICERS = ["廖昱翔科員、林威宇小隊長", "廖昱翔科員", "林威宇小隊長", "陳怡忻分隊長", "尤仁宏秘書", "民力訓練科全體同仁"]

FEEDBACK_CATEGORIES = ["義消業務", "義消福利", "補捐助案件", "訓練業務", "系統建議", "其他問題"]
FEEDBACK_STATUSES = ["待處理", "處理中", "已回覆", "列入參考"]

# 臺東縣消防局全轄外勤大隊與分隊清單
TAITUNG_UNITS = [
    # 臺東大隊
    "臺東分隊", "臺東救護分隊", "豐田分隊", "大豐分隊", "南王分隊",
    "特種搜救分隊", "科技救災分隊", "搜救犬分隊", "卑南分隊", "知本分隊", "綠島分隊", "蘭嶼分隊", "臺東大隊部",
    # 關山大隊
    "關山分隊", "池上分隊", "海端分隊", "鹿野分隊", "延平分隊", "利稻分隊", "關山大隊部",
    # 成功大隊
    "成功分隊", "長濱分隊", "都蘭分隊", "泰源分隊", "東河分隊", "成功大隊部",
    # 大武大隊
    "大武分隊", "太麻里分隊", "金峰分隊", "大溪分隊", "達仁分隊", "大武大隊部",
    # 局本部與其他
    "民力訓練科", "救災救護指揮中心", "安檢隊", "其他科室/大隊"
]

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
        "content_detail": """### 義消專長資料庫維護作業 SOP
1. **登入系統**：請對照 [各分隊維護帳號清單](https://reurl.cc/RReedG) 登入 [義消專長資料庫入口](https://reurl.cc/gN66v7)。
2. **資料清查**：檢視並維護所屬分隊義消人員專長分類（EMT救護、水域救援、山搜、無人機、火搶）及證照效期。
3. **異動更新**：定期彙整人員異動與受訓名冊，確保救災協勤調度資訊即時準確。""",
        "doc_links": "義消專長資料庫入口: https://reurl.cc/gN66v7\n維護帳號對照清單: https://reurl.cc/RReedG",
        "last_updated": "2026-08-30 08:00:00"
    },
    {
        "category": "義消業務",
        "subcategory": "中程計畫",
        "title": "韌性臺灣－強化各類型義消科技化訓練與精進裝備中程計畫",
        "owner": "廖昱翔科員、林威宇小隊長",
        "status": "執行中",
        "update_highlight": "⚠️ 115年計畫包含購置裝備訓練，相關核銷作業預計 9 月中函報消防署！",
        "content_detail": """### 中程計畫執行 SOP 與期程管制
1. **計畫內容**：115 年中程計畫重點包含「購置裝備」與「科技化模組訓練」。
2. **訓練進度**：各梯次辦理進度及管制期限請參閱 [訓練部分列表及辦理執行狀況與期限](https://reurl.cc/AX22qd)。
3. **核銷作業**：相關核銷作業預計於 **9 月中旬** 函報內政部消防署辦理。""",
        "doc_links": "訓練部分列表及辦理執行狀況與期限: https://reurl.cc/AX22qd",
        "last_updated": "2026-08-30 08:00:00"
    },
    {
        "category": "義消業務",
        "subcategory": "業務評核",
        "title": "115年義消評核",
        "owner": "廖昱翔科員、林威宇小隊長",
        "status": "規劃中",
        "update_highlight": "★ 115年義消評核表、重點說明及各項指標資料已彙整，請各分隊依期程備妥佐證資料！",
        "content_detail": """### 115年度義消工作評核作業 SOP
1. **評核對象**：各大隊、中隊、分隊年度組織健全度、協勤成效、訓練出席率及各項業務推動成果。
2. **四大評核重點**：
   - 組織編組與人事資料維護完整度
   - 常年訓練與專業訓練參訓率
   - 救災協勤出勤安全管制與紀錄
   - 經費運用與裝備器材保管維護
3. **表件備妥**：各分隊依評核評分表及重點說明備齊佐證資料（評核表及資料連結待補）。""",
        "doc_links": "評核表及重點說明: (待補)\n各項評核資料連結: (待補)",
        "last_updated": "2026-08-30 08:00:00"
    },
    {
        "category": "義消業務",
        "subcategory": "裝備配發",
        "title": "本年度義消消防衣帽鞋採購與火搶義消配發",
        "owner": "廖昱翔科員、林威宇小隊長",
        "status": "執行中",
        "update_highlight": "⚠️ 本年度義消消防衣帽鞋採購將針對「尚未配發之火搶義消」完成配發，預計 11 月完成驗收後辦理配發！",
        "content_detail": """### 消防衣帽鞋採購與配發 SOP
1. **配發對象**：本年度採購案針對「尚未配發個人防護裝備（PPE）」之火搶義消同仁全面補足配發。
2. **履約進度**：目前辦理採購履約中，預計 **11 月完成驗收** 並迅速依清冊配發各分隊。
3. **清冊對焦**：各分隊火搶義消裝備配發清冊造冊中（待補）。""",
        "doc_links": "義消消防衣及裝備配發清冊: (待補)",
        "last_updated": "2026-08-30 08:00:00"
    },
    {
        "category": "義消業務",
        "subcategory": "法規介紹",
        "title": "義消法規介紹與作業指引",
        "owner": "廖昱翔科員、林威宇小隊長",
        "status": "常態辦理",
        "update_highlight": "",
        "content_detail": """### 義消核心法規作業指引
- **法規名稱**：[義勇消防組織編組訓練演習服勤辦法](https://law.nfa.gov.tw/MOBILE/law.aspx?LSID=FL005073)
- **規範核心**：涵蓋義勇消防編組架構、幹部遴聘資格、常年與專精訓練規範、演習及服勤協勤之法定權利與義務保障。各分隊辦理組訓與協勤請確依本辦法執行。""",
        "doc_links": "義勇消防組織編組訓練演習服勤辦法: https://law.nfa.gov.tw/MOBILE/law.aspx?LSID=FL005073",
        "last_updated": "2026-08-30 08:00:00"
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
        "content_detail": """### 義消保險與福利互助申請 SOP
1. **保障範圍**：涵蓋意外傷害、傷病住院、失能給付及互助金申領。
2. **申辦管制**：請承辦人透過 [義消福利互助管制系統](https://reurl.cc/8YXX2b) 線上登錄案件並追蹤審核進度。
3. **檢附文件**：依規定備齊醫療診斷證明書、收據正本及互助申請表送科審查（保險保障表及申請SOP待補）。""",
        "doc_links": "義消福利互助管制系統: https://reurl.cc/8YXX2b\n保險保障項目及申請SOP: (待補)",
        "last_updated": "2026-08-30 08:00:00"
    },
    {
        "category": "義消福利",
        "subcategory": "出勤費申請",
        "title": "義消出勤費申請作業",
        "owner": "陳怡忻分隊長",
        "status": "常態辦理",
        "update_highlight": "",
        "content_detail": """### 義消出勤費申請 SOP
1. **出勤紀錄登錄**：義消人員協勤出勤紀錄須確實由「救災派遣系統」簽到並確認出勤時數。
2. **造冊審核**：分隊承辦人按月匯出出勤紀錄，製作出勤印領清冊送大隊與科內審核。
3. **津貼核發**：審查通過後辦理經費核銷並撥入義消同仁郵局帳戶（申請流程及規定待補）。""",
        "doc_links": "出勤費申請流程及規定: (待補)",
        "last_updated": "2026-08-30 08:00:00"
    },
    {
        "category": "義消福利",
        "subcategory": "子女獎學金",
        "title": "消防義消子女獎學金申請",
        "owner": "陳怡忻分隊長",
        "status": "常態辦理",
        "update_highlight": "",
        "content_detail": """### 義消子女獎學金申辦 SOP
1. **申請資格**：獎勵現役義勇消防人員在學子女成績優良者。
2. **申請期程**：每學期依局方公告期程受理申請。
3. **應備文件**：填具申請表，檢附前一學期在學成績單、戶籍謄本或戶口名簿影本（表格及程序待補）。""",
        "doc_links": "獎學金申請表格及程序: (待補)",
        "last_updated": "2026-08-30 08:00:00"
    },
    {
        "category": "義消福利",
        "subcategory": "健康檢查",
        "title": "義消健康檢查專案補助",
        "owner": "陳怡忻分隊長",
        "status": "規劃中",
        "update_highlight": "★ 【重要宣導】義消健康檢查預計 116 年開始正式執行，每年提供 300 位名額！",
        "content_detail": """### 義消健康檢查專案說明 SOP
1. **實施期程**：預計 **116 年正式推動實行**。
2. **名額補助**：**每年補助 300 位名額**，照顧第一線奉獻之義消同仁健康。
3. **分配與院所**：健檢合約醫院清冊、健檢套餐項目與各單位名額分配要點規劃中（待補）。""",
        "doc_links": "健檢特約院所與分配要點: (規劃中待補)",
        "last_updated": "2026-08-30 08:00:00"
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
        "content_detail": """### 補捐助案件標準作業程序 (SOP)
1. **線上表單下載**：請至 [補捐助申請表單及系統](https://reurl.cc/0kdd2M) 下載最新申請企劃與經費概算表。
2. **申請範例（顏色標記）**：申請範例會隨時間更新，**更新部分會以顏色做清楚區別**，請各分隊務必下載最新版本填報。
3. **初審查核**：承辦人查核自籌款比例、支用科目是否符合相關補捐助規定。
4. **核定發函**：審核通過後發函核定，受補助單位依核定計畫執行活動或採購。
5. **核銷結案**：活動結束後檢附發票收據、活動成果照片等黏存單送科辦理核銷撥款。""",
        "doc_links": "申請表單及系統: https://reurl.cc/0kdd2M\n申請範例(隨時間顏色更新版): https://reurl.cc/0kdd2M",
        "last_updated": "2026-08-30 08:00:00"
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
        "content_detail": """### 義消教育訓練管理 SOP
1. **訓練項目**：涵蓋義消新進基本訓練、常年定期訓練、專業機能訓練與幹部講習。
2. **簽到與時數**：各項訓練落實簽到退，並登載義消人員訓練時數紀錄。
3. **作業規定**：教育訓練程序書及相關表格規定（待補）。""",
        "doc_links": "教育訓練程序書及相關表格規定: (待補)",
        "last_updated": "2026-08-30 08:00:00"
    },
    {
        "category": "訓練業務",
        "subcategory": "鳳凰數位學習",
        "title": "鳳凰數位學習網管理與時數認證",
        "owner": "尤仁宏秘書",
        "status": "常態辦理",
        "update_highlight": "★ 鳳凰數位學習網專屬入口已建立，請同仁依規定登入並完成年度必修課程時數。",
        "content_detail": """### 鳳凰數位學習網線上修課 SOP
1. **線上平台入口**：請點選進入 [消防署鳳凰數位學習網入口](https://sites.google.com/d/1KSikFOmeqiEngtUdU7ilsc2XOl6tuUkn/p/1DvhmzmB8E9JfwT5qALznUaHlGJMJkHsn/edit)。
2. **修課認證**：依年度必修課程清單完成線上影音研習並通過隨堂測驗。
3. **時數匯入**：分隊承辦人定期查核學習時數並匯入義消教育訓練管理系統。""",
        "doc_links": "鳳凰數位學習網入口: https://sites.google.com/d/1KSikFOmeqiEngtUdU7ilsc2XOl6tuUkn/p/1DvhmzmB8E9JfwT5qALznUaHlGJMJkHsn/edit",
        "last_updated": "2026-08-30 08:00:00"
    }
]

# 專業義消承辦人 4 大實務情境預設導引資料
SAMPLE_GUIDES = [
    {
        "scenario_num": 1,
        "icon": "👥",
        "title": "1. 我的分隊義消是誰？",
        "target_badge": "連結業務：義消專長資料庫定期維護",
        "description": "新任承辦人或需要清查轄內分隊義消弟兄姊妹編組、專長分類（救護、水域、山搜、無人機、火搶）及證照效期時，請透過「義消專長資料庫」進行人員名冊查閱與定期維護。",
        "linked_task_titles": "義消專長資料庫定期維護"
    },
    {
        "scenario_num": 2,
        "icon": "🎁",
        "title": "2. 義消問我有什麼福利？",
        "target_badge": "連結業務：義消福利大項",
        "description": "義消隊員詢問有哪些福利保障時，承辦人可依下列四大項福利政策（團體保險與互助金、出勤費、子女獎學金、健檢補助）向同仁說明並協助申辦。",
        "linked_task_titles": "義消保險及福利互助申請\n義消出勤費申請作業\n消防義消子女獎學金申請\n義消健康檢查專案補助"
    },
    {
        "scenario_num": 3,
        "icon": "🚒",
        "title": "3. 義消出勤協助救災",
        "target_badge": "連結業務：義消裝備管理 及 義消出勤費申請",
        "description": "義消同仁出勤協勤救災前之個人防護裝備（PPE）配發管理，以及出勤後之出勤津貼申報作業。",
        "linked_task_titles": "本年度義消消防衣帽鞋採購與火搶義消配發\n義消出勤費申請作業"
    },
    {
        "scenario_num": 4,
        "icon": "🤝",
        "title": "4. 義消辦理團結活動",
        "target_badge": "連結業務：義消申請補縣府及各鄉鎮公所補捐助案件",
        "description": "各義消分隊規劃辦理常年訓練研習、自強團結活動或器材購置時，向縣府及各鄉鎮公所申請補捐助款之作業指引。",
        "linked_task_titles": "義消申請補縣府及各鄉鎮公所補捐助案件"
    }
]

# 「我有話要說」範例留言 (完整以臺東縣消防局轄下分隊為預設範例)
SAMPLE_FEEDBACKS = [
    {
        "unit_name": "臺東大隊 豐田分隊",
        "submitter": "蕭義消隊員",
        "category": "義消福利",
        "content": "請問 116 年預計推動的義消健康檢查專案，是否有規定入隊年資或年齡限制？名額如何分配給各分隊？",
        "contact_info": "公務分機 2119",
        "status": "已回覆",
        "admin_reply": "蕭同仁您好！116 年度健檢專案預計每年提供 300 位名額，規劃優先針對 40 歲以上且出勤率達標之現役義消同仁辦理，詳細名額分配與各特約醫療院所清冊預計於年底前函頒各大隊週知。",
        "created_at": "2026-08-30 09:30:00",
        "replied_at": "2026-08-30 11:00:00"
    },
    {
        "unit_name": "成功大隊 都蘭分隊",
        "submitter": "分隊義消承辦人",
        "category": "補捐助案件",
        "content": "分隊向公所申請辦理常年研習活動補助款，發票黏存單如檢附電子發票證明聯，是否必須請店家登載機關統編？",
        "contact_info": "公務信箱 dulan_fire@ttfd.gov.tw",
        "status": "已回覆",
        "admin_reply": "承辦人您好！電子發票證明聯請務必請店家登載機關統一編號，若為熱感應紙建議影印一份併同正本黏存，以防字跡褪色影響審計核銷。",
        "created_at": "2026-08-30 10:15:00",
        "replied_at": "2026-08-30 13:20:00"
    },
    {
        "unit_name": "關山大隊 池上分隊",
        "submitter": "林分隊長",
        "category": "義消業務",
        "content": "本年度火搶義消消防衣帽鞋配發進度，各分隊預計何時可以送交身材尺寸與型號對照清單？",
        "contact_info": "0912-345-678",
        "status": "處理中",
        "admin_reply": "林分隊長您好！廠商已備料並排定於 11 月辦理驗收，各分隊身材尺寸清冊已請各大隊彙整中，預計本月中旬由科內統一對焦名冊。",
        "created_at": "2026-08-30 14:00:00",
        "replied_at": "2026-08-30 14:45:00"
    },
    {
        "unit_name": "大武大隊 太麻里分隊",
        "submitter": "陳小隊長",
        "category": "訓練業務",
        "content": "請問鳳凰數位學習網之年度線上修課時數，分隊義消同仁完成研習後，何時會統一由系統匯入認證？",
        "contact_info": "公務分機 3119",
        "status": "已回覆",
        "admin_reply": "陳小隊長您好！科內每月初會進行鳳凰數位學習網時數批次勾稽與認證，同仁於線上完成測驗合格後，次月 5 日前即可於訓練系統查得時數。",
        "created_at": "2026-08-30 15:00:00",
        "replied_at": "2026-08-30 16:30:00"
    }
]


def get_db_connection():
    """取得 SQLite 資料庫連線"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(force_reseed=False):
    """初始化資料庫與資料表"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS SystemMeta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

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
        cursor.execute("DELETE FROM SystemMeta")
        conn.commit()

    cursor.execute("SELECT value FROM SystemMeta WHERE key = 'initialized'")
    row = cursor.fetchone()

    if not row:
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

        cursor.execute("INSERT OR REPLACE INTO SystemMeta (key, value) VALUES ('initialized', 'true')")
        conn.commit()

    conn.close()


def get_all_tasks_df() -> pd.DataFrame:
    """取得所有業務資料並轉換為 Pandas DataFrame"""
    init_db()
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM TaskDatabase ORDER BY id ASC", conn)
    conn.close()
    return df



def get_subcategories_list(category=None):
    """取得所有子項目/分項清單 (依業務分類動態取得)"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    if category and category != "全部業務":
        cursor.execute("SELECT DISTINCT subcategory FROM TaskDatabase WHERE category = ? AND subcategory IS NOT NULL AND TRIM(subcategory) != '' ORDER BY subcategory", (category,))
    else:
        cursor.execute("SELECT DISTINCT subcategory FROM TaskDatabase WHERE subcategory IS NOT NULL AND TRIM(subcategory) != '' ORDER BY subcategory")
    subcats = [row[0] for row in cursor.fetchall()]
    conn.close()
    return subcats


def get_owners_list():
    """取得所有獨立承辦人清單 (自動拆分多位承辦人姓名)"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT owner FROM TaskDatabase WHERE owner IS NOT NULL AND TRIM(owner) != ''")
    raw_owners = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    unique_owners = set()
    for o_str in raw_owners:
        split_names = re.split(r'[,、;\s/]+', o_str)
        for name in split_names:
            name = name.strip()
            if name:
                unique_owners.add(name)
    return sorted(list(unique_owners))


def get_tasks_by_filter(category=None, subcategory=None, owner=None, status=None, search_query=None, only_highlight=False):
    """依條件查詢任務清單 (支援子項目篩選與模糊承辦人比對)"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM TaskDatabase WHERE 1=1"
    params = []

    if category and category != "全部業務":
        query += " AND category = ?"
        params.append(category)

    if subcategory and subcategory not in ["全部子項目", "全部分項", "全部項目"]:
        query += " AND subcategory = ?"
        params.append(subcategory)

    if owner and owner != "全部承辦人":
        query += " AND owner LIKE ?"
        params.append(f"%{owner}%")

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
    """永久刪除指定回饋留言"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM FeedbackDatabase WHERE id = ?", (feedback_id,))
    conn.commit()
    conn.close()


def clear_all_feedbacks():
    """清空所有回饋留言"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM FeedbackDatabase")
    conn.commit()
    conn.close()

def clear_gsheet_url():
    """清除 Google 試算表連動網址"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM SystemMeta WHERE key = 'gsheet_url'")
    cursor.execute("DELETE FROM SystemMeta WHERE key = 'last_gsheet_sync'")
    conn.commit()
    conn.close()


def import_tasks_from_df(df: pd.DataFrame, replace_all=True):
    """從上傳的 DataFrame 匯入/還原業務資料表 (100% 智慧對齊中文標頭、英文標頭、防空值與事務安全)"""
    if df is None or df.empty:
        return 0
        
    init_db()
    
    # 智慧欄位對照表 (涵蓋所有常見中文與英文欄位變體)
    col_map = {
        "分類": "category", "業務分類": "category", "類別": "category", "大項": "category", "業務大項": "category",
        "子項目": "subcategory", "分項": "subcategory", "次類別": "subcategory", "業務分項": "subcategory",
        "業務項目名稱": "title", "業務名稱": "title", "標題": "title", "項目名稱": "title", "業務項目": "title",
        "承辦人": "owner", "科內承辦人": "owner", "負責人": "owner", "承辦人員": "owner",
        "執行狀態": "status", "狀態": "status", "辦理狀態": "status",
        "最新異動重點": "update_highlight", "異動重點": "update_highlight", "紅字重點": "update_highlight", "宣導重點": "update_highlight", "最新異動": "update_highlight",
        "詳細工作內容": "content_detail", "SOP": "content_detail", "詳細SOP": "content_detail", "工作內容": "content_detail", "SOP作業指引": "content_detail", "作業指引": "content_detail", "詳細內容": "content_detail",
        "相關連結": "doc_links", "表單連結": "doc_links", "雲端連結": "doc_links", "附件連結": "doc_links", "連結": "doc_links", "表單/雲端連結": "doc_links",
        "最後更新時間": "last_updated", "更新時間": "last_updated"
    }
    
    # 清理標頭前後空白並替換欄位名
    df_clean = df.rename(columns=lambda c: str(c).strip())
    df_clean = df_clean.rename(columns=col_map)
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    valid_rows = []
    
    for _, row in df_clean.iterrows():
        title = ""
        if "title" in row and pd.notna(row["title"]):
            title = str(row["title"]).strip()
        
        # 若仍無 title，嘗試從其他可能的欄位抓取
        if not title:
            for c_name in ["業務項目名稱", "業務名稱", "標題", "title", "項目名稱"]:
                if c_name in row and pd.notna(row[c_name]) and str(row[c_name]).strip():
                    title = str(row[c_name]).strip()
                    break
                    
        # 若該列完全沒有標題，略過該空行
        if not title or title.lower() in ["nan", "none", "null"]:
            continue
            
        cat = str(row.get("category", "")).strip() if pd.notna(row.get("category")) else "義消業務"
        if not cat or cat not in CATEGORIES:
            cat = "義消業務"
            
        subcat = str(row.get("subcategory", "")).strip() if pd.notna(row.get("subcategory")) and str(row.get("subcategory")).strip().lower() not in ["nan", "none", "null"] else ""
        owner = str(row.get("owner", "")).strip() if pd.notna(row.get("owner")) and str(row.get("owner")).strip().lower() not in ["nan", "none", "null"] else ""
        status = str(row.get("status", "常態辦理")).strip() if pd.notna(row.get("status")) and str(row.get("status")).strip().lower() not in ["nan", "none", "null"] else "常態辦理"
        highlight = str(row.get("update_highlight", "")).strip() if pd.notna(row.get("update_highlight")) and str(row.get("update_highlight")).strip().lower() not in ["nan", "none", "null"] else ""
        content = str(row.get("content_detail", "")).strip() if pd.notna(row.get("content_detail")) and str(row.get("content_detail")).strip().lower() not in ["nan", "none", "null"] else ""
        doc_links = str(row.get("doc_links", "")).strip() if pd.notna(row.get("doc_links")) and str(row.get("doc_links")).strip().lower() not in ["nan", "none", "null"] else ""
        updated = str(row.get("last_updated", now_str)).strip() if pd.notna(row.get("last_updated")) and str(row.get("last_updated")).strip().lower() not in ["nan", "none", "null"] else now_str

        valid_rows.append((cat, subcat, title, owner, status, highlight, content, doc_links, updated))
        
    # 事務保護：若 0 筆有效資料，絕對不執行清空資料庫！
    if not valid_rows:
        return 0
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if replace_all:
        cursor.execute("DELETE FROM TaskDatabase")
        
    for r in valid_rows:
        cursor.execute("""
            INSERT INTO TaskDatabase (
                category, subcategory, title, owner, status,
                update_highlight, content_detail, doc_links, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, r)
        
    conn.commit()
    conn.close()
    
    # 同步寫入持久化備份 CSV 檔，確保重開機永久保留
    try:
        csv_persist_path = os.path.join(DB_DIR, "tasks_persistent_backup.csv")
        df_clean.to_csv(csv_persist_path, index=False, encoding="utf-8-sig")
    except Exception:
        pass
        
    return len(valid_rows)


def get_tasks_for_officer(officer_name):
    """取得指定承辦人負責的所有業務項目"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    if not officer_name or officer_name == "全部承辦人":
        cursor.execute("SELECT id, category, subcategory, title, owner, status FROM TaskDatabase ORDER BY category, id")
    else:
        cursor.execute("SELECT id, category, subcategory, title, owner, status FROM TaskDatabase WHERE owner LIKE ? ORDER BY category, id", (f"%{officer_name}%",))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def search_tasks_for_jump(query_str):
    """依關鍵字全文檢索業務項目清單供點擊跳轉"""
    init_db()
    conn = get_db_connection()
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

def get_full_system_data():
    """取得全系統所有資料表之完整資料 (包含業務主表、導航情境表、留言回饋表、系統設定)"""
    init_db()
    conn = get_db_connection()
    tasks_df = pd.read_sql_query("SELECT * FROM TaskDatabase ORDER BY id ASC", conn)
    guides_df = pd.read_sql_query("SELECT * FROM GuideDatabase ORDER BY id ASC", conn)
    feedbacks_df = pd.read_sql_query("SELECT * FROM FeedbackDatabase ORDER BY id ASC", conn)
    conn.close()
    
    return {
        "tasks": tasks_df.to_dict(orient="records"),
        "guides": guides_df.to_dict(orient="records"),
        "feedbacks": feedbacks_df.to_dict(orient="records"),
        "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "organization": "臺東縣消防局民力訓練科"
    }


def sync_tasks_from_google_sheet(sheet_url):
    """從 Google 試算表 (Google Sheets) 連結即時同步業務資料表 (支援多種 Google 連結與發布端點)"""
    import urllib.request
    import io
    import re
    
    init_db()
    if not sheet_url or not sheet_url.strip():
        return False, 0, "請輸入有效的 Google 試算表連結！"
    
    clean_url = sheet_url.strip()
    target_urls = []
    
    # 策略 1: 發布到網路 CSV 連結
    if "output=csv" in clean_url or "format=csv" in clean_url:
        target_urls.append(clean_url)
        
    # 策略 2: Google 試算表連結 (docs.google.com/spreadsheets/d/ID/...)
    if "docs.google.com/spreadsheets/d/" in clean_url:
        match = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", clean_url)
        if match:
            s_id = match.group(1)
            target_urls.extend([
                f"https://docs.google.com/spreadsheets/d/{s_id}/export?format=csv",
                f"https://docs.google.com/spreadsheets/d/{s_id}/gviz/tq?tqx=out:csv"
            ])
            
    # 策略 3: Google 雲端硬碟檔案連結 (drive.google.com/file/d/ID/...)
    if "drive.google.com/file/d/" in clean_url:
        match = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", clean_url)
        if match:
            f_id = match.group(1)
            target_urls.extend([
                f"https://docs.google.com/spreadsheets/d/{f_id}/export?format=csv",
                f"https://docs.google.com/spreadsheets/d/{f_id}/gviz/tq?tqx=out:csv",
                f"https://drive.google.com/uc?export=download&id={f_id}",
                f"https://drive.usercontent.google.com/download?id={f_id}&export=download"
            ])
            
    if not target_urls:
        target_urls.append(clean_url)
        
    df = None
    last_error = ""
    
    for t_url in target_urls:
        try:
            req = urllib.request.Request(t_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                raw_bytes = resp.read()
                
                # 若回傳 HTML 網頁內容表示非直接 CSV，略過換下一個端點
                if raw_bytes.strip().startswith(b"<!DOCTYPE") or raw_bytes.strip().startswith(b"<html"):
                    continue
                    
                # 嘗試以 utf-8 或 cp950 解析
                try:
                    df = pd.read_csv(io.BytesIO(raw_bytes), encoding="utf-8-sig")
                except Exception:
                    df = pd.read_csv(io.BytesIO(raw_bytes), encoding="utf-8")
                break
        except Exception as e:
            last_error = str(e)
            continue
            
    if df is None or df.empty:
        return False, 0, (
            "無法直接讀取該連結！\n"
            "💡 最佳解決方法（只要 1 步）：\n"
            "請在您的 Google 試算表中，點擊上方選單【檔案】➔【共用】➔【發布到網路】➔ 選擇【逗號分隔值 (.csv)】➔ 點【發布】，並將產生的網址貼在此處，即可 100% 成功連動！"
        )
        
    # 智慧欄位對照轉換
    col_map = {
        "分類": "category", "業務分類": "category",
        "子項目": "subcategory", "分項": "subcategory",
        "業務項目名稱": "title", "業務名稱": "title", "標題": "title",
        "承辦人": "owner", "科內承辦人": "owner",
        "執行狀態": "status", "狀態": "status",
        "最新異動重點": "update_highlight", "異動重點": "update_highlight", "紅字重點": "update_highlight",
        "詳細工作內容": "content_detail", "SOP": "content_detail", "詳細SOP": "content_detail", "工作內容": "content_detail",
        "相關連結": "doc_links", "表單連結": "doc_links", "雲端連結": "doc_links", "附件連結": "doc_links"
    }
    df = df.rename(columns=col_map)
    
    if "title" not in df.columns:
        return False, 0, "試算表中找不到「業務項目名稱」或「title」欄位，請檢查試算表標頭！"
        
    count = import_tasks_from_df(df, replace_all=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO SystemMeta (key, value) VALUES ('gsheet_url', ?)", (sheet_url.strip(),))
    cursor.execute("INSERT OR REPLACE INTO SystemMeta (key, value) VALUES ('last_gsheet_sync', ?)", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
    conn.commit()
    conn.close()
    
    return True, count, "同步成功"


def get_gsheet_sync_info():
    """取得 Google 試算表同步設定資訊"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM SystemMeta WHERE key = 'gsheet_url'")
    row_url = cursor.fetchone()
    url = row_url[0] if row_url else ""
    
    cursor.execute("SELECT value FROM SystemMeta WHERE key = 'last_gsheet_sync'")
    row_time = cursor.fetchone()
    sync_time = row_time[0] if row_time else "尚未同步"
    conn.close()
    return url, sync_time

def auto_sync_from_gsheet():
    """若系統有綁定 Google 試算表，自動進行即時背景同步"""
    url, _ = get_gsheet_sync_info()
    if url and url.strip():
        try:
            sync_tasks_from_google_sheet(url)
        except Exception:
            pass

def import_full_system_from_json(json_obj):
    """從全系統備份包 (JSON) 一次性完全還原全系統三大資料表 (業務表、導航情境表、同仁留言表)"""
    if not json_obj or not isinstance(json_obj, dict):
        return False, "無效的備份檔案格式！"
        
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    t_count = 0
    g_count = 0
    f_count = 0
    
    # 1. 還原 TaskDatabase
    if "tasks" in json_obj and isinstance(json_obj["tasks"], list):
        cursor.execute("DELETE FROM TaskDatabase")
        for t in json_obj["tasks"]:
            cursor.execute("""
                INSERT INTO TaskDatabase (
                    category, subcategory, title, owner, status,
                    update_highlight, content_detail, doc_links, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                t.get("category", "義消業務"),
                t.get("subcategory", ""),
                t.get("title", ""),
                t.get("owner", ""),
                t.get("status", "常態辦理"),
                t.get("update_highlight", ""),
                t.get("content_detail", ""),
                t.get("doc_links", ""),
                t.get("last_updated", "")
            ))
            t_count += 1
            
    # 2. 還原 GuideDatabase
    if "guides" in json_obj and isinstance(json_obj["guides"], list):
        cursor.execute("DELETE FROM GuideDatabase")
        for g in json_obj["guides"]:
            cursor.execute("""
                INSERT INTO GuideDatabase (
                    scenario_num, title, icon, target_badge, description, linked_task_titles
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                g.get("scenario_num", 1),
                g.get("title", ""),
                g.get("icon", "📌"),
                g.get("target_badge", ""),
                g.get("description", ""),
                g.get("linked_task_titles", "")
            ))
            g_count += 1
            
    # 3. 還原 FeedbackDatabase
    if "feedbacks" in json_obj and isinstance(json_obj["feedbacks"], list):
        cursor.execute("DELETE FROM FeedbackDatabase")
        for fb in json_obj["feedbacks"]:
            cursor.execute("""
                INSERT INTO FeedbackDatabase (
                    unit_name, submitter, category, content, contact_info,
                    status, admin_reply, replied_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fb.get("unit_name", ""),
                fb.get("submitter", ""),
                fb.get("category", "其他問題"),
                fb.get("content", ""),
                fb.get("contact_info", ""),
                fb.get("status", "待處理"),
                fb.get("admin_reply", ""),
                fb.get("replied_at", ""),
                fb.get("created_at", "")
            ))
            f_count += 1
            
    conn.commit()
    conn.close()
    
    return True, f"已成功還原：{t_count} 筆業務、{g_count} 筆情境導航、{f_count} 筆同仁留言紀錄！"

def get_top_latest_highlights(limit=3):
    """取得最新更新且具異動重點的前 N 項業務公告"""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, category, subcategory, title, owner, status, update_highlight, last_updated
        FROM TaskDatabase
        WHERE update_highlight IS NOT NULL AND TRIM(update_highlight) != ''
        ORDER BY last_updated DESC, id DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
