# -*- coding: utf-8 -*-
"""
補捐助「核銷自我檢核」的檢核規則（純函式，不依賴 Streamlit，方便單獨測試）。

- check_settlement()：依「收支清單」的預算／實際金額，檢查補助與自籌的比例規定。
- DOC_CHECKLIST / check_documents()：對照「建議補助款【核銷案】大隊初審檢核表」的文件檢核清單。

所有檢核都只是提醒，最終仍以縣府核定函與大隊、會計室審查意見為準。
本模組不儲存任何使用者輸入，也不含任何個案資料。
"""

from dataclasses import dataclass

SELF_FUND_THRESHOLD = 20000      # 補助金額超過此數，自籌款須占總經費 30% 以上
SELF_FUND_RATIO = 0.30
MEAL_SOUVENIR_RATIO = 0.50       # 餐費＋紀念品合計不得超過核定補助金額 50%
MISC_RATIO = 0.05                # 雜支不得超過總經費 5%
PROCUREMENT_THRESHOLD = 150000   # 總經費超過 15 萬元適用採購法規範

ITEM_KINDS = ["一般", "餐費", "紀念品", "雜支", "住宿", "交通"]
MEAL_KINDS = ("餐費", "紀念品")

OK, WARN, ERROR = "ok", "warn", "error"


@dataclass
class Finding:
    level: str      # ok / warn / error
    title: str
    detail: str
    rule: str = ""          # 對照的注意要點或錯誤樣態（以標題標示；畫面上的編號會因增刪而變）
    where: str = ""         # 出錯的欄位或區段
    comparison: str = ""    # 實際值與規定上限
    suggestion: str = ""    # 一行修正建議


def _num(v):
    try:
        if v is None or v != v:      # None 或 NaN
            return 0
        return float(v)
    except (TypeError, ValueError):
        return 0


def _money(v):
    return f"{int(round(v)):,}"


