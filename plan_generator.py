# -*- coding: utf-8 -*-
"""
補捐助「計畫書／經費概算表 草稿產生器」。

- 以固定範本把同仁填的資料套進計畫書與概算表，不是自由生成文字，格式與用字固定。
- 產出前先套用申請階段的規則檢查（自籌 30%、餐費紀念品 50%、雜支 5%、用字、備註欄、課程表…）。
- 輸出 Word 計畫書（.docx）與 Excel 概算表（.xlsx，合計用公式）。
- 純函式、不依賴 Streamlit，也不儲存任何輸入資料。

目前只有一種計畫類型（專業訓練活動／議員建議補助款）。要新增類型時，在 PLAN_TYPES 加一筆，
並提供對應的章節範本即可。
"""

import calendar
import io
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from subsidy_check import (
    MEAL_KINDS, MEAL_SOUVENIR_RATIO, MISC_RATIO, PROCUREMENT_THRESHOLD,
    SELF_FUND_RATIO, SELF_FUND_THRESHOLD, OK, WARN, ERROR, Finding,
)

PLAN_TYPES = {
    "training": {
        "label": "專業訓練活動（議員建議補助款）",
        "desc": "義消／分隊辦理的專業訓練、研習活動（救災、救護、宣導、環境教育等），經費來源為議員建議補助款加自籌款。",
        "source_label": "議員建議補助款",
    },
}

ITEM_KINDS = ["一般", "餐費", "紀念品", "雜支", "內聘鐘點費", "二代健保補充保費", "設備購置"]
FORBIDDEN_WORDS = ("聯誼", "餐敘", "聯歡", "健身")
NHI_KIND = "二代健保補充保費"
# 活動開始日須在「今天 + 1 個日曆月 + 7 天」之後，讓大隊先初審再送局本部。
# （約 37～38 天，依當月天數略有不同；不再用固定 30 天。）

_CN_DIGITS = "零壹貳參肆伍陸柒捌玖"
_YEAR_TOKEN = re.compile(
    r"(?:[0-9０-９]{2,3}|[○〇零一二三四五六七八九十]{2,8})\s*年度"
)
_CN_SECTION = ["壹", "貳", "參", "肆", "伍", "陸", "柒", "捌", "玖", "拾", "拾壹", "拾貳", "拾參", "拾肆"]
_CN_PLAIN = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]


def roc_year(d=None):
    return (d or date.today()).year - 1911


def roc_date(d):
    return f"{d.year - 1911}年{d.month:02d}月{d.day:02d}日"


