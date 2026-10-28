"""案件登錄與管制（取代雲端表單 + 手動填寫）。

表格結構與現行「115年議員補助款一覽表 (回覆)」完全一致：同樣的欄位順序、同樣的兩列標題。
所以這個模組以「欄位位置」讀寫（標題有重複，例如兩個「審核結果」），連線時會逐欄核對標題，
對不上就拒絕寫入，不會悄悄寫錯欄。

分層：
  - 欄位與階段定義（FIELDS、STAGES）：誰能改哪幾欄
  - 儲存層（MemoryStore / SheetStore）：只管讀整張表、附加一列、改幾格。換成資料庫只要換這一層
  - 案件邏輯（CaseRegistry）：編號、驗證、依角色寫入、狀態判斷、異動紀錄
這個檔案不依賴 Streamlit，可以直接做單元測試。
"""
from __future__ import annotations

import hashlib
import hmac
import re
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8))

HEADER_ROWS = 2          # 第 1 列：分組標題；第 2 列：欄位標題；資料從第 3 列開始
LOG_SHEET_NAME = "異動紀錄"
LOG_HEADERS = ["時間", "案件編號", "帳號", "角色", "階段", "異動內容", "來源"]

# ---------------------------------------------------------------- 角色與階段
ROLE_UNIT = "unit"            # 分隊承辦人
ROLE_BATTALION = "battalion"  # 大隊
ROLE_SECTION = "section"      # 業務科室
ROLE_LABELS = {ROLE_UNIT: "分隊", ROLE_BATTALION: "大隊", ROLE_SECTION: "業務科室"}

# 欄位：key -> (欄位位置 0 起算, 標題開頭, 階段)
# 「標題開頭」只用來核對，取標題去掉空白後的前幾個字即可。
FIELDS = {
    "timestamp":      (1,  "時間戳記",     "submit"),
    "battalion":      (2,  "所屬大隊",     "submit"),
    "unit":           (3,  "承辦單位",     "submit"),
    "officer":        (4,  "承辦人",       "submit"),
    "purpose":        (5,  "經費用途",     "submit"),
    "plan_name":      (6,  "計畫名稱",     "submit"),
    "date_start":     (7,  "活動日期(始)", "submit"),
    "date_end":       (8,  "活動日期(末)", "submit"),
    "total":          (9,  "計畫總經費概算", "submit"),
    "applied":        (10, "爭取經費",     "submit"),
    "source_kind":    (11, "補助款來源",   "submit"),
    "source_detail":  (12, "補助款來源細項", "submit"),
    "first_result":   (13, "審核結果",     "first_review"),
    "first_by":       (14, "審核人員",     "first_review"),
    "received":       (15, "收件",         "second_review"),
    "received_at":    (16, "收件",         "second_review"),
    "section_dept":   (17, "承辦科室",     "second_review"),
    "section_officer": (18, "承辦人",      "second_review"),
    "apply_doc_no":   (19, "申請補助",     "second_review"),
    "approve_status": (20, "補助單位",     "reply"),
    "approve_no":     (21, "核准案號",     "reply"),
    "approve_amount": (22, "核准金額",     "reply"),
    "letter_back":    (23, "核准函是否",   "reply"),
    "settle_first_result": (24, "審核結果", "settle_first"),
    "settle_first_by": (25, "審核人員",    "settle_first"),
    "settle_doc_no":  (26, "核銷",         "settle_second"),
    "settle_amount":  (27, "核銷金額",     "settle_second"),
    "settle_status":  (28, "核銷進度",     "settle_second"),
    "note":           (29, "備註",         "note"),
    "no_defect":      (30, "審查無缺失",   "defect"),
    "defect":         (31, "簡寫缺失",     "defect"),
    "case_no":        (32, "案件編號",     "system"),   # 新增在最後一欄（AG）
}
N_COLS = 33

