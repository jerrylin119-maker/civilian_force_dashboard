# -*- coding: utf-8 -*-
"""
補捐助「計畫書／經費概算表 草稿產生器」。

- 以固定範本把同仁填的資料套進計畫書與概算表，不是自由生成文字，格式與用字固定。
- 產出前先套用申請階段的規則檢查（自籌 30%、餐費紀念品 50%、雜支 5%、用字、備註欄、課程表…）。
- 輸出 Word 計畫書（.docx）與 Excel 概算表（.xlsx，合計用公式）。
- 純函式、不依賴 Streamlit，也不儲存任何輸入資料。

目前有三種計畫類型：專業訓練活動、活動類（表揚／研習／文康）、設備類（購置設備）。
經費來源可有多筆：議員（建議縣府補助）、鄉鎮市公所代表（建議公所補助），各自列金額，加總為補助總額。
要新增類型時，在 PLAN_TYPES 加一筆（含畫面欄位名稱），並在 sections() 提供對應的章節範本即可。
活動類的歷史去識別化範例放在 plan_cases.py。
"""

import calendar
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from subsidy_check import (
    MEAL_KINDS, MEAL_SOUVENIR_RATIO, MISC_RATIO, PROCUREMENT_THRESHOLD,
    SELF_FUND_RATIO, SELF_FUND_THRESHOLD, OK, WARN, ERROR, Finding,
)

# app.py 用這個數字判斷記憶體裡的模組是不是舊版。Streamlit Cloud 重新部署時
# 常常只重跑 app.py，sys.modules 仍留著上一版 plan_generator。
MODULE_REVISION = 10

PLAN_TYPES = {
    "training": {
        "label": "專業訓練活動（議員建議補助款）",
        "desc": "義消／分隊辦理的專業訓練、研習活動（救災、救護、宣導、環境教育等），經費來源為議員建議補助款加自籌款。",
        "source_label": "議員建議補助款",
        "kind_word": "訓練",
        "audience_label": "參訓對象",
        "headcount_label": "參訓人數",
        "schedule_label": "課程表",
        "method_label": "訓練方式",
        "schedule_required": True,
        "show_instructors": True,
    },
    "activity": {
        "label": "活動類（表揚／研習／文康）",
        "desc": "績優表揚、縣外研習觀摩、環境教育暨文康等活動類案件，經費來源為議員建議補助款加自籌款。"
                "名稱含「研習」「環境教育」「訓練」的活動仍須列出流程（行程）表。",
        "source_label": "議員建議補助款",
        "kind_word": "活動",
        "audience_label": "參加對象",
        "headcount_label": "參加人數",
        "schedule_label": "活動流程／行程表",
        "method_label": "活動內容",
        "schedule_required": False,
        "show_instructors": False,
    },
    "equipment": {
        "label": "設備類（購置設備）",
        "desc": "義消／分隊購置救災、訓練、辦公設備（資本門）的案件，經費來源為議員或鄉鎮市公所代表建議補助款加自籌款。"
                "須附廠商估價單與縣政府受理議員建議購置設備類案件申請審核表；核銷時另附財產增加單。",
        "source_label": "議員建議補助款",
        "kind_word": "購置",
        "audience_label": "使用單位",
        "headcount_label": "使用人數",
        "schedule_label": "",
        "method_label": "購置說明",
        "schedule_required": False,
        "show_instructors": False,
        "dated": False,
    },
}
# 名稱含這些字的活動類案件，仍須附流程（行程）表，證明活動實質內容。
SCHEDULE_KEYWORDS = ("研習", "環境教育", "訓練")

ITEM_KINDS = ["一般", "餐費", "紀念品", "雜支", "內聘鐘點費", "二代健保補充保費", "設備購置"]
FORBIDDEN_WORDS = ("聯誼", "餐敘", "聯歡", "健身")
NHI_KIND = "二代健保補充保費"
# 縣府核定函（115 年 7 月 24 日府民捐字第 1150164990 號）：油資、過路費、停車費不予補助。
NO_SUBSIDY_WORDS = ("油資", "過路費", "停車費")
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


def submission_deadline(activity_start):
    """活動類案件送到局本部的期限：活動開始日減 1 個日曆月，再減 7 天。"""
    return add_months(activity_start, -1) - timedelta(days=7)


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


def format_people(text, title):
    """每位人員只留一個職稱（議員、代表）。空白時用「ＯＯ」加職稱。"""
    raw = str(text or "").strip()
    parts = re.split(r"[、,，;；/]+", raw)
    names = []
    for part in parts:
        part = re.sub(rf"\s*{title}\s*$", "", part).strip()
        if part:
            names.append(part + title)
    return "、".join(names) if names else "ＯＯ" + title


SOURCE_KIND_NAMES = {"councilor": "議員", "rep": "代表"}
_SOURCE_KIND_ALIASES = {"議員": "councilor", "councilor": "councilor", "代表": "rep", "民代表": "rep", "rep": "rep"}


def normalize_sources(sources, councilors="", subsidy=0):
    """補助來源清單 [{"kind": councilor|rep, "names", "township", "amount"}]。

    沒有填任何來源時，用 councilors 與 subsidy 組成單一議員來源（舊版輸入仍可用）。
    """
    out = []
    for src in sources or []:
        if not isinstance(src, dict):
            continue
        kind = _SOURCE_KIND_ALIASES.get(_text(src.get("kind")), "councilor")
        names = _text(src.get("names"))
        township = _text(src.get("township"))
        amount = max(0.0, _f(src.get("amount")))
        if not names and not township and amount == 0:
            continue
        out.append({"kind": kind, "names": names, "township": township, "amount": amount})
    if not out:
        out = [{"kind": "councilor", "names": str(councilors or "").strip(), "township": "", "amount": max(0.0, _f(subsidy))}]
    return out


def _township_name(src):
    return src["township"] or "ＯＯ公所"


def source_label_of(src):
    """概算表備註用的來源名稱。"""
    if src["kind"] == "rep":
        return f"{_township_name(src)}代表建議補助款"
    return "議員建議補助款"


def source_phrase(src):
    """計畫書經費段的單筆來源句（含金額）。"""
    amount = f"新臺幣{to_cn_amount(src['amount'])}元整"
    if src["kind"] == "rep":
        town = _township_name(src)
        return f"{town}{format_people(src['names'], '代表')}建議{town}補助{amount}"
    return f"{format_councilors(src['names'])}建議縣府補助{amount}"


def source_who(sources):
    """陳報單用的來源名稱：議員姓名加公所名稱，例：王議員、李議員及卑南鄉公所。"""
    people = [format_councilors(s["names"]) for s in sources if s["kind"] == "councilor"]
    towns = []
    for s in sources:
        if s["kind"] == "rep" and _township_name(s) not in towns:
            towns.append(_township_name(s))
    left, right = "、".join(people), "、".join(towns)
    return "及".join(x for x in (left, right) if x)


AWARD_KINDS = ("嘉獎", "記功", "記大功")


def normalize_awards(awards):
    """敘獎額度 [{"role", "count", "kind", "times"}]。沒填職務或次數為 0 的列略過。"""
    out = []
    for a in awards or []:
        if not isinstance(a, dict):
            continue
        role = _text(a.get("role"))
        times = int(_f(a.get("times")))
        count = int(_f(a.get("count")))
        kind = _text(a.get("kind")) or "嘉獎"
        if not role or times <= 0 or count <= 0:
            continue
        out.append({"role": role, "count": count, "kind": kind if kind in AWARD_KINDS else "嘉獎", "times": times})
    return out


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


def _remark(use, subsidy, self_amt, source_label, source_parts=None):
    """概算表備註：只放用途說明。「○元由議員建議補助款支應、○元由自籌款支應」依現行規定不再顯示，
    各項補助與自籌金額看「補助款分配計算預覽」。"""
    return (use or "").strip()


def _no_subsidy_words(item):
    """品項名稱中出現的「不予補助」字眼（油資、過路費、停車費）。"""
    name = str(item.get("name") or "")
    return [w for w in NO_SUBSIDY_WORDS if w in name]


