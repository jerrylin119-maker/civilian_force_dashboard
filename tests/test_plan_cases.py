# -*- coding: utf-8 -*-
"""活動類計畫類型、歷史案例範例與「油資、過路費、停車費不予補助」檢查的測試。"""

import io
import json
import re
import unittest
from datetime import date

import plan_cases
import plan_generator as pg


TODAY = date(2026, 10, 27)
CASE_KEYS = list(plan_cases.CASE_KEYS)


def _titles(findings, level=None):
    return [f.title for f in findings if level is None or f.level == level]


def _activity(**overrides):
    start = pg.earliest_activity_date(TODAY)
    subsidy = overrides.pop("subsidy", 20000)
    raw_items = overrides.pop("items", [
        {"name": "場地佈置", "kind": "一般", "qty": 1, "unit": "式", "price": 20000, "use": "供典禮使用"},
        {"name": "雜支", "kind": "雜支", "qty": 1, "unit": "式", "price": 1000, "use": "文具"},
        {"name": "便餐", "kind": "餐費", "qty": 2, "unit": "桌", "price": 5000, "use": "供用餐"},
    ])
    base = dict(
        plan_type="activity", unit="成功義消大隊", year=115, name="績優義消人員表揚",
        start=start, end=start, place="成功消防大隊車庫", audience="義消人員", headcount=100,
        method="", instructors="", co_organizer="", supervisor="", councilors="王議員",
        subsidy=subsidy, items=pg.normalize_items(raw_items, subsidy=subsidy), courses=[], roster=[],
    )
    base.update(overrides)
    return pg.PlanContext(**base)


class ActivityTypeTests(unittest.TestCase):
    def test_both_plan_types_registered_with_labels(self):
        self.assertIn("activity", pg.PLAN_TYPES)
        self.assertEqual(pg.PLAN_TYPES["training"]["audience_label"], "參訓對象")
        self.assertEqual(pg.PLAN_TYPES["activity"]["audience_label"], "參加對象")
        self.assertEqual(pg.MODULE_REVISION, 4)

    def test_activity_sections_use_activity_wording_and_skip_award(self):
        ctx = _activity(purpose="表彰績優人員", method="（一）績優表揚。\n（二）頒獎。")
        heads = [h for h, _ in pg.sections(ctx)]
        self.assertEqual(heads, ["目的", "辦理單位", "活動日期及地點", "參加對象", "活動內容", "活動經費", "其他"])
        self.assertNotIn("訓練課程", heads)
        self.assertNotIn("緣由", heads)
        text = pg.markdown_preview(ctx)
        self.assertNotIn("嘉獎", text)
        self.assertIn("臺東縣消防局辦理成功義消大隊", text)
        self.assertIn("115年度績優義消人員表揚活動計畫", text)

    def test_fund_text_points_to_first_attachment_when_no_schedule(self):
        ctx = _activity()
        self.assertIn("本案活動經費共計新臺幣", pg.fund_text(ctx))
        self.assertIn("（如附件一）", pg.fund_text(ctx))
        self.assertEqual(pg.attachment_labels(ctx), (None, "附件一", "附件二"))

    def test_training_attachments_unchanged(self):
        start = pg.earliest_activity_date(TODAY)
        ctx = pg.PlanContext(
            plan_type="training", unit="達仁義消分隊", year=115, name="繩索救助訓練", start=start, end=start,
            place="x", audience="y", headcount=1, method="", instructors="", co_organizer="", supervisor="",
            councilors="", subsidy=0, items=[], courses=[], roster=[])
        self.assertEqual(pg.attachment_labels(ctx), ("附件一", "附件二", "附件三"))
        self.assertIn("（如附件二）", pg.fund_text(ctx))

    def test_schedule_not_required_for_honor_but_required_for_study(self):
        honor = _activity()
        self.assertEqual(_titles(pg.check_plan(honor, today=TODAY), pg.ERROR), [])
        study = _activity(name="縣外研習")
        errors = _titles(pg.check_plan(study, today=TODAY), pg.ERROR)
        self.assertIn("沒有活動流程／行程表", errors)
        env = _activity(name="員工環境教育暨文康")
        self.assertIn("沒有活動流程／行程表", _titles(pg.check_plan(env, today=TODAY), pg.ERROR))

    def test_required_field_label_follows_plan_type(self):
        ctx = _activity(audience="")
        hit = [f for f in pg.check_plan(ctx, today=TODAY) if f.title == "尚有必填欄位未填"]
        self.assertIn("參加對象", hit[0].detail)
        self.assertNotIn("參訓對象", hit[0].detail)

    def test_docx_and_xlsx_without_schedule_have_no_course_sheet(self):
        from docx import Document
        from openpyxl import load_workbook
        ctx = _activity(method="（一）績優表揚。")
        doc = Document(io.BytesIO(pg.build_docx(ctx)))
        text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("附件一", text)
        self.assertNotIn("附件二", text)
        self.assertNotIn("課程表", text)
        wb = load_workbook(io.BytesIO(pg.build_xlsx(ctx)))
        self.assertEqual(wb.sheetnames, ["經費概算表"])

    def test_docx_and_xlsx_with_schedule_use_activity_names(self):
        from docx import Document
        from openpyxl import load_workbook
        start = pg.earliest_activity_date(TODAY)
        ctx = _activity(name="縣外研習", courses=[{"date": start, "time": "09:00", "content": "研習交流", "teacher": ""}],
                        roster=[{"unit": "成功義消大隊", "title": "隊員", "name": "甲"}])
        doc = Document(io.BytesIO(pg.build_docx(ctx)))
        text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("縣外研習活動流程表", text)
        self.assertIn("附件三", text)
        self.assertIn("參加人員名冊", text)
        self.assertNotIn("訓練課程表", text)
        wb = load_workbook(io.BytesIO(pg.build_xlsx(ctx)))
        self.assertEqual(wb.sheetnames, ["經費概算表", "活動流程表"])