STAGE_LABELS = {
    "submit": "① 登錄",
    "first_review": "② 申請初審",
    "second_review": "③ 申請複審",
    "reply": "④ 回覆進度",
    "settle_first": "⑤ 核銷初審",
    "settle_second": "⑥ 核銷複審",
    "note": "備註",
    "defect": "缺失登記",
}
# 哪個角色能編輯哪個階段（大隊的審核只限自己所屬大隊的案件，見 can_edit）
STAGE_ROLES = {
    "submit": {ROLE_UNIT, ROLE_BATTALION},   # 分隊登錄；大隊也可登錄大隊本身的案件
    "first_review": {ROLE_BATTALION, ROLE_SECTION},
    "second_review": {ROLE_SECTION},
    "reply": {ROLE_SECTION, ROLE_BATTALION},
    "settle_first": {ROLE_BATTALION, ROLE_SECTION},
    "settle_second": {ROLE_SECTION},
    "note": {ROLE_BATTALION, ROLE_SECTION},
    "defect": {ROLE_SECTION},
}
# 前一階段要先完成才能進下一階段：階段 -> (欄位, 必須等於)
STAGE_PREREQ = {
    "second_review": ("first_result", "通過"),
    "reply": ("received", True),
    "settle_first": ("approve_status", "已核准"),
    "settle_second": ("settle_first_result", "通過"),
}

BOOL_FIELDS = {"received", "no_defect"}   # 試算表裡存 TRUE / FALSE（勾選方塊）

ADMIN_LOGINS = {"民力訓練科"}
# 這些階段的資料屬於「承辦科室」，收件後只有該科室（或民力訓練科）能改
DEPT_STAGES = {"second_review", "reply", "settle_second", "defect"}

FIRST_REVIEW_RESULTS =["通過", "退回分隊修正"]
PURPOSES = ["設備費", "活動費"]

BATTALION_CODES = {
    "台東大隊": "台", "關山大隊": "關", "成功大隊": "成", "大武大隊": "武",
}
BATTALIONS = list(BATTALION_CODES)

CASE_NO_RE = re.compile(r"^(\d{3})-(.)-(\d{4})$")


# ---------------------------------------------------------------- 小工具
def _clean(v):
    return "" if v is None else str(v).strip()


FIELD_LABELS = {k: re.split(r"[\s(（]", head)[0] for k, (_i, head, _s) in FIELDS.items()}
FIELD_LABELS.update({"first_result": "初審結果", "first_by": "初審人員", "received": "收件", "received_at": "收件時間",
                     "section_officer": "科室承辦人", "settle_first_result": "核銷初審結果",
                     "settle_first_by": "核銷初審人員", "settle_doc_no": "核銷發文字號",
                     "apply_doc_no": "申請發文字號", "approve_status": "核准進度", "approve_no": "核准案號",
                     "approve_amount": "核准金額", "letter_back": "核准函回寄", "applied": "爭取經費",
                     "total": "總經費", "source_detail": "來源細項"})


def _norm_header(text):
    return re.sub(r"\s+", "", _clean(text))


def now_text(now=None):
    n = now or datetime.now(TZ)
    return f"{n.year}/{n.month}/{n.day} {n:%H:%M:%S}"


def date_text(d):
    if isinstance(d, (date, datetime)):
        return f"{d.year}/{d.month}/{d.day}"
    return _clean(d)


def to_int(v):
    s = re.sub(r"[,\s]", "", _clean(v))
    if not s:
        return 0
    try:
        return int(round(float(s)))
    except ValueError:
        return 0


def roc_year(d=None):
    d = d or date.today()
    return d.year - 1911


# ---------------------------------------------------------------- 帳號
PBKDF2_ROUNDS = 120_000   # 測試時會調低；正式環境不要改


def hash_password(password, salt=None):
    """產生 'salt$hash' 格式，放進 Streamlit Secrets，不要放明碼。"""
    import os
    salt = salt or os.urandom(8).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ROUNDS).hex()
    return f"{salt}${digest}"