def _eligible_for_subsidy(item):
    return (
        item.get("kind") != NHI_KIND
        and not _no_subsidy_words(item)
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
    sources: list = field(default_factory=list)
    awards: list = field(default_factory=list)
    meet: str = ""
    org_battalion: str = ""   # 登入帳號所屬大隊，陳報單抬頭用
    org_unit: str = ""       # 登入帳號的分隊；大隊帳號留空
    award_basis: str = ""    # amount / days / custom / none；空白＝有填敘獎額度就是 custom，否則不敘獎
    case_no: str = ""        # 登錄案件管制後取得的案號，會印在計畫書、概算表、陳報單上

    # ---- 衍生值
    def __post_init__(self):
        self.courses = prepare_courses(self.courses, self.start, self.end)
        given = bool(self.sources)
        self.sources = normalize_sources(self.sources, self.councilors, self.subsidy)
        self.awards = normalize_awards(self.awards)
        if given:
            self.subsidy = sum(s["amount"] for s in self.sources)

    @property
    def name_for_title(self):
        return strip_activity_year(self.name).strip()

    @property
    def activity(self):
        n = self.name_for_title
        if not n:
            return ""
        if self.plan_type == "equipment":
            return "購置" + n.removeprefix("購置").removesuffix("計畫")
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
            return "（尚未選擇日期）" if self.info.get("dated", True) else "（日期未定）"
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

    @property
    def info(self):
        return PLAN_TYPES[self.plan_type]

    @property
    def needs_schedule(self):
        """這份計畫是否須列出課程（流程、行程）表。"""
        if self.plan_type == "equipment":
            return False
        if self.info["schedule_required"]:
            return True
        return any(word in (self.name or "") for word in SCHEDULE_KEYWORDS)


def normalize_items(rows, subsidy=0, source_label="議員建議補助款", sources=None):
    """把畫面輸入的列轉成概算項目。補助款依金額比例分配，並產生「用途＋經費來源」備註。

    使用者只填數量、單價、用途、類別與補助總額；各列不再另填補助款。
    有多筆補助來源（議員、公所代表）時，每個來源各自依比例分配，備註分別寫明各來源支應多少。
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
    if sources:
        srcs = normalize_sources(sources, "", subsidy)
        pairs = [(source_label_of(src), src["amount"]) for src in srcs]
    else:
        pairs = [(source_label, _f(subsidy))]
    per_item = [[] for _ in items]
    for label, amount in pairs:
        trial = [dict(item) for item in items]
        allocate_subsidy(trial, amount)
        for n, t in enumerate(trial):
            per_item[n].append((label, t["subsidy"]))
    allocate_subsidy(items, sum(amount for _label, amount in pairs))
    for item, parts in zip(items, per_item):
        if len(pairs) > 1:
            item["subsidy"] = sum(a for _l, a in parts)
            item["self"] = item["total"] - item["subsidy"]
        merged = {}
        for label, amount in parts:
            merged[label] = merged.get(label, 0) + amount
        item["by_source"] = list(merged.items())
        self_amt = item["self"] if item["self"] > 0.5 else 0
        item["remark"] = _remark(item["use"], item["subsidy"], self_amt, source_label,
                                 item["by_source"] if len(pairs) > 1 else None)
    return items


def _text(v):
    """畫面表格空格可能是 None 或 NaN，統一轉成空字串。"""
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return str(v).strip()


def _f(v):
    try:
        if v is None or v != v:
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# 注意要點、錯誤樣態在網頁上的編號會隨承辦人增刪而變，這裡以標題對照，不寫死編號。
RULE_WORDING = "注意要點「計畫書命名與用字」；錯誤樣態「計畫名稱出現「聯誼」「餐敘」「聯歡」「健身」等字眼」"
RULE_AWARD = "注意要點「計畫書內容：課程表與敘獎」；錯誤樣態「計畫書載明行政獎勵字句」"
RULE_COURSE = "注意要點「計畫書內容：課程表與敘獎」；錯誤樣態「研習、訓練、環境教育活動未附課程表」"
RULE_RATIO = "注意要點「經費比例上限（自籌款、餐費紀念品、雜支）」"
RULE_SELF_FUND = RULE_RATIO + "；錯誤樣態「自籌款未達總經費 30%」"
RULE_MEAL = RULE_RATIO + "；錯誤樣態「餐費及紀念品超過申請補助金額 50%（或未分來源計算）」"
RULE_DEADLINE = "注意要點「申請流程與發文單位」；錯誤樣態「活動類案件未於活動 1 個月前送達局本部」"
RULE_NHI = "注意要點「二代健保補充保費與概算表備註欄」；錯誤樣態「二代健保補充保費用補助款支應」"
RULE_REMARK = "注意要點「二代健保補充保費與概算表備註欄」；錯誤樣態「概算表備註欄位不清楚」"
RULE_GIFT = "注意要點「品項名稱適法性（宣導品 vs. 贈品/獎品）」"
RULE_INTERNAL = "注意要點「內聘教官、助教鐘點費」"
RULE_PROCUREMENT = "注意要點「陳報單：採購法規範（總經費逾 15 萬元）」；錯誤樣態「總經費逾 15 萬元，未敘明採購法依據或未加會政風室」"
RULE_EQUIPMENT = "錯誤樣態「設備類案件缺廠商估價單或縣府審核表」（活動類補助款不得用於資本門）"
RULE_PERSONAL_GEAR = "常見問答「活動費用用於採購服裝」；設備工程類捐助款不得支應採購個人服裝及裝備"
RULE_EQUIPMENT_KIND = "注意要點「計畫書命名（設備類）」；設備類為購置設備（資本門）"
PERSONAL_GEAR_WORDS = ("服裝", "制服", "個人裝備", "外套", "T恤", "鞋")
RULE_NO_SUBSIDY = "縣府核定函：「油資、過路費、停車費」不予補助"
RULE_MEAL_QTY = ("編列原則「名冊人數需與便當、物品數量合理對應」；工作人員名冊若為 30 人，便當不應無故暴增至 100 多份，"
                 "需於備註欄清楚註明數量來源與用途")
ALL_CLEAR_MESSAGE = "計畫符合現行補捐助規定，可以開始匯出"


def _issue(level, title, detail, *, rule, where, comparison, suggestion):
    return Finding(level, title, detail, rule=rule, where=where, comparison=comparison, suggestion=suggestion)


def _budget_where(names):
    labels = [name or "（未命名）" for name in names]
    if not labels:
        return "經費概算表"
    return "經費概算表" + "".join(f"「{name}」" for name in labels)


def compliance_banner(findings):
    """回傳 (pass / warn / error, 標題訊息)。全部通過時用固定文句。"""
    n_err = sum(1 for item in findings if item.level == ERROR)
    n_warn = sum(1 for item in findings if item.level == WARN)
    if n_err:
        return "error", f"有 {n_err} 項不符規定，請依下列說明逐項修正後再送審（仍可先下載草稿）。"
    if n_warn:
        return "warn", f"沒有不符規定的項目，另有 {n_warn} 項提醒，請另外確認。"
    return "pass", ALL_CLEAR_MESSAGE


def format_compliance_item(finding):
    """把單一檢查結果排成：規則、位置、現況與規定、修正建議。"""
    lines = [f"**{finding.title}**"]
    rule = getattr(finding, "rule", "") or ""
    where = getattr(finding, "where", "") or ""
    comparison = getattr(finding, "comparison", "") or ""
    suggestion = getattr(finding, "suggestion", "") or ""
    if rule:
        lines.append(f"規則：{rule}")
    if where:
        lines.append(f"位置：{where}")
    if comparison:
        lines.append(f"現況與規定：{comparison}")
    if suggestion:
        lines.append(f"修正建議：{suggestion}")
    elif finding.detail:
        lines.append(finding.detail)
    return "\n\n".join(lines)


# ---------------------------------------------------------------- 規則檢查（申請階段）
def check_plan(ctx, today=None):
    today = today or date.today()
    f = []

    # 1. 用字
    text_all = " ".join([ctx.name, ctx.unit, ctx.background, ctx.purpose, ctx.method, ctx.rules] +
                        [i["name"] for i in ctx.items])
    bad = [w for w in FORBIDDEN_WORDS if w in text_all]
    if bad:
        field_hits = []
        for label, value in (
            ("活動名稱", ctx.name), ("申請單位", ctx.unit), ("緣由", ctx.background),
            ("目的", ctx.purpose), (ctx.info["method_label"], ctx.method), ("規定事項", ctx.rules),
        ):
            if any(word in (value or "") for word in bad):
                field_hits.append(label)
        item_hits = [i["name"] or "（未命名）" for i in ctx.items if any(word in (i["name"] or "") for word in bad)]
        where = "、".join(field_hits)
        if item_hits:
            where = (where + "、" if where else "") + _budget_where(item_hits)
        f.append(_issue(
            ERROR, "名稱或內容出現不得使用的字眼",
            f"請移除：{'、'.join(bad)}。計畫須以社會公益、教育、訓練、研習為主。",
            rule=RULE_WORDING,
            where=where or "活動名稱或計畫內容",
            comparison=f"出現不得使用的字眼：{'、'.join(bad)}",
            suggestion="請移除這些字眼，並改以社會公益、教育、訓練或研習來敘述。",
        ))
    else:
        f.append(Finding(OK, "名稱與內容沒有「聯誼、餐敘、聯歡、健身」等字眼", ""))
    award_fields = []
    if "獎勵" in (ctx.background or ""):
        award_fields.append("緣由")
    if "獎勵" in (ctx.purpose or ""):
        award_fields.append("目的")
    if "獎勵" in (ctx.rules or "") or "敘獎" in (ctx.rules or ""):
        award_fields.append("規定事項")
    if award_fields:
        f.append(_issue(
            ERROR, "計畫書內不得出現行政獎勵／敘獎字句",
            "敘獎事項只在陳報單敘明並加會人事室。",
            rule=RULE_AWARD,
            where="、".join(award_fields),
            comparison="內容出現「獎勵」或「敘獎」",
            suggestion="請從計畫書刪除敘獎字句，改在陳報單敘明並加會人事室。",
        ))

    # 2. 必填
    audience_label = ctx.info["audience_label"]
    miss = [n for n, v in [("申請單位", ctx.unit), ("活動名稱", ctx.name), ("地點", ctx.place), (audience_label, ctx.audience)] if not str(v).strip()]
    if miss:
        f.append(_issue(
            ERROR, "尚有必填欄位未填", "、".join(miss),
            rule=f"計畫書必填欄位（申請單位、活動名稱、地點、{audience_label}）",
            where="、".join(miss),
            comparison="尚未填寫：" + "、".join(miss),
            suggestion="請補上這些欄位後再檢查。",
        ))

    # 2b. 活動名稱若已含年度，標題會自動拿掉，避免「115年度一一五年度…」
    raw_name = ctx.name.strip()
    if raw_name and ctx.name_for_title != raw_name:
        if not ctx.name_for_title:
            f.append(_issue(
                ERROR, "活動名稱只寫了年度",
                "請改填活動名稱本身，不必再寫「115年度」或「一一五年度」，標題會自動加上年度。",
                rule="注意要點「計畫書命名與用字」",
                where="活動名稱",
                comparison=f"目前只寫了「{raw_name}」",
                suggestion="請改填活動名稱本身，不必再寫年度，標題會自動加上。",
            ))
        else:
            f.append(_issue(
                WARN, "活動名稱含有年度，已自動省略",
                f"標題使用「{ctx.title2}」，避免年度重複。",
                rule="注意要點「計畫書命名與用字」",
                where="活動名稱",
                comparison=f"原名稱「{raw_name}」含年度，標題改用「{ctx.title2}」",
                suggestion="可維持現況（系統已省略年度）；若要自行修正，請把活動名稱裡的年度拿掉。",
            ))

    # 3. 日期（須預留 1 個月 + 7 天給大隊初審，再送局本部）。設備類沒有活動日期，不檢查。
    if not ctx.info.get("dated", True):
        pass
    elif ctx.start is None or ctx.end is None:
        missing_dates = []
        if ctx.start is None:
            missing_dates.append("開始日期")
        if ctx.end is None:
            missing_dates.append("結束日期")
        f.append(_issue(
            ERROR, "尚未選擇開始或結束日期", "請選擇活動日期。",
            rule=RULE_DEADLINE,
            where="活動日期",
            comparison="尚未選擇：" + "、".join(missing_dates),
            suggestion="請選擇開始與結束日期；開始日須在今天起 1 個月又 1 週以後。",
        ))
    elif ctx.end < ctx.start:
        f.append(_issue(
            ERROR, "結束日期早於開始日期", "請修正日期區間，結束日期不可早於開始日期。",
            rule="活動日期區間",
            where="活動日期",
            comparison=f"結束日期 {ctx.end.isoformat()} 早於開始日期 {ctx.start.isoformat()}",
            suggestion="請把結束日期改到開始日期當天或之後。",
        ))
    else:
        lead = (ctx.start - today).days
        earliest = earliest_activity_date(today)
        deadline = submission_deadline(ctx.start)
        if ctx.start < today:
            f.append(_issue(
                ERROR, "活動開始日期已過",
                f"開始日期 {roc_date(ctx.start)} 早於今天 {abs(lead)} 天，請改期後再送審。",
                rule=RULE_DEADLINE,
                where="活動日期",
                comparison=f"開始日期 {ctx.start.isoformat()}，今日 {today.isoformat()} 已過 {abs(lead)} 天",
                suggestion=f"請把開始日期改到 {earliest.isoformat()}（含）以後再送審。",
            ))
        elif ctx.start == today:
            f.append(_issue(
                ERROR, "活動開始日期就是今天", "已來不及完成大隊初審並送達局本部，請改期。",
                rule=RULE_DEADLINE,
                where="活動日期",
                comparison=f"開始日期 {ctx.start.isoformat()} 就是今日 {today.isoformat()}",
                suggestion=f"請把開始日期改到 {earliest.isoformat()}（含）以後。",
            ))
        elif deadline < today:
            late = (today - deadline).days
            f.append(_issue(
                WARN, "已超過送件期限，不足 1 個月又 1 週",
                f"送件期限是活動日減 1 個月再減 7 天（{roc_date(deadline)}），"
                f"今天已晚 {late} 天。開始日期至少要在今天起 1 個月再加 7 天"
                f"（{roc_date(earliest)}）以後，才來得及大隊初審並送達局本部。"
                f"縣府另要求活動舉辦日 5 日前送達縣府。",
                rule=RULE_DEADLINE,
                where="活動日期",
                comparison=f"屆時送局期限 {deadline.isoformat()}，今日 {today.isoformat()} 已逾 {late} 天",
                suggestion=f"請把開始日期改到 {earliest.isoformat()}（含）以後，才來得及大隊初審並送達局本部。",
            ))
        else:
            f.append(Finding(OK, "活動日期已預留 1 個月又 1 週",
                             f"距離活動還有 {lead} 天。送件期限（活動日減 1 個月再減 7 天）為 {roc_date(deadline)}，"
                             f"今天尚未超過。最早可辦理日為 {roc_date(earliest)}。"))

    # 4. 概算表
    if not ctx.items:
        f.append(_issue(
            ERROR, "概算表沒有任何項目", "請至少輸入一個經費項目。",
            rule="經費概算表",
            where="經費概算表",
            comparison="沒有任何經費項目",
            suggestion="請至少輸入一個經費項目（數量、單價、用途說明與類別）。",
        ))
        return f
    total, sub = ctx.total, ctx.subsidy
    bad_amount_items = [i for i in ctx.items if i["qty"] <= 0 or i["price"] <= 0]
    bad_amount = [i["name"] or "（未命名）" for i in bad_amount_items]
    if bad_amount:
        bits = []
        for item in bad_amount_items:
            bits.append(f"「{item['name'] or '（未命名）'}」數量 {item['qty']:g}、單價 {item['price']:g}")
        f.append(_issue(
            ERROR, "數量或單價不是正數",
            "、".join(bad_amount) + "。數量與單價都要大於 0，零或負數不能當成有效經費。",
            rule="經費概算表（數量與單價須為正數）",
            where=_budget_where(bad_amount),
            comparison="；".join(bits) + "（規定都要大於 0）",
            suggestion="請把數量與單價都改成大於 0，或刪除該列。",
        ))
    allocated = sum(i["subsidy"] for i in ctx.items)
    if abs(allocated - sub) > 0.5:
        if any(i["kind"] == NHI_KIND for i in ctx.items) and not any(_eligible_for_subsidy(i) for i in ctx.items):
            f.append(_issue(
                ERROR, "補助款無法分配",
                "二代健保補充保費不得使用補助款，請再填其他可分配的項目，或把補助金額改為 0。",
                rule=RULE_NHI,
                where="議員建議補助款",
                comparison=f"補助金額 {money(sub)} 元，可分配項目合計 0 元",
                suggestion="請再填其他可分配的項目，或把補助金額改為 0。二代健保補充保費全數自籌。",
            ))
        else:
            f.append(_issue(
                ERROR, "補助款無法依比例分配",
                f"已分配 {money(allocated)} 元，補助金額 {money(sub)} 元。請確認各項數量、單價都是正數。",
                rule="補助款依各項金額比例分配",
                where="議員建議補助款",
                comparison=f"已分配 {money(allocated)} 元，補助金額 {money(sub)} 元",
                suggestion="請確認各項數量、單價都是正數，使分配合計等於補助金額。",
            ))
    else:
        f.append(Finding(OK, "補助款已依各項金額比例分配", f"加總 {money(sub)} 元，與議員建議補助款相同。"))
    eligible_base = sum(i["total"] for i in ctx.items if _eligible_for_subsidy(i))
    if sub > eligible_base + 0.5:
        extra = "二代健保補充保費不分配補助款、全數自籌。" if any(i["kind"] == NHI_KIND for i in ctx.items) else ""
        f.append(_issue(
            ERROR, "補助金額超過可分配項目的合計",
            f"可分配項目合計 {money(eligible_base)} 元，補助金額 {money(sub)} 元。{extra}",
            rule="補助款依各項金額比例分配",
            where="議員建議補助款",
            comparison=f"可分配項目合計 {money(eligible_base)} 元，補助金額 {money(sub)} 元",
            suggestion="請調降補助金額，或增加可分配項目，使補助金額不高於可分配合計。",
        ))
    over_items = [i for i in ctx.items if i["subsidy"] > i["total"] + 0.5]
    over = [i["name"] or "（未命名）" for i in over_items]
    if over:
        bits = [
            f"「{item['name'] or '（未命名）'}」補助款支應 {money(item['subsidy'])} 元，該項合計 {money(item['total'])} 元"
            for item in over_items
        ]
        f.append(_issue(
            ERROR, "有項目的補助款支應大於該項合計", "、".join(over),
            rule="補助款依各項金額比例分配",
            where=_budget_where(over),
            comparison="；".join(bits),
            suggestion="請調降補助金額，或提高該項數量、單價，使補助款支應不高於該項合計。",
        ))
    if sub > total + 0.5:
        f.append(_issue(
            ERROR, "補助金額大於總經費",
            f"補助 {money(sub)} 元，總經費 {money(total)} 元。請調降補助金額或增加項目，自籌款不會以負數表示。",
            rule="補助金額不得大於總經費",
            where="議員建議補助款",
            comparison=f"補助 {money(sub)} 元，總經費 {money(total)} 元，已超過 {money(sub - total)} 元",
            suggestion="請調降補助金額或增加項目。自籌款不會以負數表示。",
        ))
    elif ctx.plan_type == "equipment":
        f.append(Finding(OK, "設備類不適用「自籌款 30%」規定", "大隊初審檢核表的自籌款、餐費、雜支比例只適用活動類。"))
    elif sub > SELF_FUND_THRESHOLD:
        # 5. 自籌 30%（補助已超過總經費時不再計算，避免自籌出現負數）
        self_amt = total - sub
        ratio = self_amt / total if total else 0
        if ratio + 1e-9 < SELF_FUND_RATIO:
            need = total * SELF_FUND_RATIO - self_amt
            f.append(_issue(
                ERROR, "補助超過 2 萬元，自籌款未達總經費 30%",
                f"自籌 {money(self_amt)} 元，占 {ratio:.1%}，至少還差 {money(need)} 元。",
                rule=RULE_SELF_FUND,
                where="自籌款",
                comparison=f"自籌 {money(self_amt)} 元，占 {ratio:.1%}，規定至少 {SELF_FUND_RATIO:.0%}",
                suggestion=f"請再增加自籌至少 {money(need)} 元，或調降補助金額。",
            ))
        else:
            f.append(Finding(OK, "自籌款占總經費 30% 以上", f"自籌 {money(self_amt)} 元，占 {ratio:.1%}。"))
    else:
        f.append(Finding(OK, "補助未超過 2 萬元，不適用 30% 自籌規定", ""))

    # 6. 餐費＋紀念品 ≤ 50%
    meal_items = [i for i in ctx.items if i["kind"] in MEAL_KINDS]
    meal = sum(i["subsidy"] for i in meal_items)
    if sub > 0 and ctx.plan_type != "equipment":
        cap = sub * MEAL_SOUVENIR_RATIO
        meal_where = _budget_where([i["name"] for i in meal_items]) if meal_items else "經費概算表"
        if meal > cap + 0.5:
            f.append(_issue(
                ERROR, "餐費及紀念品超過補助金額 50%",
                f"補助款支應 {money(meal)} 元，上限 {money(cap)} 元。",
                rule=RULE_MEAL,
                where=meal_where,
                comparison=f"補助款支應 {money(meal)} 元，上限 {money(cap)} 元（補助金額的 50%），已超過 {money(meal - cap)} 元",
                suggestion="請調降餐費或紀念品，或改由自籌款支應，使補助款支應不高於上限。",
            ))
        elif cap and meal > cap * 0.9:
            f.append(_issue(
                WARN, "餐費及紀念品已接近 50% 上限",
                f"補助款支應 {money(meal)} 元／上限 {money(cap)} 元，核銷時單據稍有變動就可能超過，建議預留空間。",
                rule=RULE_MEAL,
                where=meal_where,
                comparison=f"補助款支應 {money(meal)} 元，上限 {money(cap)} 元（已超過上限的 90%）",
                suggestion="建議再調降一些餐費或紀念品，預留核銷時單據變動的空間。",
            ))
        else:
            f.append(Finding(OK, "餐費及紀念品未超過補助金額 50%", f"補助款支應 {money(meal)} 元／上限 {money(cap)} 元。"))

    # 7. 雜支 5%
    misc_items = [i for i in ctx.items if i["kind"] == "雜支"]
    misc = sum(i["total"] for i in misc_items)
    if misc > 0:
        misc_cap = total * MISC_RATIO
        if misc > misc_cap + 0.5:
            f.append(_issue(
                ERROR, "雜支超過總經費 5%",
                f"雜支 {money(misc)} 元，上限 {money(misc_cap)} 元。",
                rule=RULE_RATIO,
                where=_budget_where([i["name"] for i in misc_items]),
                comparison=f"雜支 {money(misc)} 元，上限 {money(misc_cap)} 元（總經費的 5%），已超過 {money(misc - misc_cap)} 元",
                suggestion="請把雜支降到上限以內，或改列其他適當科目。",
            ))
        else:
            f.append(Finding(OK, "雜支未超過總經費 5%", ""))

    # 8. 特殊類別（二代健保不參與分配，補助款應為 0）
    nhi_items = [i for i in ctx.items if i["kind"] == NHI_KIND]
    if any(i["subsidy"] > 0.5 for i in nhi_items):
        paid = [i for i in nhi_items if i["subsidy"] > 0.5]
        f.append(_issue(
            ERROR, "二代健保補充保費不得使用補助款支應",
            "請改由自籌款或分隊經費吸收。",
            rule=RULE_NHI,
            where=_budget_where([i["name"] for i in paid]),
            comparison="；".join(
                f"「{item['name'] or '（未命名）'}」補助款支應 {money(item['subsidy'])} 元，規定為 0 元"
                for item in paid
            ),
            suggestion="請改由自籌款或分隊經費吸收，這類項目不分配補助款。",
        ))
    elif nhi_items:
        f.append(Finding(OK, "二代健保補充保費全數由自籌款支應", "這類項目不分配補助款。"))
    equip = [i for i in ctx.items if i["kind"] == "設備購置"]
    if ctx.plan_type == "equipment":
        gear_hit = {w for i in ctx.items for w in PERSONAL_GEAR_WORDS if w in (i["name"] or "")}
        clothing = [i["name"] or "（未命名）" for i in ctx.items if any(w in (i["name"] or "") for w in PERSONAL_GEAR_WORDS)]
        if clothing:
            f.append(_issue(
                WARN, "設備類不得採購個人服裝及裝備",
                "、".join(clothing) + "：設備工程類捐助款不得支應個人服裝及裝備，裝備類應以共同裝備為宜。",
                rule=RULE_PERSONAL_GEAR,
                where=_budget_where(clothing),
                comparison="品項名稱含：" + "、".join(sorted(gear_hit)),
                suggestion="請改列共同使用的裝備；個人服裝請改走活動類（且單價不得達資本門標準 1 萬元）。",
            ))
        not_equip = [i["name"] or "（未命名）" for i in ctx.items if i["kind"] in MEAL_KINDS]
        if not_equip:
            f.append(_issue(
                WARN, "設備類概算表出現餐費或紀念品",
                "、".join(not_equip) + "：設備類案件是購置設備（資本門），餐費、紀念品應走活動類。",
                rule=RULE_EQUIPMENT_KIND,
                where=_budget_where(not_equip),
                comparison="設備類概算表含餐費或紀念品類別",
                suggestion="請移除餐費、紀念品，或改走活動類案件。",
            ))
    if equip and ctx.plan_type != "equipment":
        f.append(_issue(
            ERROR, "活動類補助款不得用於資本門（購置設備）",
            "設備購置請改走設備類案件（須附廠商估價單與縣府審核表）。",
            rule=RULE_EQUIPMENT,
            where=_budget_where([i["name"] for i in equip]),
            comparison="活動類概算表含設備購置，規定不得以活動類補助款支應資本門",
            suggestion="請從本概算表移除設備購置，改走設備類案件並附廠商估價單與縣府審核表。",
        ))
    internal = [i for i in ctx.items if i["kind"] == "內聘鐘點費"]
    if internal:
        f.append(_issue(
            WARN, "有內聘教官／助教鐘點費",
            "僅限具法源依據且須核發專業證照的實質訓練課程；須由實際授課教官親自簽領，且領取者該案不得重複申請行政敘獎。",
            rule=RULE_INTERNAL,
            where=_budget_where([i["name"] for i in internal]),
            comparison="已編列內聘教官／助教鐘點費",
            suggestion="僅限具法源依據且須核發專業證照的訓練；其餘課程請刪除該項。",
        ))
    if total > PROCUREMENT_THRESHOLD:
        f.append(_issue(
            WARN, "總經費超過 15 萬元",
            "陳報單須敘明採購法依據並加會政風室，不可拆分發包。本產生器目前不處理這類案件，請另洽承辦人。",
            rule=RULE_PROCUREMENT,
            where="總經費",
            comparison=f"總經費 {money(total)} 元，門檻 {money(PROCUREMENT_THRESHOLD)} 元",
            suggestion="陳報單須敘明採購法依據並加會政風室，不可拆分發包。本產生器不處理這類案件，請另洽承辦人。",
        ))

    # 9. 品項名稱：避免「贈品」
    gifts = [i["name"] or "（未命名）" for i in ctx.items if "贈品" in (i["name"] or "")]
    if gifts:
        f.append(_issue(
            WARN, "品項名稱使用「贈品」",
            "建議依性質改列「宣導品」；若是有獎徵答再改列「獎品」。項目：" + "、".join(gifts) + "。",
            rule=RULE_GIFT,
            where=_budget_where(gifts),
            comparison="品項名稱含「贈品」：" + "、".join(gifts),
            suggestion="請依性質改列「宣導品」；若是有獎徵答再改列「獎品」。",
        ))

    # 9b. 油資、過路費、停車費不予補助（品項名稱含這些字的項目全數列為自籌）
    fuel_items = [i for i in ctx.items if _no_subsidy_words(i)]
    if fuel_items:
        names = [i["name"] for i in fuel_items]
        bundled = [i["name"] for i in fuel_items if "含" in i["name"]]
        extra = ("「" + "」「".join(bundled) + "」把這些費用併在其他費用裡，整項都被列為自籌；"
                 "請拆成「（不含油資、過路費、停車費）的費用」與獨立的油資、過路費、停車費品項。") if bundled else ""
        f.append(_issue(
            WARN, "有油資、過路費或停車費品項，縣府不予補助",
            "、".join(names) + "：已全數列為自籌款，不分配補助款。" + extra,
            rule=RULE_NO_SUBSIDY,
            where=_budget_where(names),
            comparison="品項名稱含：" + "、".join(sorted({w for i in fuel_items for w in _no_subsidy_words(i)})),
            suggestion="這些費用須由自籌款支應；若已含在遊覽車租金等品項內，請拆成獨立品項，租車費備註註明不含這些費用。",
        ))

    # 10. 備註欄
    no_use =[i["name"] or "（未命名）" for i in ctx.items if not i["use"]]
    if no_use:
        f.append(_issue(
            ERROR, "概算表有項目沒填「用途說明」",
            "、".join(no_use) + "。每個品項的備註都要寫明用途與經費來源（經費來源系統會自動補上）。",
            rule=RULE_REMARK,
            where=_budget_where(no_use) + "用途說明",
            comparison="尚未填寫用途說明：" + "、".join(no_use),
            suggestion="請為每個品項寫明用途；經費來源系統會自動補上。",
        ))
    else:
        f.append(Finding(OK, "每個品項都有用途說明，經費來源已自動寫入備註", ""))

    # 11. 課程表（有填時間或日期但內容空白的列仍保留，列數與畫面一致）
    courses = list(ctx.courses)
    sched = ctx.info["schedule_label"]
    if not courses and not ctx.needs_schedule:
        pass  # 活動類（如表揚）不要求流程表
    elif not courses:
        f.append(_issue(
            ERROR, f"沒有{sched}", f"辦理研習、訓練、環境教育活動時，計畫書內應列出詳細{sched}。",
            rule=RULE_COURSE,
            where=sched,
            comparison="沒有任何課程列",
            suggestion="請列出日期、時間與內容。",
        ))
    else:
        f.append(Finding(OK, f"已列出{sched}", f"共 {len(courses)} 列。"))
        empty = [str(i) for i, course in enumerate(courses, 1) if not str(course.get("content") or "").strip()]
        if empty:
            f.append(_issue(
                WARN, f"{sched}有列未填{'課程' if ctx.plan_type == 'training' else '活動'}內容",
                "第 " + "、".join(empty) + " 列仍會列入 Word 與 Excel，請補上內容，或刪除用不到的列。",
                rule=RULE_COURSE,
                where=f"{sched}第 " + "、".join(empty) + " 列",
                comparison="這些列有日期或時間，但課程內容是空白",
                suggestion="請補上課程內容，或刪除用不到的列。",
            ))
        if ctx.start and ctx.end and ctx.end >= ctx.start:
            outside = []
            outside_iso = []
            for i, course in enumerate(courses, 1):
                course_date = course.get("date")
                if course_date and (course_date < ctx.start or course_date > ctx.end):
                    outside.append(f"第{i}列（{roc_date(course_date)}）")
                    outside_iso.append(f"第{i}列 {course_date.isoformat()}")
            if outside:
                f.append(_issue(
                    ERROR, "課程日期不在活動期間",
                    "、".join(outside) + f"。須介於 {roc_date(ctx.start)} 至 {roc_date(ctx.end)}。",
                    rule=RULE_COURSE,
                    where="課程表",
                    comparison="、".join(outside_iso) + f" 不在 {ctx.start.isoformat()} 至 {ctx.end.isoformat()}",
                    suggestion="請把課程日期改到活動開始日至結束日之間。",
                ))

    # 11. 人數與餐點、耗材數量
    f += _quantity_findings(ctx)
    return f


# ---------------------------------------------------------------- 餐費列（便當、便餐）與用途說明下拉
MEAL_NAMES = ("便當", "便餐")
MEAL_DEFAULT_UNIT = {"便當": "份", "便餐": "桌"}


def meal_use_options(start, end):
    """餐費「用途說明」下拉選單：計畫期間每一天的中餐、晚餐、中餐及晚餐。沒有日期時只給餐別。"""
    opts = []
    if start and end and end >= start and (end - start).days < 14:
        d = start
        while d <= end:
            r = roc_date(d)
            opts += [f"{r}中餐", f"{r}晚餐", f"{r}中餐及晚餐"]
            d += timedelta(days=1)
    return opts or ["中餐", "晚餐", "中餐及晚餐"]


def merge_meal_use(use, note):
    """餐費備註 = 用途說明（日期＋餐別）＋數量說明（超過人數時寫明來源）。"""
    use, note = str(use or "").strip(), str(note or "").strip()
    return f"{use}；{note}" if use and note else (use or note)


def normalize_meal_rows(rows, start=None, end=None):
    """餐費列的項目只能是「便當」「便餐」，用途說明只能是下拉選項。
    舊資料或自由輸入的文字會改成最接近的選項，原文移到「數量說明」，不會遺失。非餐費列原樣保留。"""
    opts = meal_use_options(start, end)
    day = roc_date(start) if start else ""
    out = []
    for r in rows:
        r = dict(r)
        r["數量說明"] = str(r.get("數量說明") or "").strip()
        qty = r.get("數量")
        blank = not str(r.get("項目") or "").strip() and not (isinstance(qty, (int, float)) and qty)
        if str(r.get("類別") or "") != "餐費" or blank:
            out.append(r)
            continue
        orig = str(r.get("項目") or "").strip()
        unit = str(r.get("單位") or "").strip()
        use = str(r.get("用途說明") or "").strip()
        if orig not in MEAL_NAMES:
            r["項目"] = "便餐" if (unit in ("桌", "席") or "便餐" in orig or "桌" in orig) else "便當"
        if not unit:
            r["單位"] = MEAL_DEFAULT_UNIT[r["項目"]]
        if use not in opts:
            n, label = _meals_in(f"{orig} {use}")
            kind = "中餐及晚餐" if n >= 2 else ("晚餐" if "晚" in label else "中餐")
            if use:
                r["數量說明"] = f"{r['數量說明']}；{use}" if r["數量說明"] and use not in r["數量說明"] else (r["數量說明"] or use)
            r["用途說明"] = f"{day}{kind}" if day else kind
        out.append(r)
    return out


# ---------------------------------------------------------------- 人數與餐點、耗材數量
def _meals_in(text):
    """辨識品名或用途說明裡的餐別：午晚餐＝午餐＋晚餐。回傳 (餐數, 說明)。至少算 1 餐。"""
    t = str(text or "")
    meals = []
    if re.search(r"早餐|早點|早飯", t):
        meals.append("早餐")
    if re.search(r"午餐|中餐|午飯|午[、及與和]?晚", t):
        meals.append("午餐")
    if re.search(r"晚餐|晚飯|午[、及與和]?晚", t):
        meals.append("晚餐")
    return max(1, len(meals)), ("＋".join(meals) if meals else "1 餐")


def _has_qty_note(use):
    """用途說明有沒有寫明數量來源：至少要有「○人」這類人數說明。"""
    return bool(re.search(r"\d+\s*[人名位]", str(use or "")))


_MEAL_NAME = re.compile(r"便當|餐盒|午餐|中餐|晚餐|早餐|餐")
_DRINK_NAME = re.compile(r"礦泉水|飲用水|瓶裝水|茶|飲料|果汁|咖啡|運動飲")
_GOODS_NAME = re.compile(r"毛巾|帽|袋|資料夾|筆記|文具|識別證|名牌|貼紙|手冊|背心|雨衣")
_MEAL_UNITS = ("份", "個", "人", "盒", "客", "組")
_TABLE_UNITS = ("桌", "席")          # 桌餐：每桌人數不一（6～10 人），以最少 6 人估，只提醒、明顯離譜才算不符
_PEOPLE_PER_TABLE = 6
_DRINK_UNITS = ("瓶", "罐", "杯")
_GOODS_UNITS = ("個", "條", "件", "本", "支", "份", "組", "頂", "張", "套", "雙")


def _ceil(x):
    return int(-(-x // 1))


def _quantity_findings(ctx):
    """名冊（或參加）人數需與便當、桌餐、飲品、個人耗材數量合理對應。

    餐點：每人每天餐數 × 人數 × 天數為基準。超過基準就提醒；超過基準 10% 以上而且用途說明沒有寫明
    人數來源，就是不符規定。用途說明有寫「○人」這類來源，視為已說明。
    """
    if ctx.plan_type == "equipment":
        return []
    roster_n = len([r for r in ctx.roster if str(r.get("name") or "").strip()])
    people = roster_n or int(ctx.headcount or 0)
    if people <= 0:
        return []
    basis = f"名冊 {roster_n} 人" if roster_n else f"參加人數 {people} 人"
    days = ctx.days
    out, lines = [], []
    for i in ctx.items:
        name, use, unit, qty = i["name"], i["use"], i["unit"], i["qty"]
        text = f"{name} {use}"
        meal = False
        slack = 1.0
        if (i["kind"] == "餐費" or _MEAL_NAME.search(name)) and (unit in _MEAL_UNITS or unit in _TABLE_UNITS):
            meal = True
            per, label = _meals_in(text)
            row_days = 1 if re.search(r"\d+年\d+月\d+日", use) else days     # 下拉選單選了某一天，就只算那一天
            if unit in _TABLE_UNITS:
                exact = _ceil(people * row_days * per / _PEOPLE_PER_TABLE)
                how = f"{basis}、{row_days} 天、每人每天 {label}、每{unit}以 {_PEOPLE_PER_TABLE} 人估"
                slack = 2.0
            else:
                exact = people * row_days * per
                how = f"{basis}、{row_days} 天、每人每天 {label}"
                slack = 1.1
        elif _DRINK_NAME.search(name) and unit in _DRINK_UNITS:
            exact = people * days * 3
            how = f"{basis}、{days} 天、每人每天最多約 3 {unit}"
        elif _GOODS_NAME.search(name) and unit in _GOODS_UNITS:
            exact = _ceil(people * 1.2)
            how = f"{basis}、每人 1 {unit}（含約 20% 備品）"
        else:
            continue
        limit = max(exact, _ceil(exact * slack))
        lines.append(f"「{name}」{int(qty)} {unit}（基準 {exact}）：{how}")
        if qty <= exact:
            continue
        where = _budget_where([name])
        noted = _has_qty_note(use)
        if noted:
            out.append(Finding(OK, f"「{name}」數量超過人數基準，已於用途說明註明來源",
                               f"{int(qty)} {unit}，{how}，基準 {exact}；用途說明：{use}"))
            continue
        if qty <= limit:
            out.append(_issue(
                WARN, f"「{name}」數量比人數基準多",
                f"{int(qty)} {unit}，{how}，基準 {exact}，多 {int(qty - exact)}。",
                rule=RULE_MEAL_QTY, where=where,
                comparison=f"數量 {int(qty)} {unit}，依 {how} 基準 {exact}",
                suggestion="如果是多備或有其他人員（教官、工作人員、來賓），請在「用途說明」寫明數量來源，"
                           "例如：學員 30 人＋工作人員 3 人，午餐。"))
            continue
        out.append(_issue(
            ERROR if meal else WARN, f"「{name}」數量與人數不相符",
            f"{int(qty)} {unit}，{how}，基準 {exact}，上限約 {limit}。",
            rule=RULE_MEAL_QTY, where=where,
            comparison=f"數量 {int(qty)} {unit}，依 {how} 基準 {exact}（上限約 {limit}）",
            suggestion="請調降數量，或在「用途說明」清楚註明數量來源與用途，"
                       "例如：學員 30 人＋工作人員 10 人＋來賓 5 人，午餐及晚餐。"))
    if lines and not any(f.level != OK for f in out):
        out.append(Finding(OK, "餐點與耗材數量與人數相符", "；".join(lines)))
    return out


# ---------------------------------------------------------------- 文字範本
def default_background(ctx):
    if ctx.plan_type == "equipment":
        return (f"{ctx.unit.strip()}因業務及勤務需要，現有相關設備數量或性能不足，為提升整體救災及訓練效能，"
                f"爰辦理本設備購置案。")
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
    if ctx.plan_type == "equipment":
        what = ctx.activity.removeprefix("購置") or "相關設備"
        return f"為充實{ctx.unit.strip()}所需之{what}，提升勤務及救災效能，保障民眾生命財產安全，特訂定本計畫。"
    if ctx.plan_type == "activity":
        return f"為辦理{ctx.activity or '本活動'}，特訂定本計畫。"
    return (f"藉由{_training(ctx)}，使參訓人員熟悉相關裝備器材之使用及操作方法，提升專業技能與實務能力，"
            f"強化整體救災戰力，保障民眾生命財產安全，特訂定本計畫。")


def default_method(ctx):
    return ("採集中訓練方式辦理，由授課教官講解相關技術及裝備操作要領，並由每位學員實際操作各項訓練技能，"
            "教官逐一指導動作及操作技巧。")


def default_rules(ctx):
    return ("一、參訓人員請準時於集合地點報到點名。\n"
            "二、參訓人員一律穿著救助服或整齊服裝到訓。\n"
            "三、訓練所需裝備器具，由本單位及各授課教官預先檢修及協助備妥。")


def has_schedule_attachment(ctx):
    """是否產出「課程（流程、行程）表」附件。訓練類一律有；活動類有填才有。"""
    if ctx.plan_type == "equipment":
        return False
    return ctx.plan_type == "training" or bool(ctx.courses)


def attachment_labels(ctx):
    """回傳 (流程表附件, 概算表附件, 名冊附件)；沒有流程表時為 None，後面的附件順位前移。"""
    n = 1
    sched = None
    if has_schedule_attachment(ctx):
        sched = "附件" + _CN_PLAIN[n - 1]
        n += 1
    budget = "附件" + _CN_PLAIN[n - 1]
    roster = "附件" + _CN_PLAIN[n]
    return sched, budget, roster


def fund_text(ctx):
    budget_label = attachment_labels(ctx)[1]
    clauses = "、".join(source_phrase(src) for src in ctx.sources)
    rest = f"，其餘不足部分由{ctx.unit}自行籌措" if ctx.self_fund > 0.5 or ctx.total <= 0 else ""
    return (f"本案{ctx.info['kind_word']}經費共計新臺幣{to_cn_amount(ctx.total)}元整（如{budget_label}），擬由{clauses}{rest}。")


def _activity_sections(ctx):
    """活動類（表揚／研習／文康）章節。依歷年案件格式；敘獎事項不入計畫書。"""
    pu = _end(ctx.purpose) if ctx.purpose.strip() else default_purpose(ctx)
    org = [
        "一、指導單位：臺東縣政府、臺東縣議會。",
        "二、主辦單位：臺東縣消防局。",
        f"三、承辦單位：{ctx.unit.strip()}。",
    ]
    if ctx.co_organizer.strip():
        org.append(f"四、協辦單位：{ctx.co_organizer.strip()}。")
    out = [
        ("目的", [pu]),
        ("辦理單位", org),
        ("活動日期及地點", [f"一、時間：{ctx.date_text}。", f"二、地點：{ctx.place.strip()}。"]),
        ("參加對象", [f"{ctx.audience.strip()}" + (f"，共計{ctx.headcount}人。" if ctx.headcount else "。")]),
    ]
    if ctx.method.strip():
        out.append(("活動內容", [line.strip() for line in ctx.method.strip().split("\n") if line.strip()]))
    if has_schedule_attachment(ctx):
        out.append(("活動流程", [f"詳如{attachment_labels(ctx)[0]}。"]))
    out.append(("活動經費", [fund_text(ctx)]))
    if ctx.rules.strip():
        out.append(("注意事項", [line.strip() for line in ctx.rules.strip().split("\n") if line.strip()]))
    if ctx.supervisor.strip():
        out.append(("督導考核", [_end(ctx.supervisor)]))
    out.append(("其他", ["本計畫如有未盡事宜得隨時補充修正之。"]))
    return out


def _equipment_sections(ctx):
    """設備類（購置設備）章節。格式比照歷年購置案；金額與備註在附件概算表。"""
    bg = _end(ctx.background) if ctx.background.strip() else default_background(ctx)
    pu = _end(ctx.purpose) if ctx.purpose.strip() else default_purpose(ctx)
    org = [
        "一、指導單位：臺東縣政府、臺東縣議會。",
        "二、主辦單位：臺東縣消防局。",
        f"三、承辦單位：{ctx.unit.strip()}。",
    ]
    if ctx.co_organizer.strip():
        org.append(f"四、協辦單位：{ctx.co_organizer.strip()}。")
    lines = []
    for n, it in enumerate(ctx.items, 1):
        no = _CN_PLAIN[n - 1] if n <= len(_CN_PLAIN) else str(n)
        use = f"：{it['use'].strip().rstrip('。')}" if it.get("use") else ""
        lines.append(f"{no}、{it['name']}{money(it['qty'])}{it['unit']}{use}。")
    lines.append(f"詳如{attachment_labels(ctx)[1]}。")
    out = [
        ("緣由", [bg]),
        ("目的", [pu]),
        ("辦理單位", org),
        ("設置地點", [f"{ctx.place.strip()}。"]),
        ("使用單位", [f"{ctx.audience.strip()}" + (f"，共計{ctx.headcount}人。" if ctx.headcount else "。")]),
        ("購置項目", lines),
    ]
    if ctx.end:
        out.append(("預計完成日期", [f"{roc_date(ctx.end)}前完成購置及驗收。"]))
    out.append(("購置經費", [fund_text(ctx)]))
    out.append(("驗收及管理", ["設備購置完成後依規定辦理驗收，並列入財產管理，由" + ctx.unit.strip() + "指定專人保管維護。"]))
    if ctx.supervisor.strip():
        out.append(("督導考核", [_end(ctx.supervisor)]))
    out.append(("其他", ["本計畫如有未盡事宜得隨時補充修正之。"]))
    return out


def sections(ctx):
    """回傳計畫書章節 [(標題, [段落…])]。"""
    if ctx.plan_type == "equipment":
        return _equipment_sections(ctx)
    if ctx.plan_type == "activity":
        return _activity_sections(ctx)
    bg =_end(ctx.background) if ctx.background.strip() else default_background(ctx)
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


# ---------------------------------------------------------------- 陳報單（送計畫時附上）
# 格式依 115 年成功分隊送計畫的陳報單：案由、陳報內容（一預定辦理、二經費、三檢陳文件、四敘獎）、敬會、簽核欄。
# 活動、訓練、設備的句型相同，只有計畫名稱與檢陳文件不同。
_COMPOUND_SURNAMES = ("歐陽", "司馬", "諸葛", "上官", "夏侯", "皇甫", "慕容", "東方", "南宮", "公孫", "尉遲",
                      "長孫", "司徒", "澹台", "令狐", "鍾離", "宇文")


def _tw(text):
    """顯示用：台東寫成臺東（資料欄位為與現行表單一致用「台」）。"""
    return str(text or "").strip().replace("台東", "臺東")


def org_title(ctx):
    """陳報單抬頭：臺東縣消防局＋大隊＋分隊。大隊帳號只有大隊；沒帶入單位時留空白給人填。"""
    bn, un = _tw(ctx.org_battalion), _tw(ctx.org_unit)
    if bn and un:
        return f"臺東縣消防局{bn}{un}"
    if bn:
        return f"臺東縣消防局{bn}"
    return "臺東縣消防局○○大隊○○分隊"


def _self_word(ctx):
    return "大隊" if (ctx.org_battalion and not ctx.org_unit) else "分隊"


def plan_full_name(ctx):
    return f"{ctx.unit.strip()}{ctx.title2}"


def _source_names(ctx):
    """來源說明，例：議員建議補助款、卑南鄉公所代表建議補助款。"""
    labels = []
    for src in ctx.sources:
        label = source_label_of(src)
        if label not in labels:
            labels.append(label)
    return "及".join(labels)


def _equipment_reason(ctx):
    """設備類主旨要簡述需求原因或目的。優先用緣由欄，沒填就用範本。"""
    reason = ctx.background.strip().rstrip("。")
    if reason:
        return reason.removeprefix("為")
    return f"充實{ctx.unit.strip()}救災及訓練所需設備，提升勤務效能"


def submission_subject(ctx):
    """案由。"""
    return f"有關本{_self_word(ctx)}辦理「{plan_full_name(ctx)}」乙案，請鑒核。"


def _source_name(src):
    return _township_name(src) if src["kind"] == "rep" else format_councilors(src["names"])


def _councilor_call(names):
    """陳報單用的議員稱呼：姓＋議員＋名，例：陳志峰 → 陳議員志峰；多位用「、」。"""
    raw = str(names or "").strip()
    if not raw:
        return "ＯＯ議員"
    out = []
    for part in re.split(r"[、,，;；/]+", raw):
        part = re.sub(r"\s*議員\s*$", "", part).strip()
        if not part:
            continue
        if re.fullmatch(r"[一-鿿]{2,4}", part):
            n = 2 if (len(part) >= 3 and part[:2] in _COMPOUND_SURNAMES) else 1
            out.append(f"{part[:n]}議員{part[n:]}")
        else:
            out.append(part + "議員")
    return "、".join(out) or "ＯＯ議員"


def _fund_source_clause(src):
    if src["kind"] == "rep":
        town = _township_name(src)
        return f"{town}{format_people(src['names'], '代表')}建議{town}補助經費項下支應"
    return f"本縣縣議會{_councilor_call(src['names'])}建議本縣縣府補助經費項下支應"


def _fund_sentence(ctx):
    """第二點：所需經費（國字大寫）與經費來源。"""
    total = f"新臺幣{to_cn_amount(ctx.total)}元整"
    srcs = ctx.sources
    self_fund = max(ctx.self_fund, 0)
    if len(srcs) == 1 and self_fund < 0.5:
        return f"二、本案所需經費{total}，由{_fund_source_clause(srcs[0])}，建請鈞長同意辦理申請補助款事宜。"
    parts = "、".join(f"新臺幣{to_cn_amount(s['amount'])}元整由{_fund_source_clause(s)}" for s in srcs)
    rest = f"，其餘新臺幣{to_cn_amount(self_fund)}元整由{ctx.unit.strip()}自籌款支應" if self_fund >= 0.5 else ""
    return f"二、本案所需經費{total}，其中{parts}{rest}，建請鈞長同意辦理申請補助款事宜。"


def submission_attachments(ctx):
    """第三點檢陳資料（含份數）。計畫書本身已含概算表，不另列。設備類另附審核表與估價單。"""
    kind = "設備" if ctx.plan_type == "equipment" else "活動"
    if ctx.plan_type == "training":
        out = [f"{ctx.title2}（含課程表及經費概算表）1份"]
    elif ctx.plan_type == "equipment":
        out = [f"{ctx.title2}1份"]
    else:
        out = [f"{ctx.title2}（含{'流程表及' if ctx.courses else ''}經費概算表）1份"]
    if ctx.plan_type != "equipment" and (ctx.plan_type == "training" or ctx.roster):
        out.append("人員名冊1份")
    if any(s["kind"] == "councilor" for s in ctx.sources):
        out.append(f"臺東縣議員建議補助{kind}類案件建議表1份")
    towns = []
    for s in ctx.sources:
        if s["kind"] == "rep" and _township_name(s) not in towns:
            towns.append(_township_name(s))
    for town in towns:
        out.append(f"{town.removesuffix('公所')}代表建議補助{kind}類案件建議表1份")
    if ctx.plan_type == "equipment":
        out += ["審核表1份", "估價單2份"]
    if ctx.plan_type == "training":
        out.append("訓練安全計畫與檢核表1份")
    return out


def issuing_note(ctx):
    """發文單位提醒：僅公所補助由大隊發文；含縣府補助由局本部權責科室發文。"""
    if all(s["kind"] == "rep" for s in ctx.sources):
        return "本案只有公所補助，依規定由大隊發文。"
    return "本案含縣府補助（議員建議），依規定由本局權責科室發文。"


# ---- 獎懲：依「消防專業人員平時考核獎懲標準」
AWARD_BASES = {"amount": "依爭取補助款金額", "days": "依活動辦理天數", "custom": "自行輸入", "none": "不敘獎"}
_AWARD_PREFIX = "依本縣消防局消防專業人員平時考核獎懲標準規定，"


def award_by_amount(subsidy):
    """依爭取建議補助款總額度敘獎。未達兩萬元沒有獎勵額度，回傳空字串。"""
    s = float(subsidy or 0)
    if s >= 300000:
        label, who = "達三十萬元以上", "單位主管及承辦人記功1次；協辦人員(至多2名)嘉獎2次"
    elif s >= 100000:
        label, who = "達十萬元至三十萬元以下", "單位主管及承辦人嘉獎2次；協辦人員(至多2名)嘉獎2次"
    elif s >= 50000:
        label, who = "達五萬元至十萬元以下", "單位主管及承辦人嘉獎1次；協辦人員(至多2名)嘉獎1次"
    elif s >= 20000:
        label, who = "達兩萬元以上，未達五萬元", "承辦人嘉獎1次；協辦人員(至多2名)嘉獎1次"
    else:
        return ""
    return f"{_AWARD_PREFIX}爭取建議補助款總額度{label}者{who}。"


def award_by_days(start, end):
    """依活動辦理時程及支援勤務天數敘獎。沒有日期回傳空字串。"""
    if not start or not end or end < start:
        return ""
    days = (end - start).days + 1
    if days >= 3:
        label, who = "達三日以上", "承辦人嘉獎2次；單位主管嘉獎2次；協辦人員嘉獎1次"
    elif days == 2:
        label, who = "在二日內", "承辦人嘉獎2次；單位主管嘉獎1次；協辦人員嘉獎1次"
    else:
        label, who = "在一日內", "承辦人嘉獎2次；單位主管嘉獎1次；協辦人員嘉獎1次"
    return f"{_AWARD_PREFIX}活動辦理時程及支援勤務{label}者{who}。"


def award_lines(ctx):
    """自行輸入的敘獎額度明細。沒有填就回傳空清單。"""
    out = []
    for n, a in enumerate(ctx.awards[: len(_CN_PLAIN)]):
        out.append(f"（{_CN_PLAIN[n]}）{a['role']}（{a['count']}名）{a['kind']}{a['times']}次。")
    return out


def award_text(ctx):
    """第四點「獎懲」內容（不含「四、獎懲：」）。空字串表示不加第四點。"""
    basis = ctx.award_basis or ("custom" if ctx.awards else "none")
    if basis == "amount":
        return award_by_amount(ctx.subsidy)
    if basis == "days":
        return award_by_days(ctx.start, ctx.end) if ctx.plan_type != "equipment" else ""
    if basis == "custom":
        lines = award_lines(ctx)
        if lines:
            return "辦理本案出（不）力人員依規定獎（懲）勵，敘獎額度如下：\n" + "\n".join("　" + x for x in lines)
    return ""


def default_meet(ctx):
    """敬會單位的預設值（可在畫面修改）。有敘獎時加會人事室。"""
    units = []
    if ctx.plan_type == "equipment":
        units.append("災害搶救科")
        if award_text(ctx):
            units.append("人事室")
        return "、".join(units)
    if ctx.plan_type == "training":
        units += ["災害搶救科", "綜合企劃及安全衛生科"]
    units.append("民力運用及訓練科")
    if award_text(ctx):
        units.append("人事室")
    units.append("會計室")
    return "、".join(units)


def meet_text(ctx):
    return ctx.meet.strip() or default_meet(ctx)


def submission_body(ctx):
    """陳報內容（分點，每個元素一點；附件與獎懲內含換行）。"""
    full = plan_full_name(ctx)
    if ctx.plan_type == "equipment":
        if ctx.background.strip():
            first = f"一、{_end(ctx.background)}特訂定本計畫以充實{ctx.unit.strip()}設備。"
        else:
            first = f"一、為{_equipment_reason(ctx)}，擬辦理「{full}」。"
    else:
        first = f"一、本案預訂於{ctx.date_text}於{ctx.place.strip()}辦理「{full}」。"
    third = "三、檢陳相關資料附件如下：\n" + "\n".join(
        (f"　（{_CN_PLAIN[n]}）{x}" if n < len(_CN_PLAIN) else f"　（{n + 1}）{x}") + "。"
        for n, x in enumerate(submission_attachments(ctx)))
    out = [first, _fund_sentence(ctx), third]
    award = award_text(ctx)
    if award:
        out.append("四、獎懲：" + award)
    return out


def submission_markdown(ctx):
    lines = ([f"案件編號：{ctx.case_no}", ""] if ctx.case_no else [])
    lines += [f"**{org_title(ctx)} 陳報單**　　{ctx.year}年○月○日　第○○○號", "",
             f"**案由**：{submission_subject(ctx)}", "", "**陳報內容**：", ""]
    for p in submission_body(ctx):
        lines += [line + "  " for line in p.split("\n")]
    lines += ["", f"敬會　{meet_text(ctx)}", "", "敬陳　局長", "", "承辦人　／　分（小）隊長　／　大隊長"]
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


def _case_no_header(doc, ctx):
    """每一頁右上角印案件編號（登錄後才有）。"""
    if not ctx.case_no:
        return
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    for section in doc.sections:
        p = section.header.paragraphs[0]
        p.text = ""
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _set_font(p.add_run(f"案件編號：{ctx.case_no}"), 11, True)


def build_docx(ctx):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm

    doc = Document()
    _case_no_header(doc, ctx)
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin = sec.bottom_margin = Cm(2.0)

    _para(doc, ctx.title1, 18, True, WD_ALIGN_PARAGRAPH.CENTER, space_after=0)
    _para(doc, f"「{ctx.title2}」", 18, True, WD_ALIGN_PARAGRAPH.CENTER, space_after=12)

    for i, (h, paras) in enumerate(sections(ctx)):
        _para(doc, f"{_CN_SECTION[i]}、{h}：", 14, True, space_after=2)
        for p in paras:
            _para(doc, p, 14, indent=1.0, space_after=4)

    sched_label, budget_label, roster_label = attachment_labels(ctx)
    course_label = ctx.name_for_title
    if sched_label:
        doc.add_page_break()
        _para(doc, sched_label, 12)
        if ctx.plan_type == "activity":
            _para(doc, f"{ctx.year}年{ctx.unit.strip()}{ctx.activity}流程表", 16, True, WD_ALIGN_PARAGRAPH.CENTER)
            header, widths = ["日期", "時間", "活動內容", "負責人員／講師"], [3.4, 3.2, 6.4, 3.6]
            note = ("備註：一、活動地點：" + ctx.place.strip() + "。二、各項活動流程得視現場環境、天候及實際辦理情形適時調整。")
        else:
            _para(doc, f"{ctx.year}年{ctx.unit.strip()}{course_label}訓練課程表", 16, True, WD_ALIGN_PARAGRAPH.CENTER)
            header, widths = ["日期", "時間", "課程內容", "教官／講師"], [3.4, 3.2, 6.4, 3.6]
            note = ("備註：一、訓練地點：" + ctx.place.strip() + "。二、各項訓練課程得視現場環境、天候及實際訓練情形適時調整。")
        _table(doc, header,
               [[roc_date(c["date"]) if c.get("date") else "", c.get("time", ""), c.get("content", ""), c.get("teacher", "")]
                for c in ctx.courses],
               widths)
        _para(doc, note, 12)

    doc.add_page_break()
    _para(doc, budget_label, 12)
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
        _para(doc, roster_label, 12)
        roster_word = "參加人員名冊" if ctx.plan_type == "activity" else "參訓名冊"
        _para(doc, f"{ctx.year}年{ctx.unit.strip()}{course_label}{roster_word}", 16, True, WD_ALIGN_PARAGRAPH.CENTER)
        _table(doc, ["編號", "單位", "職稱", "姓名"],
               [[n + 1, r.get("unit", ""), r.get("title", ""), r.get("name", "")] for n, r in enumerate(roster)],
               [1.5, 5.0, 4.0, 4.0])

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_submission_docx(ctx):
    """陳報單 Word：抬頭、案由、陳報內容、敬會、敬陳局長、承辦人／分（小）隊長／大隊長，格式比照歷年陳報單。"""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm

    doc = Document()
    _case_no_header(doc, ctx)
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin = sec.bottom_margin = Cm(2.0)

    _para(doc, f"{org_title(ctx)} 陳報單", 18, True, WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    _para(doc, f"{ctx.year}年○月○日　第○○○號", 12, False, WD_ALIGN_PARAGRAPH.RIGHT, space_after=4)

    t = doc.add_table(rows=4, cols=2)
    t.style = "Table Grid"
    labels = ["案　由", "陳報內容", "敬　會", "敬　陳"]
    for row, label in zip(t.rows, labels):
        row.cells[0].text = ""
        _set_font(row.cells[0].paragraphs[0].add_run(label), 14, True)
        row.cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        row.cells[0].width, row.cells[1].width = Cm(2.6), Cm(14.0)

    def fill(cell, lines, size=14):
        cell.text = ""
        first = True
        for line in lines:
            p = cell.paragraphs[0] if first else cell.add_paragraph()
            first = False
            _set_font(p.add_run(line), size)

    fill(t.rows[0].cells[1], [submission_subject(ctx)])
    body_lines = [line for p in submission_body(ctx) for line in p.split("\n")]
    fill(t.rows[1].cells[1], body_lines)
    fill(t.rows[2].cells[1], [meet_text(ctx)])
    fill(t.rows[3].cells[1], ["局長"])

    _para(doc, "", 6, space_after=2)
    s = doc.add_table(rows=1, cols=3)
    s.style = "Table Grid"
    for cell, label in zip(s.rows[0].cells, ["承辦人", "分（小）隊長" if _self_word(ctx) == "分隊" else "副大隊長", "大隊長"]):
        cell.text = ""
        _set_font(cell.paragraphs[0].add_run(label + "\n\n\n"), 13)
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
    if ctx.case_no:
        ws.oddHeader.right.text = f"案件編號：{ctx.case_no}"
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

    if has_schedule_attachment(ctx):
        activity = ctx.plan_type == "activity"
        ws2 = wb.create_sheet("活動流程表" if activity else "課程表")
        head2 = ["日期", "時間", "活動內容", "負責人員／講師"] if activity else ["日期", "時間", "課程內容", "教官／講師"]
        for c, h in enumerate(head2, 1):
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


def context_from_inputs(data, plan_type="training"):
    """把 example_inputs／case_inputs 的資料轉成 PlanContext。"""
    srcs = normalize_sources(data.get("sources"), data["councilors"], data["subsidy"])
    subsidy = sum(src["amount"] for src in srcs)
    return PlanContext(
        plan_type=plan_type,
        unit=data["unit"],
        year=data["year"],
        name=data["name"],
        start=data["start"],
        end=data["end"],
        place=data["place"],
        audience=data["audience"],
        headcount=data["headcount"],
        method=data.get("method", ""),
        instructors=data["instructors"],
        co_organizer=data["co_organizer"],
        supervisor=data["supervisor"],
        councilors=data["councilors"],
        subsidy=subsidy,
        sources=srcs if data.get("sources") else [],
        awards=data.get("awards", []),
        meet=data.get("meet", ""),
        items=normalize_items(data["items"], subsidy=subsidy, sources=srcs),
        courses=data["courses"],
        roster=[],
        background=data.get("background", ""),
        purpose=data.get("purpose", ""),
        rules=data.get("rules", ""),
    )


def item_examples(plan_type):
    """歷史案例裡出現過的概算項目（依品名去重），供畫面一鍵加入整列範例。設備類只給設備購置項目。"""
    plan_cases = _load_plan_cases()
    today = date.today()
    seen, out = set(), []
    for key in plan_cases.CASE_KEYS:
        data = plan_cases.build_case(key, today)
        for it in data["items"]:
            is_equip = it["kind"] == "設備購置"
            if (plan_type == "equipment") != is_equip or it["name"] in seen:
                continue
            seen.add(it["name"])
            out.append(dict(it))
    return out


def example_context(today=None):
    return context_from_inputs(example_inputs(today))


def _load_plan_cases():
    """載入歷史案例模組。長時間執行的程序可能留著舊版，檔案有更新就重新載入。"""
    import importlib
    import os
    import plan_cases

    stamp = os.path.getmtime(plan_cases.__file__)
    if getattr(plan_cases, "_loaded_stamp", None) != stamp:
        plan_cases = importlib.reload(plan_cases)
        plan_cases._loaded_stamp = stamp
    return plan_cases


def case_list(plan_type):
    """某計畫類型可載入的歷史案例 [(key, label, summary)]。目前只有活動類有案例。"""
    plan_cases = _load_plan_cases()
    today = date.today()
    out = []
    for key in plan_cases.CASE_KEYS:
        data = plan_cases.build_case(key, today)
        if data["plan_type"] == plan_type:
            out.append((key, data["label"], data["summary"]))
    return out


def case_inputs(key, today=None):
    """歷史案例的完整輸入資料（去識別化）。開始日落在 1 個月又 1 週之後，年度為今年。"""
    plan_cases = _load_plan_cases()
    today = today or date.today()
    data = plan_cases.build_case(key, today + timedelta(days=45))
    data["year"] = roc_year(today)
    return data


def case_context(key, today=None):
    data = case_inputs(key, today)
    return context_from_inputs(data, data["plan_type"])