def to_cn_amount(n):
    """整數金額轉中文大寫（例：32000 → 參萬貳仟）。"""
    n = int(round(n))
    if n == 0:
        return "零"
    units = ["", "拾", "佰", "仟"]
    big = ["", "萬", "億"]
    parts = []
    group_idx = 0
    while n > 0:
        grp = n % 10000
        n //= 10000
        if grp:
            s = ""
            zero = False
            digits = [(grp // 1000) % 10, (grp // 100) % 10, (grp // 10) % 10, grp % 10]
            for i, dgt in enumerate(digits):
                pos = 3 - i
                if dgt == 0:
                    zero = bool(s)
                else:
                    if zero:
                        s += "零"
                        zero = False
                    s += _CN_DIGITS[dgt] + units[pos]
            if grp < 1000 and n > 0:
                s = "零" + s          # 例：10500 → 壹萬零伍佰
            parts.append(s + big[group_idx])
        elif parts:
            parts.append("零")
        group_idx += 1
    out = "".join(reversed(parts))
    while "零零" in out:
        out = out.replace("零零", "零")
    return out.rstrip("零") if len(out) > 1 else out


def money(n):
    return f"{int(round(n)):,}"


def add_months(d, months):
    """日曆月加減，月底不足的日期（如 1/31 加一個月）落到該月最後一天。"""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def earliest_activity_date(today):
    """開始日期至少要在今天起 1 個月再加 7 天（含當天）。"""
    return add_months(today, 1) + timedelta(days=7)


def strip_activity_year(name):
    """去掉活動名稱裡的「115年度」「一一五年度」，避免標題年度重複。"""
    text = str(name or "").strip()
    cleaned = _YEAR_TOKEN.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" 、，,")
    return cleaned


def format_councilors(text):
    """每位議員只留一個「議員」。空白時用「ＯＯ議員」。"""
    raw = str(text or "").strip()
    if not raw:
        return "ＯＯ議員"
    parts = re.split(r"[、,，;；/]+", raw)
    names = []
    for part in parts:
        part = re.sub(r"\s*議員\s*$", "", part).strip()
        if not part:
            continue
        names.append(part + "議員")
    return "、".join(names) if names else "ＯＯ議員"


def parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        if value != value:  # NaN
            return None
    except Exception:
        pass
    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime().date()
        except Exception:
            return None
    text = str(value).strip()
    if not text or text.lower() in ("nat", "nan", "none"):
        return None
    matched = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if not matched:
        return None
    try:
        return date(int(matched.group(1)), int(matched.group(2)), int(matched.group(3)))
    except ValueError:
        return None


def _time_sort_key(text):
    matched = re.search(r"(\d{1,2})\s*[:：]\s*(\d{2})", str(text or ""))
    if not matched:
        return (99, 99, str(text or ""))
    return (int(matched.group(1)) % 24, int(matched.group(2)), str(text or ""))


def prepare_courses(courses, start=None, end=None):
    """保留有填任何欄位的課程列（含只填時間、內容空白），空日期預設為開始日期，並依日期、時間排序。

    end 目前只供呼叫端做區間檢查，不在這裡剔除列。
    """
    del end  # 區間是否合法由 check_plan 判斷，這裡不丟列
    rows = []
    for course in courses or []:
        if not isinstance(course, dict):
            continue
        content = str(course.get("content") or "").strip()
        time = str(course.get("time") or "").strip()
        teacher = str(course.get("teacher") or "").strip()
        parsed = parse_date(course.get("date"))
        if not content and not time and not teacher and parsed is None:
            continue
        if parsed is None and start is not None:
            parsed = start
        rows.append({"date": parsed, "time": time, "content": content, "teacher": teacher})
    rows.sort(key=lambda row: (row["date"] or date.min, _time_sort_key(row["time"]), row["content"]))
    return rows


def _remark(use, subsidy, self_amt, source_label):
    parts = []
    if subsidy > 0.5:
        parts.append(f"{money(subsidy)}元由{source_label}支應")
    if self_amt > 0.5:
        parts.append(f"{money(self_amt)}元由自籌款支應")
    body = "，".join(parts)
    use = (use or "").strip()
    if use and body:
        return f"{use}；{body}"
    return use or body


def _eligible_for_subsidy(item):
    return (
        item.get("kind") != NHI_KIND
        and _f(item.get("qty")) > 0
        and _f(item.get("price")) > 0
        and _f(item.get("total")) > 0
    )


def allocate_subsidy(items, subsidy):
    """依項目金額比例分配補助款（整數元）。最後一個可分配項目吸收餘數，使加總剛好等於補助金額。

    二代健保補充保費、數量或單價不是正數的項目不分配，全數視為自籌。
    """
    subsidy_int = max(0, int(round(_f(subsidy))))
    eligible = [item for item in items if _eligible_for_subsidy(item)]
    base = sum(int(round(item["total"])) for item in eligible)
    running = 0
    for item in items:
        item["subsidy"] = 0
    if eligible and subsidy_int > 0 and base > 0:
        for item in eligible[:-1]:
            share = (int(round(item["total"])) * subsidy_int) // base
            item["subsidy"] = share
            running += share
        eligible[-1]["subsidy"] = subsidy_int - running
    for item in items:
        item["self"] = item["total"] - item["subsidy"]
    return items


@dataclass
class PlanContext:
    plan_type: str
    unit: str
    year: int
    name: str
    start: date | None
    end: date | None
    place: str
    audience: str
    headcount: int
    method: str
    instructors: str
    co_organizer: str
    supervisor: str
    councilors: str
    subsidy: float
    items: list
    courses: list
    roster: list
    background: str = ""
    purpose: str = ""
    rules: str = ""
    contact: str = ""

    # ---- 衍生值
    def __post_init__(self):
        self.courses = prepare_courses(self.courses, self.start, self.end)

    @property
    def name_for_title(self):
        return strip_activity_year(self.name).strip()

    @property
    def activity(self):
        n = self.name_for_title
        if not n:
            return ""
        return n if n.endswith("活動") else n + "活動"

    @property
    def title1(self):
        return f"臺東縣消防局辦理{self.unit.strip()}"

    @property
    def title2(self):
        if not self.activity:
            return f"{self.year}年度計畫"
        return f"{self.year}年度{self.activity}計畫"

    @property
    def total(self):
        return sum(i["total"] for i in self.items)

    @property
    def self_fund(self):
        return self.total - self.subsidy

    @property
    def date_text(self):
        if not self.start or not self.end:
            return "（尚未選擇日期）"
        if self.start == self.end:
            return roc_date(self.start)
        return f"{roc_date(self.start)}至{roc_date(self.end)}"

    @property
    def days(self):
        if not self.start or not self.end or self.end < self.start:
            return 1
        return (self.end - self.start).days + 1

    @property
    def source_label(self):
        return PLAN_TYPES[self.plan_type]["source_label"]


def normalize_items(rows, subsidy=0, source_label="議員建議補助款"):
    """把畫面輸入的列轉成概算項目。補助款依金額比例分配，並產生「用途＋經費來源」備註。

    使用者只填數量、單價、用途、類別與補助總額；各列不再另填補助款。
    """
    items = []
    for r in rows or []:
        name = str(r.get("name") or "").strip()
        qty = _f(r.get("qty"))
        price = _f(r.get("price"))
        use = str(r.get("use") or "").strip()
        unit = str(r.get("unit") or "").strip()
        if not name and qty == 0 and price == 0 and not use and not unit:
            continue
        total = qty * price
        items.append({
            "name": name, "kind": r.get("kind") or "一般", "qty": qty, "unit": unit,
            "price": price, "total": total, "use": use, "subsidy": 0, "self": total, "remark": "",
        })
    allocate_subsidy(items, subsidy)
    for item in items:
        self_amt = item["self"] if item["self"] > 0.5 else 0
        item["remark"] = _remark(item["use"], item["subsidy"], self_amt, source_label)
    return items


def _f(v):
    try:
        if v is None or v != v:
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------- 規則檢查（申請階段）
def check_plan(ctx, today=None):
    today = today or date.today()
    f = []

    # 1. 用字
    text_all = " ".join([ctx.name, ctx.unit, ctx.background, ctx.purpose, ctx.method, ctx.rules] +
                        [i["name"] for i in ctx.items])
    bad = [w for w in FORBIDDEN_WORDS if w in text_all]
    if bad:
        f.append(Finding(ERROR, "名稱或內容出現不得使用的字眼", f"請移除：{'、'.join(bad)}。計畫須以社會公益、教育、訓練、研習為主。"))
    else:
        f.append(Finding(OK, "名稱與內容沒有「聯誼、餐敘、聯歡、健身」等字眼", ""))
    if "獎勵" in ctx.rules or "敘獎" in ctx.rules or "獎勵" in ctx.background or "獎勵" in ctx.purpose:
        f.append(Finding(ERROR, "計畫書內不得出現行政獎勵／敘獎字句", "敘獎事項只在陳報單敘明並加會人事室。"))

    # 2. 必填
    miss = [n for n, v in [("申請單位", ctx.unit), ("活動名稱", ctx.name), ("地點", ctx.place), ("參訓對象", ctx.audience)] if not str(v).strip()]
    if miss:
        f.append(Finding(ERROR, "尚有必填欄位未填", "、".join(miss)))

    # 2b. 活動名稱若已含年度，標題會自動拿掉，避免「115年度一一五年度…」
    raw_name = ctx.name.strip()
    if raw_name and ctx.name_for_title != raw_name:
        if not ctx.name_for_title:
            f.append(Finding(ERROR, "活動名稱只寫了年度",
                             "請改填活動名稱本身，不必再寫「115年度」或「一一五年度」，標題會自動加上年度。"))
        else:
            f.append(Finding(WARN, "活動名稱含有年度，已自動省略",
                             f"標題使用「{ctx.title2}」，避免年度重複。"))

    # 3. 日期（須預留 1 個月 + 7 天給大隊初審，再送局本部）
    if ctx.start is None or ctx.end is None:
        f.append(Finding(ERROR, "尚未選擇開始或結束日期", "請選擇活動日期。"))
    elif ctx.end < ctx.start:
        f.append(Finding(ERROR, "結束日期早於開始日期", "請修正日期區間，結束日期不可早於開始日期。"))
    else:
        lead = (ctx.start - today).days
        earliest = earliest_activity_date(today)
        if ctx.start < today:
            f.append(Finding(ERROR, "活動開始日期已過",
                             f"開始日期 {roc_date(ctx.start)} 早於今天 {abs(lead)} 天，請改期後再送審。"))
        elif ctx.start == today:
            f.append(Finding(ERROR, "活動開始日期就是今天", "已來不及完成大隊初審並送達局本部，請改期。"))
        elif ctx.start < earliest:
            need = (earliest - today).days
            f.append(Finding(WARN, f"距離活動只剩 {lead} 天，不足 1 個月又 1 週",
                             f"活動類案件要先經大隊初審再送局本部，開始日期至少要在今天起 1 個月再加 7 天"
                             f"（{roc_date(earliest)}，約 {need} 天後）以後。縣府另要求活動舉辦日 5 日前送達縣府。"))
        else:
            f.append(Finding(OK, "活動日期已預留 1 個月又 1 週",
                             f"距離活動還有 {lead} 天，足夠大隊初審後送達局本部（最早可為 {roc_date(earliest)}）。"))

    # 4. 概算表
    if not ctx.items:
        f.append(Finding(ERROR, "概算表沒有任何項目", "請至少輸入一個經費項目。"))
        return f
    total, sub = ctx.total, ctx.subsidy
    bad_amount = [i["name"] or "（未命名）" for i in ctx.items if i["qty"] <= 0 or i["price"] <= 0]
    if bad_amount:
        f.append(Finding(ERROR, "數量或單價不是正數",
                         "、".join(bad_amount) + "。數量與單價都要大於 0，零或負數不能當成有效經費。"))
    allocated = sum(i["subsidy"] for i in ctx.items)
    if abs(allocated - sub) > 0.5:
        if any(i["kind"] == NHI_KIND for i in ctx.items) and not any(_eligible_for_subsidy(i) for i in ctx.items):
            f.append(Finding(ERROR, "補助款無法分配",
                             "二代健保補充保費不得使用補助款，請再填其他可分配的項目，或把補助金額改為 0。"))
        else:
            f.append(Finding(ERROR, "補助款無法依比例分配",
                             f"已分配 {money(allocated)} 元，補助金額 {money(sub)} 元。請確認各項數量、單價都是正數。"))
    else:
        f.append(Finding(OK, "補助款已依各項金額比例分配", f"加總 {money(sub)} 元，與議員建議補助款相同。"))
    eligible_base = sum(i["total"] for i in ctx.items if _eligible_for_subsidy(i))
    if sub > eligible_base + 0.5:
        extra = "二代健保補充保費不分配補助款、全數自籌。" if any(i["kind"] == NHI_KIND for i in ctx.items) else ""
        f.append(Finding(ERROR, "補助金額超過可分配項目的合計",
                         f"可分配項目合計 {money(eligible_base)} 元，補助金額 {money(sub)} 元。{extra}"))
    over = [i["name"] or "（未命名）" for i in ctx.items if i["subsidy"] > i["total"] + 0.5]
    if over:
        f.append(Finding(ERROR, "有項目的補助款支應大於該項合計", "、".join(over)))
    if sub > total + 0.5:
        f.append(Finding(ERROR, "補助金額大於總經費",
                         f"補助 {money(sub)} 元，總經費 {money(total)} 元。請調降補助金額或增加項目，自籌款不會以負數表示。"))
    elif sub > SELF_FUND_THRESHOLD:
        # 5. 自籌 30%（補助已超過總經費時不再計算，避免自籌出現負數）
        self_amt = total - sub
        ratio = self_amt / total if total else 0
        if ratio + 1e-9 < SELF_FUND_RATIO:
            need = total * SELF_FUND_RATIO - self_amt
            f.append(Finding(ERROR, "補助超過 2 萬元，自籌款未達總經費 30%",
                             f"自籌 {money(self_amt)} 元，占 {ratio:.1%}，至少還差 {money(need)} 元。"))
        else:
            f.append(Finding(OK, "自籌款占總經費 30% 以上", f"自籌 {money(self_amt)} 元，占 {ratio:.1%}。"))
    else:
        f.append(Finding(OK, "補助未超過 2 萬元，不適用 30% 自籌規定", ""))

    # 6. 餐費＋紀念品 ≤ 50%
    meal = sum(i["subsidy"] for i in ctx.items if i["kind"] in MEAL_KINDS)
    if sub > 0:
        cap = sub * MEAL_SOUVENIR_RATIO
        if meal > cap + 0.5:
            f.append(Finding(ERROR, "餐費及紀念品超過補助金額 50%", f"補助款支應 {money(meal)} 元，上限 {money(cap)} 元。"))
        elif cap and meal > cap * 0.9:
            f.append(Finding(WARN, "餐費及紀念品已接近 50% 上限", f"補助款支應 {money(meal)} 元／上限 {money(cap)} 元，核銷時單據稍有變動就可能超過，建議預留空間。"))
        else:
            f.append(Finding(OK, "餐費及紀念品未超過補助金額 50%", f"補助款支應 {money(meal)} 元／上限 {money(cap)} 元。"))

    # 7. 雜支 5%
    misc = sum(i["total"] for i in ctx.items if i["kind"] == "雜支")
    if misc > 0:
        if misc > total * MISC_RATIO + 0.5:
            f.append(Finding(ERROR, "雜支超過總經費 5%", f"雜支 {money(misc)} 元，上限 {money(total * MISC_RATIO)} 元。"))
        else:
            f.append(Finding(OK, "雜支未超過總經費 5%", ""))

    # 8. 特殊類別（二代健保不參與分配，補助款應為 0）
    nhi_items = [i for i in ctx.items if i["kind"] == NHI_KIND]
    if any(i["subsidy"] > 0.5 for i in nhi_items):
        f.append(Finding(ERROR, "二代健保補充保費不得使用補助款支應", "請改由自籌款或分隊經費吸收。"))
    elif nhi_items:
        f.append(Finding(OK, "二代健保補充保費全數由自籌款支應", "這類項目不分配補助款。"))
    if any(i["kind"] == "設備購置" for i in ctx.items):
        f.append(Finding(ERROR, "活動類補助款不得用於資本門（購置設備）",
                         "設備購置請改走設備類案件（須附廠商估價單與縣府審核表）。"))
    if any(i["kind"] == "內聘鐘點費" for i in ctx.items):
        f.append(Finding(WARN, "有內聘教官／助教鐘點費",
                         "僅限具法源依據且須核發專業證照的實質訓練課程；須由實際授課教官親自簽領，且領取者該案不得重複申請行政敘獎。"))
    if total > PROCUREMENT_THRESHOLD:
        f.append(Finding(WARN, "總經費超過 15 萬元",
                         "陳報單須敘明採購法依據並加會政風室，不可拆分發包。本產生器目前不處理這類案件，請另洽承辦人。"))

    # 9. 品項名稱：避免「贈品」
    gifts = [i["name"] or "（未命名）" for i in ctx.items if "贈品" in (i["name"] or "")]
    if gifts:
        f.append(Finding(WARN, "品項名稱使用「贈品」",
                         "建議依性質改列「宣導品」；若是有獎徵答再改列「獎品」。項目：" + "、".join(gifts) + "。"))

    # 10. 備註欄
    no_use = [i["name"] or "（未命名）" for i in ctx.items if not i["use"]]
    if no_use:
        f.append(Finding(ERROR, "概算表有項目沒填「用途說明」", "、".join(no_use) + "。每個品項的備註都要寫明用途與經費來源（經費來源系統會自動補上）。"))
    else:
        f.append(Finding(OK, "每個品項都有用途說明，經費來源已自動寫入備註", ""))

    # 11. 課程表（有填時間或日期但內容空白的列仍保留，列數與畫面一致）
    courses = list(ctx.courses)
    if not courses:
        f.append(Finding(ERROR, "沒有課程表", "辦理研習、訓練活動時，計畫書內應列出詳細課程表。"))
    else:
        f.append(Finding(OK, "已列出課程表", f"共 {len(courses)} 列。"))
        empty = [str(i) for i, course in enumerate(courses, 1) if not str(course.get("content") or "").strip()]
        if empty:
            f.append(Finding(WARN, "課程表有列未填課程內容",
                             "第 " + "、".join(empty) + " 列仍會列入 Word 與 Excel，請補上課程內容，或刪除用不到的列。"))
        if ctx.start and ctx.end and ctx.end >= ctx.start:
            outside = []
            for i, course in enumerate(courses, 1):
                course_date = course.get("date")
                if course_date and (course_date < ctx.start or course_date > ctx.end):
                    outside.append(f"第{i}列（{roc_date(course_date)}）")
            if outside:
                f.append(Finding(ERROR, "課程日期不在活動期間",
                                 "、".join(outside) + f"。須介於 {roc_date(ctx.start)} 至 {roc_date(ctx.end)}。"))

    # 11. 人數與餐點份數（提醒）
    if ctx.headcount > 0:
        for i in ctx.items:
            if i["kind"] == "餐費" and i["unit"] in ("份", "個", "人") and i["qty"] > ctx.headcount * ctx.days * 3:
                f.append(Finding(WARN, f"「{i['name']}」數量偏多",
                                 f"{int(i['qty'])} {i['unit']}，參訓 {ctx.headcount} 人、{ctx.days} 天，請確認是否合理。"))
    return f


# ---------------------------------------------------------------- 文字範本
def default_background(ctx):
    return (f"{ctx.unit}為提升所屬人員{_training(ctx).removesuffix('訓練')}相關專業技能，強化消防人員與義消人員共同出勤執行各項救災勤務時之"
            f"合作默契，提升救災效率及安全性，爰辦理本訓練。")


def _training(ctx):
    n = ctx.name_for_title
    for tail in ("活動", "訓練"):
        if n.endswith(tail):
            n = n[: -len(tail)]
    return (n or "本項") + "訓練"


def _end(text):
    t = text.strip()
    return t if t.endswith(("。", "！", "？")) else t + "。"


def default_purpose(ctx):
    return (f"藉由{_training(ctx)}，使參訓人員熟悉相關裝備器材之使用及操作方法，提升專業技能與實務能力，"
            f"強化整體救災戰力，保障民眾生命財產安全，特訂定本計畫。")


def default_method(ctx):
    return ("採集中訓練方式辦理，由授課教官講解相關技術及裝備操作要領，並由每位學員實際操作各項訓練技能，"
            "教官逐一指導動作及操作技巧。")


def default_rules(ctx):
    return ("一、參訓人員請準時於集合地點報到點名。\n"
            "二、參訓人員一律穿著救助服或整齊服裝到訓。\n"
            "三、訓練所需裝備器具，由本單位及各授課教官預先檢修及協助備妥。")


def fund_text(ctx):
    who = format_councilors(ctx.councilors)
    return (f"本案訓練經費共計新臺幣{to_cn_amount(ctx.total)}元整（如附件二），擬由{who}建議縣府補助新臺幣"
            f"{to_cn_amount(ctx.subsidy)}元整，其餘不足部分由{ctx.unit}自行籌措。")


def sections(ctx):
    """回傳計畫書章節 [(標題, [段落…])]。"""
    bg = _end(ctx.background) if ctx.background.strip() else default_background(ctx)
    pu = _end(ctx.purpose) if ctx.purpose.strip() else default_purpose(ctx)
    me = _end(ctx.method) if ctx.method.strip() else default_method(ctx)
    ru = ctx.rules.strip() or default_rules(ctx)

    org = [
        "一、指導單位：臺東縣政府、臺東縣議會。",
        "二、主辦單位：臺東縣消防局。",
        f"三、承辦單位：{ctx.unit.strip()}。",
    ]
    if ctx.co_organizer.strip():
        org.append(f"四、協辦單位：{ctx.co_organizer.strip()}。")

    out = [
        ("緣由", [bg]),
        ("目的", [pu]),
        ("辦理單位", org),
        ("訓練日期及地點", [f"一、時間：{ctx.date_text}。", f"二、地點：{ctx.place.strip()}。"]),
        ("訓練方式", [me]),
        ("訓練對象", [f"{ctx.audience.strip()}" + (f"，共計{ctx.headcount}人。" if ctx.headcount else "。")]),
    ]
    if ctx.instructors.strip():
        out.append(("訓練師資", [_end(ctx.instructors)]))
    out += [
        ("訓練課程", ["詳如附件一。"]),
        ("訓練經費", [fund_text(ctx)]),
        ("規定事項", ru.split("\n")),
    ]
    if ctx.supervisor.strip():
        out.append(("督導考核", [_end(ctx.supervisor)]))
    out.append(("其他", ["本計畫如有未盡事宜得隨時補充修正之。"]))
    return out


def budget_title(ctx):
    return f"臺東縣消防局辦理{ctx.unit.strip()}「{ctx.year}年度{ctx.activity}」經費概算表"


def budget_note(ctx):
    if ctx.self_fund < -0.5:
        self_text = "—（補助金額超過總經費，請修正）"
    else:
        self_text = f"{money(ctx.self_fund)}元整"
    return (f"說明：{ctx.source_label}：{money(ctx.subsidy)}元整　自籌款：{self_text}　"
            f"經費總計：新臺幣{money(ctx.total)}元整")


def markdown_preview(ctx):
    lines = [f"### {ctx.title1}", f"### 「{ctx.title2}」", ""]
    for i, (h, paras) in enumerate(sections(ctx)):
        lines.append(f"**{_CN_SECTION[i]}、{h}**")
        lines.append("")
        for p in paras:
            lines.append(p + "  ")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- Word
def _set_font(run, size=14, bold=False, name="標楷體"):
    from docx.oxml.ns import qn
    run.font.name = name
    run.font.size = __import__("docx").shared.Pt(size)
    run.bold = bold
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        from docx.oxml import OxmlElement
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), name)