def verify_password(password, stored):
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


@dataclass
class Account:
    login: str
    role: str
    display: str = ""
    battalion: str = ""   # 分隊與大隊帳號所屬大隊；科室帳號留空
    unit: str = ""        # 分隊帳號的單位名稱；科室帳號是科室全名（寫進「承辦科室」欄）
    password_hash: str = ""
    must_change: bool = False   # 還在用預設密碼

    @property
    def label(self):
        return self.display or self.login

    @property
    def is_admin(self):
        """民力訓練科：可處理所有科室的案件、重設帳號密碼。"""
        return self.role == ROLE_SECTION and self.login in ADMIN_LOGINS


def load_accounts(rows):
    """rows：Secrets 裡的帳號清單（list of dict）。壞資料略過。"""
    out = {}
    for r in rows or []:
        try:
            login = _clean(r.get("login"))
            role = _clean(r.get("role"))
        except AttributeError:
            continue
        if not login or role not in ROLE_LABELS or not _clean(r.get("password_hash")):
            continue
        out[login] = Account(login=login, role=role, display=_clean(r.get("display")),
                             battalion=_clean(r.get("battalion")), unit=_clean(r.get("unit")),
                             password_hash=_clean(r.get("password_hash")))
    return out


def authenticate(accounts, login, password):
    acct = accounts.get(_clean(login))
    # 帳號不存在也做一次雜湊，避免從回應時間猜出帳號
    stored = acct.password_hash if acct else "00$" + "0" * 64
    ok = verify_password(password or "", stored)
    return acct if (acct and ok) else None


# ---------------------------------------------------------------- 儲存層
class StoreError(Exception):
    pass


class BaseStore:
    """子類別只需實作四個方法。rows 是整張表（含兩列標題），每列是字串 list。"""

    def read_all(self):
        raise NotImplementedError

    def append_row(self, values):
        raise NotImplementedError

    def write_cells(self, row_no, cells):
        """row_no 是 1 起算的列號；cells 是 {欄位位置(0 起算): 值}。"""
        raise NotImplementedError

    def append_log(self, values):
        raise NotImplementedError

    def read_log(self, limit=200):
        return []

    # 其他工作表（例如「帳號」）：整張很小，直接整張讀寫
    def read_tab(self, name):
        """回傳含標題列的所有列；工作表不存在回傳 []。"""
        raise NotImplementedError

    def append_tab_rows(self, name, headers, rows):
        """工作表不存在就建立（寫入標題）；再附加 rows。"""
        raise NotImplementedError

    def update_tab_cells(self, name, row_no, cells):
        raise NotImplementedError


class MemoryStore(BaseStore):
    """測試與示範用，資料不保存。標題與正式表一致。"""

    def __init__(self, header_row=None):
        self.rows = [[""] * N_COLS, list(header_row or standard_header_row())]
        self.log = [list(LOG_HEADERS)]
        self.tabs = {}

    def read_tab(self, name):
        return [list(r) for r in self.tabs.get(name, [])]

    def append_tab_rows(self, name, headers, rows):
        tab = self.tabs.setdefault(name, [list(headers)])
        tab.extend([_clean(v) for v in r] for r in rows)

    def update_tab_cells(self, name, row_no, cells):
        row = self.tabs[name][row_no - 1]
        for idx, val in cells.items():
            while len(row) <= idx:
                row.append("")
            row[idx] = _clean(val)

    def read_all(self):
        return [list(r) for r in self.rows]

    def append_row(self, values):
        self.rows.append([_clean(v) for v in values])
        return len(self.rows)

    def write_cells(self, row_no, cells):
        while len(self.rows) < row_no:
            self.rows.append([""] * N_COLS)
        row = self.rows[row_no - 1]
        for idx, val in cells.items():
            while len(row) <= idx:
                row.append("")
            row[idx] = _clean(val)

    def append_log(self, values):
        self.log.append([_clean(v) for v in values])

    def read_log(self, limit=200):
        return [dict(zip(LOG_HEADERS, r)) for r in self.log[1:][-limit:]]