class NoSubsidyWordsTests(unittest.TestCase):
    def test_fuel_toll_parking_items_get_no_subsidy_and_warn(self):
        items = pg.normalize_items([
            {"name": "遊覽車租金", "kind": "一般", "qty": 2, "unit": "日", "price": 15000, "use": "往返交通"},
            {"name": "油資", "kind": "一般", "qty": 1, "unit": "式", "price": 5000, "use": "遊覽車用油"},
            {"name": "過路費", "kind": "一般", "qty": 1, "unit": "式", "price": 1000, "use": "國道通行"},
            {"name": "停車費", "kind": "一般", "qty": 1, "unit": "式", "price": 500, "use": "景點停車"},
        ], subsidy=20000)
        by = {i["name"]: i for i in items}
        self.assertEqual(by["遊覽車租金"]["subsidy"], 20000)
        for name in ("油資", "過路費", "停車費"):
            self.assertEqual(by[name]["subsidy"], 0)
            self.assertEqual(by[name]["self"], by[name]["total"])
            self.assertNotIn("議員建議補助款", by[name]["remark"])
        ctx = _activity(items=[{"name": i["name"], "kind": i["kind"], "qty": i["qty"], "unit": i["unit"],
                                "price": i["price"], "use": i["use"]} for i in items], subsidy=20000)
        warn = [f for f in pg.check_plan(ctx, today=TODAY) if "油資、過路費或停車費" in f.title]
        self.assertEqual(len(warn), 1)
        self.assertEqual(warn[0].level, pg.WARN)
        self.assertIn("油資", warn[0].detail)
        self.assertIn("過路費", warn[0].detail)
        self.assertIn("停車費", warn[0].detail)

    def test_bundled_name_is_flagged_with_split_advice(self):
        ctx = _activity(items=[
            {"name": "遊覽車租金（2日，含油資、過路費、駕駛食宿）", "kind": "一般", "qty": 2, "unit": "日",
             "price": 15000, "use": "往返交通"},
            {"name": "住宿", "kind": "一般", "qty": 20, "unit": "間", "price": 3000, "use": "住宿"},
        ], subsidy=60000)
        warn = [f for f in pg.check_plan(ctx, today=TODAY) if "油資、過路費或停車費" in f.title]
        self.assertEqual(len(warn), 1)
        self.assertIn("拆成", warn[0].detail)
        self.assertEqual(ctx.items[0]["subsidy"], 0)
        self.assertEqual(ctx.items[1]["subsidy"], 60000)

    def test_no_warning_without_those_words(self):
        ctx = _activity()
        self.assertEqual([f for f in pg.check_plan(ctx, today=TODAY) if "油資" in f.title], [])