def check_settlement(approved_subsidy, items):
    """檢查收支清單。

    approved_subsidy：縣府（或公所）核定補助金額。
    items：list[dict]，每列包含 kind（項目類別）、budget（預算金額 A）、actual（實際金額 B）、
           subsidy（實際由補助款支應）、self_fund（實際由自籌款支應）。
    回傳 list[Finding]。
    """
    rows = []
    for it in items or []:
        row = {
            "name": str(it.get("name") or "").strip(),
            "kind": it.get("kind") or "一般",
            "budget": _num(it.get("budget")),
            "actual": _num(it.get("actual")),
            "subsidy": _num(it.get("subsidy")),
            "self_fund": _num(it.get("self_fund")),
        }
        if row["name"] or row["budget"] or row["actual"] or row["subsidy"] or row["self_fund"]:
            rows.append(row)

    approved = _num(approved_subsidy)
    findings = []
    if not rows:
        return [Finding(WARN, "尚未輸入支出項目", "請在表格中至少輸入一個支出項目。")]

    budget_total = sum(r["budget"] for r in rows)
    actual_total = sum(r["actual"] for r in rows)
    subsidy_total = sum(r["subsidy"] for r in rows)
    self_total = sum(r["self_fund"] for r in rows)

    # 1. 每一列：實際金額 = 補助 + 自籌
    bad_rows = [r for r in rows if abs(r["actual"] - r["subsidy"] - r["self_fund"]) > 0.5]
    if bad_rows:
        names = "、".join((r["name"] or "（未命名）") for r in bad_rows)
        findings.append(Finding(ERROR, "有項目的「實際金額」不等於「補助＋自籌」",
                                f"請核對：{names}。收支清單每一項的實際金額必須等於各機關補助款加自付額。"))
    else:
        findings.append(Finding(OK, "每一項的實際金額＝補助款＋自籌款", ""))

    # 2. 實際補助不得超過核定金額
    if approved <= 0:
        findings.append(Finding(WARN, "尚未輸入核定補助金額", "請填入縣府（公所）核定補助金額，才能檢查補助上限。"))
    elif subsidy_total > approved + 0.5:
        findings.append(Finding(ERROR, "實際使用補助款超過核定金額",
                                f"實際補助 {_money(subsidy_total)} 元，核定 {_money(approved)} 元，超出 {_money(subsidy_total - approved)} 元。"))
    else:
        findings.append(Finding(OK, "實際補助款未超過核定金額",
                                f"實際補助 {_money(subsidy_total)} 元／核定 {_money(approved)} 元。"))

    # 3. 縣政府及公所實際金額(B) 是否等於或小於預算金額(A)（逐項）
    over = [r for r in rows if r["subsidy"] > r["budget"] + 0.5]
    if over:
        names = "、".join((r["name"] or "（未命名）") for r in over)
        findings.append(Finding(ERROR, "有項目的補助款實際金額大於預算金額",
                                f"{names}：補助款實際金額（B）不可大於預算金額（A），請調整或在計畫概算表中修正。"))
    else:
        findings.append(Finding(OK, "各項補助款實際金額都未超過預算金額", ""))

    # 4. 補助比例（四捨五入）加總須等於 100%
    if actual_total > 0:
        pct_sub = round(subsidy_total / actual_total * 100, 1)
        pct_self = round(self_total / actual_total * 100, 1)
        if abs(pct_sub + pct_self - 100) > 0.05:
            findings.append(Finding(ERROR, "補助比例加總不等於 100%",
                                    f"補助 {pct_sub}% ＋ 自籌 {pct_self}% ＝ {round(pct_sub + pct_self, 1)}%。請先修正上列金額不一致的項目，若金額都正確，再調整四捨五入的位數。"))
        else:
            findings.append(Finding(OK, "補助比例加總等於 100%", f"補助 {pct_sub}%、自籌 {pct_self}%。"))
    else:
        findings.append(Finding(WARN, "實際金額合計為 0", "請輸入實際支出金額。"))

    # 5. 補助超過 2 萬：自籌須占總經費 30% 以上
    basis = actual_total if actual_total > 0 else budget_total
    if approved > SELF_FUND_THRESHOLD or subsidy_total > SELF_FUND_THRESHOLD:
        ratio = self_total / basis if basis else 0
        if ratio + 1e-9 < SELF_FUND_RATIO:
            need = basis * SELF_FUND_RATIO - self_total
            findings.append(Finding(ERROR, "補助超過 2 萬元，自籌款未達總經費 30%",
                                    f"自籌 {_money(self_total)} 元，占總經費 {ratio:.1%}，至少還差 {_money(need)} 元（自籌經費不含其他政府機關補助）。"))
        else:
            findings.append(Finding(OK, "自籌款占總經費 30% 以上",
                                    f"自籌 {_money(self_total)} 元，占 {ratio:.1%}。補助超過 2 萬元須隨案檢附這個金額以上的自籌款單據。"))
    else:
        findings.append(Finding(OK, "補助未超過 2 萬元，不適用 30% 自籌規定",
                                "核定補助金額未超過 2 萬元者，免附自籌款單據。"))

    # 6. 餐費＋紀念品不得超過核定補助金額 50%
    meal_sub = sum(r["subsidy"] for r in rows if r["kind"] in MEAL_KINDS)
    limit_base = approved if approved > 0 else subsidy_total
    if limit_base > 0:
        cap = limit_base * MEAL_SOUVENIR_RATIO
        if meal_sub > cap + 0.5:
            findings.append(Finding(ERROR, "餐費及紀念品超過核定補助金額 50%",
                                    f"以補助款報支餐費＋紀念品 {_money(meal_sub)} 元，上限 {_money(cap)} 元。"
                                    "有多個補助來源時，須依來源分別計算。"))
        else:
            tail = "（剛好等於上限）" if abs(meal_sub - cap) <= 0.5 and meal_sub > 0 else ""
            findings.append(Finding(OK, "餐費及紀念品未超過補助金額 50%",
                                    f"以補助款報支 {_money(meal_sub)} 元／上限 {_money(cap)} 元{tail}。"))

    # 7. 雜支不得超過總經費 5%
    misc = sum(r["actual"] for r in rows if r["kind"] == "雜支")
    if misc > 0 and basis > 0:
        if misc > basis * MISC_RATIO + 0.5:
            findings.append(Finding(ERROR, "雜支超過總經費 5%",
                                    f"雜支 {_money(misc)} 元，上限 {_money(basis * MISC_RATIO)} 元。"))
        else:
            findings.append(Finding(OK, "雜支未超過總經費 5%", f"雜支 {_money(misc)} 元。"))

    # 8. 總經費超過 15 萬
    if basis > PROCUREMENT_THRESHOLD:
        findings.append(Finding(WARN, "總經費超過 15 萬元",
                                "陳報單須敘明採購法依據並加會政風室；核銷不可使用旅行社代收轉付單據，也不可拆分發包。"))

    # 9. 提醒有住宿／交通項目時的附件
    kinds = {r["kind"] for r in rows if r["actual"] > 0}
    if "住宿" in kinds:
        findings.append(Finding(WARN, "有住宿費用", "須檢附住宿名冊；住宿費依國內出差旅費標準報支，單據須註明單價與數量。"))
    if "交通" in kinds:
        findings.append(Finding(WARN, "有交通費用", "請依國內出差旅費標準報支，並留存票根。"))

    return findings