class SheetStore(BaseStore):
    """Google 試算表。需要服務帳號，且試算表已分享給該帳號（編輯者）。"""

    def __init__(self, spreadsheet_id, worksheet_name, service_account_info):
        try:
            import gspread
        except ImportError as exc:  # pragma: no cover
            raise StoreError("缺少 gspread 套件，請確認 requirements.txt") from exc
        try:
            client = gspread.service_account_from_dict(dict(service_account_info))
            self.book = client.open_by_key(spreadsheet_id)
            self.ws = self.book.worksheet(worksheet_name)
        except Exception as exc:
            raise StoreError(f"無法連到試算表：{type(exc).__name__}") from exc
        self._log_ws = None

    def read_all(self):
        # 表單預先放了到數萬列的勾選方塊，整張讀會很慢；只讀到「所屬大隊」欄（C）最後有字的那一列
        last = max(len(self.ws.col_values(3)), HEADER_ROWS)
        return self.ws.get(f"A1:{_col_letter(N_COLS - 1)}{last}")

    def append_row(self, values):
        res = self.ws.append_row(values, value_input_option="USER_ENTERED",
                                 insert_data_option="INSERT_ROWS", table_range="A1")
        rng = (res.get("updates") or {}).get("updatedRange", "")
        m = re.search(r"!\D+(\d+)", rng)
        if not m:
            raise StoreError("寫入後無法確認列號")
        return int(m.group(1))

    def write_cells(self, row_no, cells):
        from gspread.utils import rowcol_to_a1
        data = [{"range": rowcol_to_a1(row_no, idx + 1), "values": [[val]]} for idx, val in cells.items()]
        self.ws.batch_update(data, value_input_option="USER_ENTERED")

    def _log(self):
        if self._log_ws is None:
            try:
                self._log_ws = self.book.worksheet(LOG_SHEET_NAME)
            except Exception:
                self._log_ws = self.book.add_worksheet(LOG_SHEET_NAME, rows=2000, cols=len(LOG_HEADERS))
                self._log_ws.append_row(LOG_HEADERS)
        return self._log_ws

    def append_log(self, values):
        self._log().append_row(values, value_input_option="RAW")

    def read_log(self, limit=200):
        rows = self._log().get_all_values()[1:][-limit:]
        return [dict(zip(LOG_HEADERS, r)) for r in rows]

    def _tab(self, name, headers=None):
        import gspread
        try:
            return self.book.worksheet(name)
        except gspread.WorksheetNotFound:
            if headers is None:
                return None
            ws = self.book.add_worksheet(name, rows=500, cols=len(headers))
            ws.append_row(headers, value_input_option="RAW")
            return ws

    def read_tab(self, name):
        ws = self._tab(name)
        return ws.get_all_values() if ws else []

    def append_tab_rows(self, name, headers, rows):
        ws = self._tab(name, headers)
        if rows:
            ws.append_rows([list(r) for r in rows], value_input_option="RAW")

    def update_tab_cells(self, name, row_no, cells):
        from gspread.utils import rowcol_to_a1
        ws = self._tab(name)
        data = [{"range": rowcol_to_a1(row_no, idx + 1), "values": [[val]]} for idx, val in cells.items()]
        ws.batch_update(data, value_input_option="RAW")


def standard_header_row():
    row = [""] * N_COLS
    for _key, (idx, head, _stage) in FIELDS.items():
        row[idx] = head
    return row


# ---------------------------------------------------------------- 案件邏輯
@dataclass
class Case:
    row_no: int
    values: dict = field(default_factory=dict)

    def __getitem__(self, key):
        return self.values.get(key, "")

    @property
    def case_no(self):
        return self["case_no"]

    @property
    def status(self):
        return case_status(self)


