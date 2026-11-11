"""案件登錄系統的組織架構與帳號。

帳號資料存在試算表的「帳號」工作表（只存密碼雜湊，不存明碼），所以網站重新部署不會被洗掉，
同時也是備份。第一次連線時，依組織架構自動建立所有帳號，預設密碼 0000，並標成必須更改。
登入頁不公告這組密碼。還沒改掉初始密碼的帳號，除了更改密碼以外不能做任何事。
不存明碼：忘記密碼時由民力訓練科重設回初始密碼，並回到必須更改的狀態。

登入失敗次數記在這張表（失敗次數、最後失敗時間、鎖定至），換瀏覽器或重新整理不會歸零。
連續失敗會鎖定一段時間，時間到自動解除；鎖定期間再試不會把時間往後延。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import case_registry as cr
from case_registry import Account, ROLE_BATTALION, ROLE_SECTION, ROLE_UNIT, _clean

ACCOUNT_TAB = "帳號"
ACCOUNT_HEADERS = ["帳號", "角色", "所屬大隊", "單位", "密碼雜湊", "需更改密碼", "更新時間",
                   "失敗次數", "最後失敗時間", "鎖定至"]
COL_HASH, COL_MUST, COL_UPDATED = 4, 5, 6
COL_FAILS, COL_FAIL_AT, COL_LOCKED = 7, 8, 9
DEFAULT_PASSWORD = "0000"
MIN_PASSWORD_LEN = 8
LOCK_FAILS = 5
LOCK_MINUTES = 15
FAIL_WINDOW_MINUTES = 30

# 組織架構（臺一律寫成台，與現行表單資料一致）
ORG = {
    "台東大隊": ["蘭嶼分隊", "綠島分隊", "知本分隊", "卑南分隊", "特種搜救分隊", "南王分隊", "大豐分隊",
                 "豐田分隊", "台東救護分隊", "台東分隊", "搜救犬分隊"],
    "關山大隊": ["利稻分隊", "延平分隊", "鹿野分隊", "海端分隊", "池上分隊", "關山分隊"],
    "成功大隊": ["東河分隊", "泰源分隊", "都蘭分隊", "成功分隊", "長濱分隊"],
    "大武大隊": ["達仁分隊", "大溪分隊", "金峰分隊", "太麻里分隊", "大武分隊"],
}
# 有帳號的科室：帳號名稱 -> 寫進「承辦科室」欄的全名
SECTIONS = {
    "民力訓練科": "民力運用及訓練科",
    "緊急救護科": "緊急救護科",
    "資通作業科": "資通作業科",
    "災害搶救科": "災害搶救科",
    "預防調查科": "預防調查科",
    "綜合企劃科": "綜合企劃科",
}


def norm_login(name):
    """帳號比對：去空白、臺＝台。"""
    return _clean(name).replace("臺", "台").replace(" ", "").replace("　", "")


def default_accounts():
    """依組織架構列出所有帳號（不含密碼）：list of dict(login, role, battalion, unit)。"""
    out = []
    for bn, units in ORG.items():
        out.append({"login": bn, "role": ROLE_BATTALION, "battalion": bn, "unit": ""})
        out += [{"login": u, "role": ROLE_UNIT, "battalion": bn, "unit": u} for u in units]
    out += [{"login": k, "role": ROLE_SECTION, "battalion": "", "unit": v} for k, v in SECTIONS.items()]
    return out


def password_problem(new, old=""):
    """新密碼不合規定時回傳給使用者看的句子，合規定回傳空字串。"""
    pw = new or ""
    if pw == DEFAULT_PASSWORD:
        return "不能使用初始密碼"
    if old and pw == old:
        return "新密碼不能和舊密碼相同"
    if len(pw) < MIN_PASSWORD_LEN:
        return f"新密碼至少 {MIN_PASSWORD_LEN} 碼"
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "新密碼須同時包含英文字母與數字"
    return ""


def _as_int(text):
    try:
        return int(_clean(text) or "0")
    except ValueError:
        return 0


def _account_from_row(row):
    row = list(row) + [""] * (len(ACCOUNT_HEADERS) - len(row))
    login, role, bn, unit, pw_hash, must, _updated, fails, failed_at, locked = row[:10]
    if not _clean(login) or role not in cr.ROLE_LABELS or not _clean(pw_hash):
        return None
    return Account(login=_clean(login), role=role, battalion=_clean(bn), unit=_clean(unit),
                   password_hash=_clean(pw_hash), must_change=_clean(must).upper() == "TRUE",
                   failed_attempts=_as_int(fails), failed_at=_clean(failed_at), locked_until=_clean(locked))


def _aware(now):
    now = now or datetime.now(cr.TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=cr.TZ)
    return now.astimezone(cr.TZ)


class AccountBook:
    def __init__(self, store):
        self.store = store

    # ---- 讀取
    def _rows(self):
        return self.store.read_tab(ACCOUNT_TAB)

    def ensure_columns(self):
        """舊的帳號表只有 7 欄時，補上失敗次數與鎖定時間，不改已有的密碼雜湊。"""
        rows = self._rows()
        if not rows:
            return
        header = list(rows[0]) + [""] * max(0, len(ACCOUNT_HEADERS) - len(rows[0]))
        cells = {i: name for i, name in enumerate(ACCOUNT_HEADERS) if _clean(header[i]) != name}
        if cells:
            self.store.update_tab_cells(ACCOUNT_TAB, 1, cells)

    def ensure_seeded(self):
        """帳號工作表不存在或少了帳號時，補上預設帳號（密碼 0000、必須更改）。回傳新增筆數。"""
        self.ensure_columns()
        have = {norm_login(r[0]) for r in self._rows()[1:] if r and _clean(r[0])}
        missing = [a for a in default_accounts() if norm_login(a["login"]) not in have]
        if not missing and self._rows():
            return 0
        now = cr.now_text()
        rows = [[a["login"], a["role"], a["battalion"], a["unit"], cr.hash_password(DEFAULT_PASSWORD),
                 "TRUE", now, "0", "", ""] for a in missing]
        self.store.append_tab_rows(ACCOUNT_TAB, ACCOUNT_HEADERS, rows)
        return len(rows)

    def load(self):
        self.ensure_columns()
        out = {}
        for row in self._rows()[1:]:
            acct = _account_from_row(row)
            if acct:
                out[norm_login(acct.login)] = acct
        return out

    def list_accounts(self):
        """依組織順序列出（科室、大隊、各大隊分隊）。登入頁不再用這份清單當下拉選單。"""
        book = self.load()
        order = [a["login"] for a in default_accounts()]
        first = [norm_login(n) for n in SECTIONS]
        names = first + [norm_login(n) for n in order if norm_login(n) not in first]
        return [book[n] for n in names if n in book]

    # ---- 登入與密碼
    def _row_no(self, login):
        for i, row in enumerate(self._rows(), start=1):
            if i > 1 and row and norm_login(row[0]) == norm_login(login):
                return i
        return None

    def _is_locked(self, acct, now):
        until = cr.parse_local_datetime(acct.locked_until)
        return bool(until and now < until)

    def is_locked(self, acct, now=None):
        return self._is_locked(acct, _aware(now))

    def _effective_fails(self, acct, now):
        until = cr.parse_local_datetime(acct.locked_until)
        if until and now >= until:
            return 0
        last = cr.parse_local_datetime(acct.failed_at)
        if last and now - last > timedelta(minutes=FAIL_WINDOW_MINUTES):
            return 0
        return int(acct.failed_attempts or 0)

    def _lock_message(self, acct):
        return f"登入失敗次數過多，此帳號已暫時鎖定至 {acct.locked_until}，時間到會自動解除。"

    def _write_account(self, login, cells):
        row_no = self._row_no(login)
        if row_no is None:
            raise cr.RegistryError(f"找不到帳號 {login}")
        self.store.update_tab_cells(ACCOUNT_TAB, row_no, cells)

    def _audit(self, actor, text, now=None):
        try:
            role = cr.ROLE_LABELS.get(getattr(actor, "role", ""), "")
            login = getattr(actor, "login", "") or ""
            self.store.append_log([cr.now_text(now), "", login, role, "帳號管理", text, "管理者"])
        except Exception:
            pass

    def _record_failure(self, acct, now):
        if self._is_locked(acct, now):
            return
        fails = self._effective_fails(acct, now) + 1
        cells = {COL_FAILS: str(fails), COL_FAIL_AT: cr.now_text(now), COL_UPDATED: cr.now_text(now), COL_LOCKED: ""}
        if fails >= LOCK_FAILS:
            until = now + timedelta(minutes=LOCK_MINUTES)
            cells[COL_LOCKED] = cr.now_text(until)
            try:
                self.store.append_log([
                    cr.now_text(now), "", acct.login, cr.ROLE_LABELS.get(acct.role, ""),
                    "登入鎖定", f"連續失敗 {LOCK_FAILS} 次，鎖定至 {cr.now_text(until)}", "",
                ])
            except Exception:
                pass
        self._write_account(acct.login, cells)

    def _clear_failures(self, acct, now, must_change=None):
        cells = {COL_FAILS: "0", COL_FAIL_AT: "", COL_LOCKED: "", COL_UPDATED: cr.now_text(now)}
        if must_change is True:
            cells[COL_MUST] = "TRUE"
        elif must_change is False:
            cells[COL_MUST] = "FALSE"
        self._write_account(acct.login, cells)

    def authenticate(self, login, password):
        """只核對密碼，不計失敗次數。更改密碼時用來確認舊密碼。"""
        book = self.load()
        acct = book.get(norm_login(login))
        stored = acct.password_hash if acct else "00$" + "0" * 64   # 帳號不存在也做一次雜湊
        ok = cr.verify_password(password or "", stored)
        return acct if (acct and ok) else None

    def login(self, login, password, now=None):
        """登入。回傳 (帳號或 None, 錯誤訊息)。失敗次數存在帳號表，重新整理不會歸零。"""
        now = _aware(now)
        key = norm_login(login)
        if not key or not (password or ""):
            return None, "請輸入帳號與密碼"
        book = self.load()
        acct = book.get(key)
        stored = acct.password_hash if acct else "00$" + "0" * 64
        if acct and self._is_locked(acct, now):
            cr.verify_password(password or "", stored)
            return None, self._lock_message(acct)
        ok = cr.verify_password(password or "", stored)
        if not (acct and ok):
            if acct:
                self._record_failure(acct, now)
                fresh = self.load().get(key)
                if fresh and self._is_locked(fresh, now):
                    return None, self._lock_message(fresh)
            return None, "帳號或密碼錯誤"
        on_default = password == DEFAULT_PASSWORD
        self._clear_failures(acct, now, must_change=True if on_default else None)
        fresh = self.load().get(key)
        return fresh, ""

    def change_password(self, login, old, new):
        acct = self.authenticate(login, old)
        if acct is None:
            raise cr.RegistryError("目前的密碼不正確")
        problem = password_problem(new, old)
        if problem:
            raise cr.RegistryError(problem)
        now = cr.now_text()
        self._write_account(login, {COL_HASH: cr.hash_password(new), COL_MUST: "FALSE", COL_UPDATED: now,
                                    COL_FAILS: "0", COL_FAIL_AT: "", COL_LOCKED: ""})

    def reset_password(self, actor, login):
        if not (actor and actor.is_admin):
            raise cr.RegistryError("只有民力訓練科可以重設密碼")
        if self._row_no(login) is None:
            raise cr.RegistryError(f"找不到帳號 {login}")
        now = cr.now_text()
        self._write_account(login, {COL_HASH: cr.hash_password(DEFAULT_PASSWORD), COL_MUST: "TRUE", COL_UPDATED: now,
                                    COL_FAILS: "0", COL_FAIL_AT: "", COL_LOCKED: ""})
        self._audit(actor, f"重設密碼：{norm_login(login)}（須更改密碼，並解除鎖定）")

    def clear_lock(self, actor, login):
        """解除登入鎖定，不改密碼。給帳號被別人連試鎖住時用。"""
        if not (actor and actor.is_admin):
            raise cr.RegistryError("只有民力訓練科可以解除鎖定")
        if self._row_no(login) is None:
            raise cr.RegistryError(f"找不到帳號 {login}")
        self._write_account(login, {COL_FAILS: "0", COL_FAIL_AT: "", COL_LOCKED: "", COL_UPDATED: cr.now_text()})
        self._audit(actor, f"解除登入鎖定：{norm_login(login)}")