# ---------------------------------------------------------------- 文件檢核清單（對照大隊初審檢核表）
# (分組, 項目, 條件：None 表示一律檢查；"accommodation"/"gov_over_20k"/"township"/"equipment"/"travel_agency"/"direct_pay")
DOC_CHECKLIST = [
    ("陳報單", "案件主旨已依範例句填寫", None),
    ("陳報單", "簡述依據已依範例句填寫（縣府核定函文號、金額、案號）", None),
    ("陳報單", "經費來源已依範例句填寫", None),
    ("陳報單", "成果資料已依範例句列出各項附件", None),
    ("附件", "已附核定公文原函影本", None),
    ("附件", "已附案件計畫", None),
    ("附件", "已附經費概算表", None),
    ("收支清單", "預算金額與原計畫概算表一致", None),
    ("收支清單", "縣政府及公所實際金額（B）等於或小於預算金額（A）", None),
    ("收支清單", "補助比例四捨五入後加總等於 100%", None),
    ("收支清單", "經辦人員有承辦人及單位主管核章", None),
    ("憑證粘貼", "一張發票收據黏貼於一張憑證（或同一廠商多張黏貼於同一憑證）", None),
    ("憑證粘貼", "單據為正本，已標註本局統編 93501824，並註明品項、單價及數量", None),
    ("憑證粘貼", "電子發票已手寫補上單價及數量並加蓋職名章", None),
    ("憑證粘貼", "請購日期早於發票收據日期", None),
    ("成果照片", "成果照片與活動主旨密切相關（至少 6 張）", None),
    ("自籌款", "已檢附總經費 30% 以上的自籌款單據（正本或加蓋與正本相符章的影本）", "gov_over_20k"),
    ("住宿", "已檢附住宿名冊", "accommodation"),
    ("公所案件", "已檢附活動成果暨效益考核表", "township"),
    ("設備類", "已檢附財產增加單", "equipment"),
    ("單據", "旅行社代收轉付單據的使用符合規定（總經費 15 萬元以下才可使用）", "travel_agency"),
    ("單據", "逕付廠商：已檢附廠商存摺影本，且戶名與單據店章一致", "direct_pay"),
]

DOC_CONDITIONS = {
    "gov_over_20k": "核定補助金額超過 2 萬元",
    "accommodation": "有申請住宿費用",
    "township": "向鄉鎮市公所申請核銷",
    "equipment": "設備類（購置）案件",
    "travel_agency": "使用旅行社代收轉付單據",
    "direct_pay": "款項逕付廠商",
}


def applicable_documents(conditions):
    """conditions：已勾選的條件代號集合。回傳需要檢查的 (分組, 項目) 清單。"""
    conds = set(conditions or [])
    return [(g, t) for g, t, c in DOC_CHECKLIST if c is None or c in conds]


def check_documents(checked_items, conditions):
    """checked_items：已勾選的項目文字集合。回傳 (缺項清單, 總項數)。"""
    todo = applicable_documents(conditions)
    done = set(checked_items or [])
    missing = [(g, t) for g, t in todo if t not in done]
    return missing, len(todo)