def case_status(case):
    """由各階段欄位推出目前進度（不另存，避免與欄位不一致）。"""
    if _clean(case["settle_status"]):
        s = _clean(case["settle_status"])
        return "已結案" if s == "已函發" else f"核銷：{s}"
    r = _clean(case["settle_first_result"])
    if r == "通過":
        return "核銷複審中"
    if r:
        return "核銷退回分隊修正" if "退回" in r else f"核銷初審：{r}"
    if _clean(case["approve_status"]):
        return _clean(case["approve_status"])
    if _truthy(case["received"]):
        return "申請複審中（已收件）"
    fr = _clean(case["first_result"])
    if fr == "通過":
        return "待業務科收件"
    if fr:
        return "退回分隊修正" if "退回" in fr else fr
    return "待大隊初審"


def _bool_cols():
    return {FIELDS[k][0] for k in BOOL_FIELDS}


def row_has_data(row):
    """這一列是否真的有案件資料。勾選方塊（P、AE 欄）預先填了 FALSE，不算。"""
    skip = _bool_cols()
    return any(_clean(c) for i, c in enumerate(row) if i >= 1 and i not in skip)


def _truthy(v):
    return v is True or _clean(v).upper() in ("TRUE", "V", "是", "1")


def cr_pending(case):
    return pending_for(case)


def pending_for(case):
    """這件案子現在輪到誰：unit / battalion / section / None（已結案）。"""
    st = case_status(case)
    if st == "已結案":
        return None
    if st.startswith("退回") or st == "核銷退回分隊修正":
        return ROLE_UNIT
    if st == "待大隊初審" or (st == "已核准" and not _clean(case["settle_first_result"])):
        return ROLE_BATTALION
    return ROLE_SECTION


class RegistryError(Exception):
    """給使用者看的錯誤訊息（驗證失敗、沒權限、順序不對）。"""