class HistoricalCaseTests(unittest.TestCase):
    def test_three_activity_cases_listed(self):
        listed = pg.case_list("activity")
        self.assertEqual([k for k, _l, _s in listed], CASE_KEYS)
        self.assertEqual(pg.case_list("training"), [])

    def test_original_totals_are_preserved(self):
        expected = {"honor": (346000, 240000), "study_tour": (144000, 100000), "culture_edu": (78200, 40000)}
        for key, (total, subsidy) in expected.items():
            ctx = pg.case_context(key, TODAY)
            self.assertEqual(ctx.total, total, key)
            self.assertEqual(ctx.subsidy, subsidy, key)
            self.assertEqual(sum(i["subsidy"] for i in ctx.items), subsidy, key)

    def test_each_case_passes_without_errors_and_exports(self):
        for key in CASE_KEYS:
            ctx = pg.case_context(key, TODAY)
            errors = _titles(pg.check_plan(ctx, today=TODAY), pg.ERROR)
            self.assertEqual(errors, [], key)
            self.assertGreater(len(pg.build_docx(ctx)), 1000)
            self.assertGreater(len(pg.build_xlsx(ctx)), 1000)
            self.assertEqual(ctx.plan_type, "activity")

    def test_honor_case_over_150k_gets_procurement_warning_only(self):
        ctx = pg.case_context("honor", TODAY)
        findings = pg.check_plan(ctx, today=TODAY)
        self.assertIn("總經費超過 15 萬元", _titles(findings, pg.WARN))
        self.assertEqual(ctx.courses, [])

    def test_study_and_culture_cases_have_schedules(self):
        self.assertGreaterEqual(len(pg.case_context("study_tour", TODAY).courses), 6)
        self.assertGreaterEqual(len(pg.case_context("culture_edu", TODAY).courses), 6)

    def test_study_case_has_no_bundled_fuel_toll(self):
        ctx = pg.case_context("study_tour", TODAY)
        self.assertEqual([i for i in ctx.items if pg._no_subsidy_words(i)], [])
        self.assertEqual([f for f in pg.check_plan(ctx, today=TODAY) if "油資" in f.title], [])

    def test_dates_are_relative_to_today(self):
        data = pg.case_inputs("study_tour", TODAY)
        self.assertGreaterEqual(data["start"], pg.earliest_activity_date(TODAY))
        self.assertEqual((data["end"] - data["start"]).days, 1)
        self.assertEqual(data["year"], TODAY.year - 1911)

    def test_cases_contain_no_personal_data(self):
        blob = ""
        for key in CASE_KEYS:
            data = pg.case_inputs(key, TODAY)
            data = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in data.items()
                    if k not in ("items", "courses")}
            blob += json.dumps(data, ensure_ascii=False)
            blob += json.dumps([[i["name"], i["use"]] for i in pg.case_inputs(key, TODAY)["items"]], ensure_ascii=False)
            blob += json.dumps([[c["content"], c["teacher"]] for c in pg.case_inputs(key, TODAY)["courses"]],
                               ensure_ascii=False)
            self.assertEqual(pg.case_context(key, TODAY).roster, [])
        self.assertIsNone(re.search(r"[A-Z][12]\d{8}", blob), "不得含身分證字號")
        self.assertIsNone(re.search(r"0\d{1,2}-?\d{6,8}", blob), "不得含電話")
        self.assertIsNone(re.search(r"\d{6,}", blob.replace("000", "")), "不得含案號、發文字號")
        for word in ("廖昱翔", "林威宇", "林顯峯", "盧東發", "管建興", "吳秀華", "高美珠", "楊招信"):
            self.assertNotIn(word, blob)
        self.assertNotIn("嘉獎", blob)

    def test_fresh_dict_each_call(self):
        a = pg.case_inputs("honor", TODAY)
        a["items"].append({"name": "x"})
        self.assertEqual(len(pg.case_inputs("honor", TODAY)["items"]), 8)


if __name__ == "__main__":
    unittest.main()
