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
        self.assertEqual(pg.MODULE_REVISION, 7)

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
    def test_cases_listed_by_plan_type(self):
        activity = [k for k, _l, _s in pg.case_list("activity")]
        training = [k for k, _l, _s in pg.case_list("training")]
        self.assertEqual(activity, ["honor", "study_tour", "culture_edu", "award_dinner", "env_study"])
        self.assertEqual(training, [
            "vehicle_fire", "rehab_bls", "mountain_rescue", "car_rescue",
            "rope_two_days", "water_rescue", "mountain_three_days",
        ])
        equipment = [k for k, _l, _s in pg.case_list("equipment")]
        self.assertEqual(equipment, ["equip_rescue"])
        self.assertEqual(activity + training + equipment, CASE_KEYS)

    def test_original_totals_are_preserved(self):
        expected = {
            "honor": (346000, 240000), "study_tour": (144000, 100000), "culture_edu": (78200, 40000),
            "vehicle_fire": (24500, 20000), "rehab_bls": (78600, 50000), "mountain_rescue": (20160, 20000),
            "car_rescue": (21300, 20000), "rope_two_days": (23900, 20000), "water_rescue": (30500, 20000),
            "mountain_three_days": (86750, 60000),
            "award_dinner": (48000, 20000), "env_study": (20000, 20000),
            "equip_rescue": (97423, 97423),
        }
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
            self.assertEqual(ctx.plan_type, pg.case_inputs(key, TODAY)["plan_type"])

    def test_training_cases_have_schedule_and_no_award(self):
        for key in ("vehicle_fire", "rehab_bls", "mountain_rescue", "car_rescue",
                    "rope_two_days", "water_rescue", "mountain_three_days"):
            ctx = pg.case_context(key, TODAY)
            self.assertEqual(ctx.plan_type, "training", key)
            self.assertGreaterEqual(len(ctx.courses), 4, key)
            self.assertNotIn("沒有課程表", _titles(pg.check_plan(ctx, today=TODAY)), key)


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

    def test_submission_form_same_wording_for_activity_and_training(self):
        """陳報單句型相同，只有計畫名稱與檢陳文件不同；預訂日期地點寫在第一點；不得出現敘獎額度。"""
        for key in CASE_KEYS:
            ctx = pg.case_context(key, TODAY)
            subject = pg.submission_subject(ctx)
            body = pg.submission_body(ctx)
            joined = "".join(body)
            self.assertIn(pg.plan_full_name(ctx), subject)
            self.assertIn("申請議員建議補助款案", subject)
            if ctx.plan_type != "equipment":
                self.assertIn(ctx.date_text, body[0])
                self.assertIn(ctx.place.strip(), body[0])
            self.assertIn("建請鈞長同意辦理申請補助款事宜", body[1])
            self.assertIn(f"新臺幣{pg.money(ctx.total)}元", body[1])
            self.assertIn("經費概算表", body[2])
            self.assertNotIn("嘉獎", joined)
            self.assertNotIn("人事室", pg.meet_text(ctx))
            self.assertGreater(len(pg.build_submission_docx(ctx)), 2000)

    def test_submission_form_without_self_fund_omits_rest_clause(self):
        ctx = pg.case_context("env_study", TODAY)
        self.assertLess(ctx.self_fund, 0.5)
        self.assertNotIn("不足部分", "".join(pg.submission_body(ctx)))
        self.assertNotIn("不足部分", pg.fund_text(ctx))
        ctx = pg.case_context("honor", TODAY)
        self.assertIn("不足部分", "".join(pg.submission_body(ctx)))

    def test_training_submission_lists_safety_checklist_and_default_meet(self):
        ctx = pg.case_context("rehab_bls", TODAY)
        self.assertIn("訓練安全計畫與檢核表", pg.submission_body(ctx)[2])
        self.assertEqual(pg.meet_text(ctx), "災害搶救科、綜合企劃及安全衛生科、民力運用及訓練科、會計室")


