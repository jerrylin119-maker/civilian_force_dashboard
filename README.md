# 🚒 民力科業務知識動態看板
> **Civilian & Volunteer Force Division Management & Knowledge Portal**  
> 基於 Python (Streamlit + SQLite) 開發的民力科業務推動、知識傳承與最新異動重點動態看板。

---

## 🌟 系統亮點特色

1. **5 大業務分類分頁**：
   - 【🚒 義消業務】（承辦：廖昱翔科員、林威宇小隊長）
   - 【🎁 義消福利】（承辦：陳怡忻分隊長）
   - 【💰 補捐助業務】（承辦：廖昱翔科員、林威宇小隊長）
   - 【🎯 訓練業務】（承辦：尤仁宏秘書）
   - 【🌟 其他推動業務】（彈性自訂）
   - 【📊 全部總覽】（全域動態與宣導通報）
2. **⚠️ 最新異動重點動態高亮**：
   - 包含中程計畫核銷期程、消防衣帽鞋 11 月驗收配發、116 年健檢專案（每年 300 名額）、補捐助範例顏色區別更新等。
3. **無痛 Excel 式線上即時編輯 (`st.data_editor`)**：
   - 承辦人點擊開啟「科內維護模式」（預設密碼：`119`），即可直接在表格雙擊修改文字、承辦人或最新異動，點擊「儲存」一鍵批次同步至 SQLite。
4. **💰 補捐助專案管理與顏色標記指引**：
   - 義消申請縣府及鄉鎮公所補助案件管制作業，申請範例隨時間更新並以顏色區別。
5. **完整 SOP 知識庫與雲端系統超連結**：
   - 整合義消專長資料庫、福利互助系統、補捐助系統、鳳凰數位學習網等線上管道。

---

## 🚀 本地快速啟動指引

### 步驟 1：安裝 Python 套件
```bash
pip install -r requirements.txt
```

### 步驟 2：啟動看板
```bash
streamlit run app.py
```
*(Windows 下可直接雙擊 `run.bat` 自動開啟)*

瀏覽器網址：`http://localhost:8501`

---

## 🐙 上架 GitHub 與 Git 隨時更新教學

### 第一次上傳至 GitHub 步驟：
1. 在 GitHub 上建立一個新的儲存庫（Repository），例如命名為 `civilian_force_dashboard`（設為 Public 或 Private 皆可，**不要**勾選 Initialize with README）。
2. 在本機專案目錄下開啟終端機（PowerShell / CMD），依序執行以下指令：
```bash
# 初始化 Git 儲存庫
git init

# 將所有專案檔案加入版本控制
git add .

# 建立初次提交
git commit -m "feat: 初次發布民力科業務知識動態看板"

# 將預設分支命名為 main
git branch -M main

# 連結遠端 GitHub 儲存庫（請將 YOUR_USERNAME 與 REPO_NAME 替換成您的 GitHub 網址）
git remote add origin https://github.com/YOUR_USERNAME/civilian_force_dashboard.git

# 推送至 GitHub
git push -u origin main
```

---

### 日後「隨時一鍵更新到 GitHub」指令：
當您在本地修改完程式碼、新增 SOP 或更新資料後，只需在終端機執行：
```bash
git add .
git commit -m "update: 更新民力科業務知識與最新異動"
git push
```
*(亦可直接點擊專案目錄下的 `git_push.bat` 自動提交並推送！)*

---

### 從 GitHub 同步最新版本至本機：
```bash
git pull
```
*(亦可直接點擊 `git_pull.bat` 自動拉取最新版本！)*

---

## 🔐 科內維護模式說明
- **預設密碼**：`119` (亦相容 `admin119` 或 `minli119`)
- 登入後可於側邊欄或分頁使用：
  1. **Excel 式線上即時編輯**
  2. **新增業務項目**
  3. **單筆詳細維護與刪除**
  4. **資料庫一鍵重設為官方清單**