class CaseRegistry:
    _lock = threading.Lock()

    def __init__(self, store, today=None):
        self.store = store
        self._today = today

    # ---- 讀取
    def check_layout(self):
        """核對標題列；回傳錯誤訊息清單（空表示沒問題）。"""
        rows = self.store.read_all()
        if len(rows) < HEADER_ROWS:
            return ["試算表沒有標題列（需要兩列標題）"]
        head = rows[HEADER_ROWS - 1]
        group = rows[0]   # 備註、審查無缺失、簡寫缺失三欄的標題是第 1、2 列合併，文字在第 1 列
        problems = []
        for key, (idx, expect, _stage) in FIELDS.items():
            cell = head[idx] if idx < len(head) else ""
            if not _norm_header(cell) and idx < len(group):
                cell = group[idx]
            actual = _norm_header(cell)
            if not actual.startswith(_norm_header(expect)):
                where = _col_letter(idx)
                problems.append(f"{where} 欄標題應為「{expect}」，目前是「{actual or '（空白）'}」")
        return problems

    def cases(self):
        rows = self.store.read_all()
        out = []
        for i, row in enumerate(rows[HEADER_ROWS:], start=HEADER_ROWS + 1):
            if not row_has_data(row):
                continue
            vals = {k: (row[idx] if idx < len(row) else "") for k, (idx, _h, _s) in FIELDS.items()}
            out.append(Case(i, vals))
        return out

    def get(self, case_no):
        for c in self.cases():
            if c.case_no == case_no:
                return c
        return None

    # ---- 編號
    def next_case_no(self, battalion, year=None, cases=None):
        code = BATTALION_CODES.get(battalion)
        if not code:
            raise RegistryError(f"不認得的大隊：{battalion}")
        yy = f"{year or roc_year(self._today):03d}"
        seq = 0
        for c in (cases if cases is not None else self.cases()):
            m = CASE_NO_RE.match(c.case_no)
            if m and m.group(1) == yy and m.group(2) == code:
                seq = max(seq, int(m.group(3)))
        return f"{yy}-{code}-{seq + 1:04d}"

    # ---- 權限
    def can_edit(self, account, stage, case=None):
        if account.role not in STAGE_ROLES.get(stage, ()):
            return False
        if account.role in (ROLE_UNIT, ROLE_BATTALION) and case is not None:
            if account.battalion and case["battalion"] != account.battalion:
                return False
            if account.role == ROLE_UNIT and account.unit and case["unit"] != account.unit:
                return False
        if account.role == ROLE_SECTION and case is not None and stage in DEPT_STAGES:
            dept = _clean(case["section_dept"])
            if dept and not account.is_admin and account.unit != dept:
                return False
        return True

    def is_mine(self, account, case):
        """這件案子現在是否輪到這個帳號處理（用於「輪到我處理」）。"""
        if cr_pending(case) != account.role:
            return False
        if account.role == ROLE_SECTION:
            dept = _clean(case["section_dept"])
            return not dept or account.is_admin or account.unit == dept
        return self.can_edit(account, "first_review" if account.role == ROLE_BATTALION else "submit", case)

    # ---- 登錄
    def validate_submission(self, data):
        errs = []
        for key, label in (("battalion", "所屬大隊"), ("unit", "承辦單位"), ("officer", "承辦人"),
                           ("purpose", "經費用途"), ("plan_name", "計畫名稱"),
                           ("source_detail", "補助款來源細項")):
            if not _clean(data.get(key)):
                errs.append(f"請填寫「{label}」")
        if _clean(data.get("battalion")) and data["battalion"] not in BATTALION_CODES:
            errs.append("所屬大隊不在清單內")
        if _clean(data.get("purpose")) and data["purpose"] not in PURPOSES:
            errs.append("經費用途請選設備費或活動費")
        total, applied = to_int(data.get("total")), to_int(data.get("applied"))
        if applied <= 0:
            errs.append("爭取經費要大於 0")
        if total <= 0:
            errs.append("計畫總經費概算要大於 0")
        elif applied > total:
            errs.append("爭取經費不能大於計畫總經費")
        ds, de = _clean(data.get("date_start")), _clean(data.get("date_end"))
        if data.get("purpose") == "活動費":
            if not ds or not de:
                errs.append("活動費案件要填活動日期（始、末）")
        if ds and de:
            a, b = _parse_date(ds), _parse_date(de)
            if a and b and b < a:
                errs.append("活動日期（末）不能早於（始）")
        return errs

    def submit(self, account, data, source="手動填寫"):
        if not self.can_edit(account, "submit"):
            raise RegistryError("這個帳號不能登錄案件")
        data = dict(data)
        if account.role == ROLE_UNIT:      # 分隊只能登錄自己單位
            data["battalion"], data["unit"] = account.battalion or data.get("battalion"), account.unit or data.get("unit")
        errs = self.validate_submission(data)
        if errs:
            raise RegistryError("；".join(errs))
        problems = self.check_layout()
        if problems:
            raise RegistryError("試算表欄位與預期不一致，已停止寫入：" + "；".join(problems[:3]))
        with self._lock:
            cases = self.cases()
            case_no = self.next_case_no(data["battalion"], cases=cases)
            vals = {
                "timestamp": now_text(), "battalion": data["battalion"], "unit": data["unit"],
                "officer": data["officer"], "purpose": data["purpose"], "plan_name": data["plan_name"],
                "date_start": date_text(data.get("date_start")), "date_end": date_text(data.get("date_end")),
                "total": to_int(data.get("total")), "applied": to_int(data.get("applied")),
                "source_kind": _clean(data.get("source_kind")), "source_detail": data["source_detail"],
                "case_no": case_no,
            }
            rows = self.store.read_all()
            row_no = next((i for i, r in enumerate(rows[HEADER_ROWS:], start=HEADER_ROWS + 1)
                           if not row_has_data(r)), len(rows) + 1)
            # 只寫有值的格子，不動預先放好的勾選方塊
            self.store.write_cells(row_no, {FIELDS[k][0]: v for k, v in vals.items() if _clean(v) != ""})
            written = self.store.read_all()
            mine = written[row_no - 1] if len(written) >= row_no else []
            if (mine[FIELDS["case_no"][0]] if len(mine) > FIELDS["case_no"][0] else "") != case_no:
                raise RegistryError("寫入後核對不到剛登錄的案件，請重新整理確認是否已登錄，不要重複送出。")
            # 同時間兩人登錄時，確認自己的編號沒有被別人佔用
            dupes = [c for c in self.cases() if c.case_no == case_no]
            if len(dupes) > 1:
                case_no = self.next_case_no(data["battalion"], cases=[c for c in self.cases() if c.row_no != row_no])
                self.store.write_cells(row_no, {FIELDS["case_no"][0]: case_no})
        self._log(account, case_no, "submit", {k: vals[k] for k in ("plan_name", "applied")}, source)
        return case_no

    # ---- 各階段更新
    def update_stage(self, account, case_no, stage, changes):
        case = self.get(case_no)
        if case is None:
            raise RegistryError(f"找不到案件 {case_no}")
        if stage == "submit":
            raise RegistryError("登錄資料請用修改功能")
        if not self.can_edit(account, stage, case):
            raise RegistryError(f"您的帳號（{ROLE_LABELS[account.role]}）不能編輯「{STAGE_LABELS.get(stage, stage)}」，或這不是您所屬的案件")
        pre = STAGE_PREREQ.get(stage)
        if pre:
            field_key, need = pre
            have = _truthy(case[field_key]) if need is True else _clean(case[field_key])
            if have != need:
                raise RegistryError(f"「{STAGE_LABELS[stage]}」要等前一階段完成（目前狀態：{case.status}）")
        allowed = {k for k, (_i, _h, s) in FIELDS.items() if s == stage}
        bad = set(changes) - allowed
        if bad:
            raise RegistryError("欄位不屬於這個階段：" + "、".join(sorted(bad)))
        clean = {}
        for k, v in changes.items():
            if k in BOOL_FIELDS:
                v = "TRUE" if _truthy(v) else "FALSE"
            clean[k] = _clean(v)
        if stage == "first_review" or stage == "settle_first":
            res_key = "first_result" if stage == "first_review" else "settle_first_result"
            by_key = "first_by" if stage == "first_review" else "settle_first_by"
            if clean.get(res_key) not in FIRST_REVIEW_RESULTS + [""]:
                raise RegistryError("審核結果只能是「通過」或「退回分隊修正」")
            if clean.get(res_key) and not clean.get(by_key):
                clean[by_key] = account.label
        if stage == "second_review" and clean.get("received") == "TRUE":
            if not clean.get("received_at"):
                clean["received_at"] = now_text()
            if not clean.get("section_dept") and account.unit:
                clean["section_dept"] = account.unit
        before = {k: case[k] for k in clean}
        diff = {k: v for k, v in clean.items() if _clean(before[k]) != v}
        if not diff:
            return {}
        problems = self.check_layout()
        if problems:
            raise RegistryError("試算表欄位與預期不一致，已停止寫入：" + "；".join(problems[:3]))
        with self._lock:
            self.store.write_cells(case.row_no, {FIELDS[k][0]: v for k, v in diff.items()})
        self._log(account, case_no, stage, {k: f"{_clean(before[k])} → {v}" for k, v in diff.items()})
        return diff

    def resubmit(self, account, case_no, data):
        """被退回的案件由分隊修正登錄欄位，並清除初審結果讓大隊重審。"""
        case = self.get(case_no)
        if case is None:
            raise RegistryError(f"找不到案件 {case_no}")
        if not self.can_edit(account, "submit", case):
            raise RegistryError("這不是您的案件")
        if pending_for(case) != ROLE_UNIT and account.role == ROLE_UNIT:
            raise RegistryError("只有被退回的案件可以修改")
        merged = {k: case[k] for k in FIELDS if FIELDS[k][2] == "submit"}
        merged.update({k: v for k, v in data.items() if k in merged})
        errs = self.validate_submission(merged)
        if errs:
            raise RegistryError("；".join(errs))
        cells, diff = {}, {}
        for k in ("officer", "purpose", "plan_name", "date_start", "date_end", "total", "applied",
                  "source_kind", "source_detail"):
            new = date_text(merged[k]) if k.startswith("date") else (to_int(merged[k]) if k in ("total", "applied") else _clean(merged[k]))
            if _clean(case[k]) != _clean(new):
                cells[FIELDS[k][0]] = new
                diff[k] = f"{_clean(case[k])} → {new}"
        if pending_for(case) == ROLE_UNIT:
            for k in ("first_result", "first_by"):
                cells[FIELDS[k][0]] = ""
            diff["first_result"] = f"{_clean(case['first_result'])} → （重送大隊初審）"
        if not cells:
            return {}
        with self._lock:
            self.store.write_cells(case.row_no, cells)
        self._log(account, case_no, "submit", diff, "分隊修正")
        return diff

    # ---- 紀錄
    def _log(self, account, case_no, stage, changes, source=""):
        try:
            self.store.append_log([now_text(), case_no, account.login, ROLE_LABELS[account.role],
                                   STAGE_LABELS.get(stage, stage),
                                   "；".join(f"{FIELD_LABELS.get(k, k)}：{v}" for k, v in changes.items()), source])
        except Exception:
            # 紀錄寫入失敗不影響主流程，但不能悄悄吞掉：留在這個物件上讓畫面提醒
            self.log_failed = True

    log_failed = False