class MultiSourceAndEquipmentTests(unittest.TestCase):
    def _mixed(self):
        data = pg.case_inputs("rehab_bls", TODAY)
        data["sources"] = [
            {"kind": "councilor", "names": "林", "amount": 30000},
            {"kind": "rep", "names": "陳", "township": "卑南鄉公所", "amount": 20000},
        ]
        data["awards"] = [{"role": "大隊督辦人員", "count": 2, "kind": "嘉獎", "times": 1},
                          {"role": "分隊承辦人員", "count": 1, "kind": "嘉獎", "times": 2}]
        return pg.context_from_inputs(data, "training")

    def test_sources_sum_to_subsidy_and_each_item_remark_names_every_source(self):
        ctx = self._mixed()
        self.assertEqual(ctx.subsidy, 50000)
        self.assertEqual(sum(i["subsidy"] for i in ctx.items), 50000)
        for item in ctx.items:
            self.assertAlmostEqual(sum(a for _l, a in item["by_source"]), item["subsidy"], places=6)
            self.assertIn("議員建議補助款支應", item["remark"])
            self.assertIn("卑南鄉公所代表建議補助款支應", item["remark"])
        by_label = {}
        for item in ctx.items:
            for label, amount in item["by_source"]:
                by_label[label] = by_label.get(label, 0) + amount
        self.assertEqual(by_label, {"議員建議補助款": 30000, "卑南鄉公所代表建議補助款": 20000})

    def test_mixed_source_texts_and_attachments(self):
        ctx = self._mixed()
        fund = pg.fund_text(ctx)
        self.assertIn("林議員建議縣府補助新臺幣參萬元整", fund)
        self.assertIn("卑南鄉公所陳代表建議卑南鄉公所補助新臺幣貳萬元整", fund)
        body = pg.submission_body(ctx)
        self.assertIn("林議員及卑南鄉公所補助本局辦理", body[1])
        self.assertIn("林議員新臺幣30,000元、卑南鄉公所新臺幣20,000元", body[1])
        self.assertIn("「臺東縣議員建議補助活動類案件建議表」", body[2])
        self.assertIn("「卑南鄉代表建議補助活動類案件建議表」", body[2])
        self.assertIn("議員建議補助款及卑南鄉公所代表建議補助款", pg.submission_subject(ctx))

    def test_single_source_keeps_old_wording(self):
        ctx = pg.case_context("honor", TODAY)
        self.assertEqual(len(ctx.sources), 1)
        self.assertIn("王議員、李議員建議縣府補助新臺幣貳拾肆萬元整", pg.fund_text(ctx))
        for item in ctx.items:
            self.assertNotIn("代表", item["remark"])

    def test_rep_only_source_goes_through_battalion(self):
        data = pg.case_inputs("honor", TODAY)
        data["sources"] = [{"kind": "rep", "names": "", "township": "", "amount": 240000}]
        ctx = pg.context_from_inputs(data, "activity")
        self.assertIn("ＯＯ公所", pg.fund_text(ctx))
        self.assertIn("由大隊發文", pg.issuing_note(ctx))
        self.assertIn("縣府", pg.issuing_note(pg.case_context("honor", TODAY)))

    def test_awards_add_clause_and_personnel_office(self):
        ctx = self._mixed()
        body = pg.submission_body(ctx)
        self.assertEqual(body[3], "四、辦理本案出（不）力人員依規定獎（懲）勵，敘獎額度如下：")
        self.assertEqual(body[4], "（一）大隊督辦人員（2名）嘉獎1次。")
        self.assertEqual(body[5], "（二）分隊承辦人員（1名）嘉獎2次。")
        self.assertIn("人事室", pg.meet_text(ctx))
        self.assertNotIn("嘉獎", pg.markdown_preview(ctx))
        self.assertEqual(pg.normalize_awards([{"role": "", "count": 1, "times": 1}, {"role": "x", "count": 0, "times": 1}]), [])

    def test_equipment_type_sections_and_rules(self):
        ctx = pg.case_context("equip_rescue", TODAY)
        self.assertEqual(ctx.title2, "115年度購置救災設備及後勤照護設備計畫")
        heads = [h for h, _ in pg.sections(ctx)]
        self.assertEqual(heads, ["緣由", "目的", "辦理單位", "設置地點", "使用單位", "購置項目", "預計完成日期",
                                 "購置經費", "驗收及管理", "其他"])
        findings = pg.check_plan(ctx, today=TODAY)
        titles = [f.title for f in findings]
        self.assertIn("設備類不適用「自籌款 30%」規定", titles)
        self.assertEqual(_titles(findings, pg.ERROR), [])
        self.assertNotIn("餐費及紀念品未超過補助金額 50%", titles)
        self.assertNotIn("沒有課程表", titles)
        body = pg.submission_body(ctx)
        self.assertIn("廠商估價單", body[2])
        self.assertIn("申請審核表", body[2])
        self.assertIn("臺東縣議員建議補助設備類案件建議表", body[2])
        self.assertEqual(pg.meet_text(ctx), "災害搶救科")

    def test_equipment_allows_equipment_kind_but_activity_still_rejects_it(self):
        ctx = pg.case_context("equip_rescue", TODAY)
        self.assertNotIn("活動類補助款不得用於資本門（購置設備）", _titles(pg.check_plan(ctx, today=TODAY), pg.ERROR))
        data = pg.case_inputs("honor", TODAY)
        data["items"].append({"name": "發電機", "kind": "設備購置", "qty": 1, "unit": "台", "price": 1000, "use": "x"})
        act = pg.context_from_inputs(data, "activity")
        self.assertIn("活動類補助款不得用於資本門（購置設備）", _titles(pg.check_plan(act, today=TODAY), pg.ERROR))

    def test_equipment_warns_on_personal_gear_and_meals(self):
        data = pg.case_inputs("equip_rescue", TODAY)
        data["items"] += [
            {"name": "個人制服", "kind": "設備購置", "qty": 1, "unit": "件", "price": 1000, "use": "x"},
            {"name": "便當", "kind": "餐費", "qty": 1, "unit": "份", "price": 100, "use": "x"},
        ]
        titles = _titles(pg.check_plan(pg.context_from_inputs(data, "equipment"), today=TODAY), pg.WARN)
        self.assertIn("設備類不得採購個人服裝及裝備", titles)
        self.assertIn("設備類概算表出現餐費或紀念品", titles)

    def test_equipment_docx_and_xlsx_have_no_schedule(self):
        from docx import Document
        from openpyxl import load_workbook
        ctx = pg.case_context("equip_rescue", TODAY)
        text = "\n".join(p.text for p in Document(io.BytesIO(pg.build_docx(ctx))).paragraphs)
        self.assertIn("購置項目", text)
        self.assertNotIn("課程表", text)
        self.assertEqual(load_workbook(io.BytesIO(pg.build_xlsx(ctx))).sheetnames, ["經費概算表"])


if __name__ == "__main__":
    unittest.main()