def _para(doc, text, size=14, bold=False, align=None, indent=None, space_after=6):
    from docx.shared import Pt, Cm
    p = doc.add_paragraph()
    r = p.add_run(text)
    _set_font(r, size, bold)
    if align:
        p.alignment = align
    if indent is not None:
        p.paragraph_format.left_indent = Cm(indent)
    p.paragraph_format.space_after = Pt(space_after)
    return p


def _table(doc, header, rows, widths=None, size=12):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(h)
        _set_font(r, size, True)
        c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            r = cells[i].paragraphs[0].add_run(str(v))
            _set_font(r, size)
    if widths:
        from docx.shared import Cm
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    return t


def build_docx(ctx):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm

    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin = sec.bottom_margin = Cm(2.0)

    _para(doc, ctx.title1, 18, True, WD_ALIGN_PARAGRAPH.CENTER, space_after=0)
    _para(doc, f"「{ctx.title2}」", 18, True, WD_ALIGN_PARAGRAPH.CENTER, space_after=12)

    for i, (h, paras) in enumerate(sections(ctx)):
        _para(doc, f"{_CN_SECTION[i]}、{h}：", 14, True, space_after=2)
        for p in paras:
            _para(doc, p, 14, indent=1.0, space_after=4)

    doc.add_page_break()
    _para(doc, "附件一", 12)
    course_label = ctx.name_for_title
    _para(doc, f"{ctx.year}年{ctx.unit.strip()}{course_label}訓練課程表", 16, True, WD_ALIGN_PARAGRAPH.CENTER)
    _table(doc, ["日期", "時間", "課程內容", "教官／講師"],
           [[roc_date(c["date"]) if c.get("date") else "", c.get("time", ""), c.get("content", ""), c.get("teacher", "")]
            for c in ctx.courses],
           [3.4, 3.2, 6.4, 3.6])
    _para(doc, "備註：一、訓練地點：" + ctx.place.strip() + "。二、各項訓練課程得視現場環境、天候及實際訓練情形適時調整。", 12)

    doc.add_page_break()
    _para(doc, "附件二", 12)
    _para(doc, budget_title(ctx), 16, True, WD_ALIGN_PARAGRAPH.CENTER)
    rows = [[n + 1, it["name"], money(it["qty"]), it["unit"], money(it["price"]), money(it["total"]), it["remark"]]
            for n, it in enumerate(ctx.items)]
    rows.append(["", "合計", "", "", "", money(ctx.total), "單位：元"])
    _table(doc, ["項次", "項目", "數量", "單位", "單價", "合計", "備註（用途及經費來源）"], rows,
           [1.2, 3.0, 1.4, 1.2, 1.8, 2.0, 6.0], 11)
    _para(doc, budget_note(ctx), 12)

    roster = [r for r in ctx.roster if str(r.get("name") or "").strip()]
    if roster:
        doc.add_page_break()
        _para(doc, "附件三", 12)
        _para(doc, f"{ctx.year}年{ctx.unit.strip()}{course_label}參訓名冊", 16, True, WD_ALIGN_PARAGRAPH.CENTER)
        _table(doc, ["編號", "單位", "職稱", "姓名"],
               [[n + 1, r.get("unit", ""), r.get("title", ""), r.get("name", "")] for n, r in enumerate(roster)],
               [1.5, 5.0, 4.0, 4.0])

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- Excel
def build_xlsx(ctx):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, Side
    wb = Workbook()
    ws = wb.active
    ws.title = "經費概算表"
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    ws.merge_cells("A1:G1")
    ws["A1"] = budget_title(ctx)
    ws["A1"].font = Font(name="標楷體", size=14, bold=True)
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 36
    head = ["項次", "項目", "數量", "單位", "單價", "合計", "備註（用途及經費來源）"]
    for c, h in enumerate(head, 1):
        cell = ws.cell(row=2, column=c, value=h)
        cell.font = Font(name="標楷體", bold=True)
        cell.alignment = Alignment(horizontal="center")
        cell.border = border
    r = 3
    for n, it in enumerate(ctx.items, 1):
        vals = [n, it["name"], it["qty"], it["unit"], it["price"], f"=C{r}*E{r}", it["remark"]]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = Font(name="標楷體")
            cell.border = border
            cell.alignment = Alignment(wrap_text=True, vertical="center")
            if c in (3, 5, 6):
                cell.number_format = "#,##0"
        r += 1
    ws.cell(row=r, column=2, value="合計").font = Font(name="標楷體", bold=True)
    ws.cell(row=r, column=6, value=f"=SUM(F3:F{r - 1})").number_format = "#,##0"
    ws.cell(row=r, column=7, value="單位：元")
    for c in range(1, 8):
        ws.cell(row=r, column=c).border = border
    ws.merge_cells(start_row=r + 1, start_column=1, end_row=r + 1, end_column=7)
    ws.cell(row=r + 1, column=1, value=budget_note(ctx)).font = Font(name="標楷體")
    for col, w in zip("ABCDEFG", [6, 22, 8, 8, 10, 12, 52]):
        ws.column_dimensions[col].width = w

    ws2 = wb.create_sheet("課程表")
    for c, h in enumerate(["日期", "時間", "課程內容", "教官／講師"], 1):
        ws2.cell(row=1, column=c, value=h).font = Font(name="標楷體", bold=True)
    for n, cr in enumerate(ctx.courses, 2):
        ws2.cell(row=n, column=1, value=roc_date(cr["date"]) if cr.get("date") else "")
        ws2.cell(row=n, column=2, value=cr.get("time", ""))
        ws2.cell(row=n, column=3, value=cr.get("content", ""))
        ws2.cell(row=n, column=4, value=cr.get("teacher", ""))
        for col in range(1, 5):
            ws2.cell(row=n, column=col).font = Font(name="標楷體")
    for col, w in zip("ABCD", [16, 18, 40, 18]):
        ws2.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def example_inputs(today=None):
    """載入範例用的完整資料。必填欄位都有值，且開始日落在 1 個月又 1 週之後。"""
    today = today or date.today()
    start = today + timedelta(days=45)
    return {
        "unit": "達仁義消分隊",
        "name": "繩索救助訓練",
        "year": roc_year(today),
        "start": start,
        "end": start,
        "place": "達仁分隊訓練廣場",
        "audience": "本大隊所屬達仁義消人員（含教官團）",
        "headcount": 30,
        "co_organizer": "",
        "councilors": "王議員",
        "instructors": "由本分隊具備陸域救助訓練教官或助教資格之人員組成",
        "supervisor": "本大隊大隊長、副大隊長隨時督導考核",
        "subsidy": 20000,
        "items": [
            {"name": "便當", "kind": "餐費", "qty": 60, "unit": "份", "price": 100, "use": "供訓練人員中餐及晚餐"},
            {"name": "棚架", "kind": "一般", "qty": 2, "unit": "式", "price": 3500, "use": "供訓練人員休息使用"},
            {"name": "礦泉水", "kind": "一般", "qty": 10, "unit": "箱", "price": 150, "use": "供訓練人員飲用"},
            {"name": "救助吊帶", "kind": "一般", "qty": 5, "unit": "條", "price": 2200, "use": "供繩索救援確保訓練人員安全"},
        ],
        "courses": [
            {"date": start, "time": "08:10－09:00", "content": "學員簽到", "teacher": "分隊幹部"},
            {"date": start, "time": "09:10－12:00", "content": "繩索救助基礎操作", "teacher": "訓練教官"},
            {"date": start, "time": "13:30－16:30", "content": "確保系統實務演練", "teacher": "訓練教官"},
        ],
    }


def example_context(today=None):
    data = example_inputs(today)
    return PlanContext(
        plan_type="training",
        unit=data["unit"],
        year=data["year"],
        name=data["name"],
        start=data["start"],
        end=data["end"],
        place=data["place"],
        audience=data["audience"],
        headcount=data["headcount"],
        method="",
        instructors=data["instructors"],
        co_organizer=data["co_organizer"],
        supervisor=data["supervisor"],
        councilors=data["councilors"],
        subsidy=data["subsidy"],
        items=normalize_items(data["items"], subsidy=data["subsidy"]),
        courses=data["courses"],
        roster=[],
    )