def _parse_date(text):
    m = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", _clean(text))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _col_letter(idx):
    s, n = "", idx + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


# ---------------------------------------------------------------- 產生器 → 登錄單
def draft_from_plan(ctx, officer=""):
    """把計畫產生器的 PlanContext 轉成登錄單草稿（dict，鍵同 FIELDS）。

    對應規則（尚待與業務科確認的標註在下面）：
      經費用途：設備類 → 設備費；其餘 → 活動費
      補助款來源：有議員 → 議員；只有代表 → 公所；兩者皆有 → 議員、公所
      來源細項：議員姓名＋「議員」、公所名稱，用「、」分開（與現行表單習慣一致）
    """
    kinds = {s["kind"] for s in ctx.sources} if ctx.sources else {"councilor"}
    if kinds == {"councilor"}:
        kind_text = "議員"
    elif kinds == {"rep"}:
        kind_text = "公所"
    else:
        kind_text = "議員、公所"
    names = []
    from plan_generator import format_councilors, _township_name  # 避免循環匯入，放函式內
    for s in ctx.sources or []:
        if s["kind"] == "rep":
            names.append(_township_name(s))
        else:
            names.append(format_councilors(s["names"]))
    if not ctx.sources and ctx.councilors:
        names.append(format_councilors(ctx.councilors))
    detail = "、".join(dict.fromkeys(n for n in names if n))
    return {
        "unit": ctx.unit.strip(),
        "officer": officer,
        "purpose": "設備費" if ctx.plan_type == "equipment" else "活動費",
        "plan_name": f"臺東縣消防局辦理{ctx.unit.strip()}{ctx.title2}",
        "date_start": ctx.start if ctx.plan_type != "equipment" else "",
        "date_end": ctx.end if ctx.plan_type != "equipment" else "",
        "total": int(round(ctx.total)),
        "applied": int(round(ctx.subsidy)),
        "source_kind": kind_text,
        "source_detail": detail,
    }
