"""案件登錄系統的組織架構與帳號。

帳號資料存在試算表的「帳號」工作表（只存密碼雜湊，不存明碼），所以網站重新部署不會被洗掉，
同時也是備份。第一次連線時，依組織架構自動建立所有帳號，預設密碼 0000。
不存明碼：忘記密碼時由民力訓練科重設回 0000，無法查看原本的密碼。
"""
from __future__ import annotations

import case_registry as cr
from case_registry import Account, ROLE_BATTALION, ROLE_SECTION, ROLE_UNIT, _clean

ACCOUNT_TAB = "帳號"
ACCOUNT_HEADERS = ["帳號", "角色", "所屬大隊", "單位", "密碼雜湊", "需更改密碼", "更新時間"]
DEFAULT_PASSWORD = "0000"
MIN_PASSWORD_LEN = 6

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


def _account_from_row(row):
    row = list(row) + [""] * (len(ACCOUNT_HEADERS) - len(row))
    login, role, bn, unit, pw_hash, must, _ = row[:7]
    if not _clean(login) or role not in cr.ROLE_LABELS or not _clean(pw_hash):
        return None
    return Account(login=_clean(login), role=role, battalion=_clean(bn), unit=_clean(unit),
                   password_hash=_clean(pw_hash), must_change=_clean(must).upper() == "TRUE")


class AccountBook:
    def __init__(self, store):
        self.store = store

    # ---- 讀取
    def _rows(self):
        return self.store.read_tab(ACCOUNT_TAB)

    def ensure_seeded(self):
        """帳號工作表不存在或少了帳號時，補上預設帳號（密碼 0000）。回傳新增筆數。"""
        have = {norm_login(r[0]) for r in self._rows()[1:] if r and _clean(r[0])}
        missing = [a for a in default_accounts() if norm_login(a["login"]) not in have]
        if not missing and self._rows():
            return 0
        now = cr.now_text()
        rows = [[a["login"], a["role"], a["battalion"], a["unit"], cr.hash_password(DEFAULT_PASSWORD), "TRUE", now]
                for a in missing]
        self.store.append_tab_rows(ACCOUNT_TAB, ACCOUNT_HEADERS, rows)
        return len(rows)

    def load(self):
        out = {}
        for row in self._rows()[1:]:
            acct = _account_from_row(row)
            if acct:
                out[norm_login(acct.login)] = acct
        return out

    def list_accounts(self):
        """依組織順序列出（科室、大隊、各大隊分隊），供登入下拉選單。"""
        book = self.load()
        order = [a["login"] for a in default_accounts()]
        first = [norm_login(n) for n in SECTIONS]
        names = first + [norm_login(n) for n in order if norm_login(n) not in first]
        return [book[n] for n in names if n in book]

    # ---- 登入與密碼
    def authenticate(self, login, password):
        book = self.load()
        acct = book.get(norm_login(login))
        stored = acct.password_hash if acct else "00$" + "0" * 64   # 帳號不存在也做一次雜湊
        ok = cr.verify_password(password or "", stored)
        return acct if (acct and ok) else None

    def _row_no(self, login):
        for i, row in enumerate(self._rows(), start=1):
            if i > 1 and row and norm_login(row[0]) == norm_login(login):
                return i
        return None

    def change_password(self, login, old, new):
        acct = self.authenticate(login, old)
        if acct is None:
            raise cr.RegistryError("目前的密碼不正確")
        if len(new or "") < MIN_PASSWORD_LEN:
            raise cr.RegistryError(f"新密碼至少 {MIN_PASSWORD_LEN} 碼")
        if new == DEFAULT_PASSWORD or new == old:
            raise cr.RegistryError("新密碼不能和預設密碼或舊密碼相同")
        self.store.update_tab_cells(ACCOUNT_TAB, self._row_no(login),
                                    {4: cr.hash_password(new), 5: "FALSE", 6: cr.now_text()})

    def reset_password(self, actor, login):
        if not (actor and actor.is_admin):
            raise cr.RegistryError("只有民力訓練科可以重設密碼")
        row_no = self._row_no(login)
        if row_no is None:
            raise cr.RegistryError(f"找不到帳號 {login}")
        self.store.update_tab_cells(ACCOUNT_TAB, row_no,
                                    {4: cr.hash_password(DEFAULT_PASSWORD), 5: "TRUE", 6: cr.now_text()})
