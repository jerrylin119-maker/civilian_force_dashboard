import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import case_registry as cr  # noqa: E402


def acct(role, login="u", battalion="成功大隊", unit="成功分隊", display=""):
    return cr.Account(login=login, role=role, battalion=battalion, unit=unit, display=display)


def sample(**over):
    d = {"battalion": "成功大隊", "unit": "成功分隊", "officer": "王小明", "purpose": "活動費",
         "plan_name": "臺東縣消防局辦理成功義消分隊115年度績優表揚活動計畫",
         "date_start": date(2026, 12, 11), "date_end": date(2026, 12, 11),
         "total": 40000, "applied": 20000, "source_kind": "議員", "source_detail": "古志成議員"}
    d.update(over)
    return d


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.store = cr.MemoryStore()
        self.reg = cr.CaseRegistry(self.store, today=date(2026, 10, 27))
        self.unit = acct(cr.ROLE_UNIT)
        self.bn = acct(cr.ROLE_BATTALION, "bn", display="邱")
        self.sec = acct(cr.ROLE_SECTION, "sec", battalion="", unit="")

    def test_layout_matches_and_detects_drift(self):
        self.assertEqual(self.reg.check_layout(), [])
        self.store.rows[1][13] = "別的標題"
        self.assertTrue(any("N 欄" in p for p in self.reg.check_layout()))

    def test_layout_tolerates_real_header_text(self):
        self.store.rows[1][12] = "補助款來源細項\n（ＯＯＯ議員、ＯＯＯ代表、ＯＯＯ公所）\n【請依來源分案填寫】"
        self.store.rows[1][9] = "計畫總經費概算 (新台幣)"
        self.assertEqual(self.reg.check_layout(), [])

    def test_layout_accepts_merged_header_in_first_row(self):
        for idx in (29, 30, 31):               # 備註、審查無缺失、簡寫缺失：文字在第 1 列
            self.store.rows[0][idx] = self.store.rows[1][idx] + "\n(說明)"
            self.store.rows[1][idx] = ""
        self.assertEqual(self.reg.check_layout(), [])

    def test_layout_rejects_placeholder_headers(self):
        self.store.rows[1] = [f"第 {i + 1} 欄" for i in range(15)]
        problems = self.reg.check_layout()
        self.assertGreater(len(problems), 15)

    def test_prefilled_checkboxes_are_not_cases_and_row_lands_at_top(self):
        for _ in range(5):                      # 模擬 P、AE 欄預先放好的 FALSE 勾選方塊
            r = [""] * cr.N_COLS
            r[15], r[30] = "FALSE", "FALSE"
            self.store.rows.append(r)
        self.assertEqual(self.reg.cases(), [])
        no = self.reg.submit(self.unit, sample())
        self.assertEqual(self.store.rows[2][32], no)          # 第 3 列，不是最後一列
        self.assertEqual(self.store.rows[2][15], "FALSE")     # 勾選方塊沒被洗掉
        self.assertEqual(len(self.store.rows), 7)
        no2 = self.reg.submit(self.unit, sample(plan_name="第二件計畫"))
        self.assertEqual(self.store.rows[3][32], no2)
        self.assertEqual([c.case_no for c in self.reg.cases()], [no, no2])

    def test_failed_attempts_are_logged_without_case_number(self):
        self.reg.log_event(self.unit, "登錄未成功", "爭取經費不能大於計畫總經費", "手動填寫")
        row = self.store.read_log()[-1]
        self.assertEqual((row["案件編號"], row["階段"], row["帳號"]), ("", "登錄未成功", "u"))
        self.assertFalse(self.reg.log_failed)

    def test_case_numbers_are_per_battalion_and_sequential(self):
        a = self.reg.submit(self.unit, sample())
        b = self.reg.submit(self.unit, sample(plan_name="第二件計畫"))
        other = self.reg.submit(acct(cr.ROLE_UNIT, battalion="關山大隊", unit="延平分隊"),
                                sample(battalion="關山大隊", unit="延平分隊"))
        self.assertEqual((a, b, other), ("115-成-0001", "115-成-0002", "115-關-0001"))

    def test_submit_writes_same_columns_as_form(self):
        no = self.reg.submit(self.unit, sample())
        row = self.store.rows[2]
        self.assertEqual(row[2], "成功大隊")
        self.assertEqual(row[3], "成功分隊")
        self.assertEqual(row[7], "2026/12/11")
        self.assertEqual(row[9], "40000")
        self.assertEqual(row[10], "20000")
        self.assertEqual(row[32], no)
        self.assertEqual(self.reg.get(no).status, "待大隊初審")

    def test_unit_account_cannot_submit_for_other_unit(self):
        no = self.reg.submit(self.unit, sample(unit="別的分隊", battalion="台東大隊"))
        c = self.reg.get(no)
        self.assertEqual((c["unit"], c["battalion"]), ("成功分隊", "成功大隊"))

    def test_same_plan_cannot_be_registered_twice(self):
        no = self.reg.submit(self.unit, sample())
        with self.assertRaises(cr.RegistryError) as cm:
            self.reg.submit(self.unit, sample(plan_name=" " + sample()["plan_name"] + " "))
        self.assertIn(no, str(cm.exception))
        self.assertEqual(len(self.reg.cases()), 1)
        other_unit = acct(cr.ROLE_UNIT, "o", unit="別的分隊")
        self.reg.submit(other_unit, sample())               # 不同單位同名計畫不算重複

    def test_validation(self):
        for bad, text in ((sample(applied=50000), "不能大於"), (sample(plan_name=""), "計畫名稱"),
                          (sample(date_end=date(2026, 12, 1)), "不能早於"),
                          (sample(source_detail=""), "來源細項"), (sample(purpose="亂填"), "設備費或活動費")):
            with self.assertRaises(cr.RegistryError) as cm:
                self.reg.submit(self.unit, bad)
            self.assertIn(text, str(cm.exception))
        self.assertEqual(len(self.store.rows), 2)   # 一筆都沒寫進去

    def test_equipment_needs_no_dates(self):
        no = self.reg.submit(self.unit, sample(purpose="設備費", date_start="", date_end=""))
        self.assertTrue(no)

    def test_full_flow_and_status(self):
        no = self.reg.submit(self.unit, sample())
        self.reg.update_stage(self.bn, no, "first_review", {"first_result": "通過"})
        c = self.reg.get(no)
        self.assertEqual((c.status, c["first_by"]), ("待業務科收件", "邱"))
        self.reg.update_stage(self.sec, no, "second_review", {"received": True, "apply_doc_no": "1639"})
        c = self.reg.get(no)
        self.assertEqual(c.status, "申請複審中（已收件）")
        self.assertTrue(c["received_at"])
        self.reg.update_stage(self.sec, no, "reply", {"approve_status": "已核准", "approve_no": "115200472",
                                                      "approve_amount": "20,000"})
        self.assertEqual(self.reg.get(no).status, "已核准")
        self.reg.update_stage(self.bn, no, "settle_first", {"settle_first_result": "通過"})
        self.assertEqual(self.reg.get(no).status, "核銷複審中")
        self.reg.update_stage(self.sec, no, "settle_second", {"settle_doc_no": "4753", "settle_amount": "20000",
                                                              "settle_status": "已函發"})
        c = self.reg.get(no)
        self.assertEqual(c.status, "已結案")
        self.assertIsNone(cr.pending_for(c))

    def test_stage_order_enforced(self):
        no = self.reg.submit(self.unit, sample())
        with self.assertRaises(cr.RegistryError):
            self.reg.update_stage(self.sec, no, "second_review", {"received": True})
        with self.assertRaises(cr.RegistryError):
            self.reg.update_stage(self.sec, no, "settle_second", {"settle_status": "已函發"})

    def test_permissions(self):
        no = self.reg.submit(self.unit, sample())
        with self.assertRaises(cr.RegistryError):
            self.reg.update_stage(self.unit, no, "first_review", {"first_result": "通過"})
        other_bn = acct(cr.ROLE_BATTALION, "bn2", battalion="關山大隊", unit="")
        with self.assertRaises(cr.RegistryError):
            self.reg.update_stage(other_bn, no, "first_review", {"first_result": "通過"})
        with self.assertRaises(cr.RegistryError):
            self.reg.update_stage(self.bn, no, "second_review", {"received": True})

    def test_field_must_belong_to_stage(self):
        no = self.reg.submit(self.unit, sample())
        with self.assertRaises(cr.RegistryError):
            self.reg.update_stage(self.bn, no, "first_review", {"first_result": "通過", "approve_status": "已核准"})
        with self.assertRaises(cr.RegistryError):
            self.reg.update_stage(self.bn, no, "first_review", {"first_result": "隨便"})

    def test_return_and_resubmit(self):
        no = self.reg.submit(self.unit, sample())
        self.reg.update_stage(self.bn, no, "first_review", {"first_result": "退回分隊修正"}, return_reason="附件不足")
        c = self.reg.get(no)
        self.assertEqual((c.status, cr.pending_for(c)), ("退回分隊修正", cr.ROLE_UNIT))
        self.reg.resubmit(self.unit, no, {"applied": 15000})
        c = self.reg.get(no)
        self.assertEqual((c["applied"], c["first_result"], c.status), ("15000", "", "待大隊初審"))
        with self.assertRaises(cr.RegistryError):   # 已不是退回狀態，分隊不能再改
            self.reg.resubmit(self.unit, no, {"applied": 1000})

    def test_log_records_changes(self):
        no = self.reg.submit(self.unit, sample())
        self.reg.update_stage(self.bn, no, "first_review", {"first_result": "通過"})
        log = self.store.read_log()
        self.assertEqual([r["階段"] for r in log], ["① 登錄", "② 申請初審"])
        self.assertIn("初審結果：", log[1]["異動內容"])
        self.assertIn("通過", log[1]["異動內容"])
        self.assertNotIn("first_result", log[1]["異動內容"])
        self.assertIn("計畫名稱：", log[0]["異動內容"])
        self.assertEqual(log[1]["帳號"], "bn")

    def test_refuses_write_when_layout_changed(self):
        self.store.rows[1][10] = "被改掉了"
        with self.assertRaises(cr.RegistryError) as cm:
            self.reg.submit(self.unit, sample())
        self.assertIn("已停止寫入", str(cm.exception))

    def test_duplicate_number_is_repaired(self):
        no = self.reg.submit(self.unit, sample())
        # 模擬另一位同時寫入了相同編號
        row = [""] * cr.N_COLS
        row[2], row[6], row[32] = "成功大隊", "別案", no
        self.store.append_row(row)
        row_no = len(self.store.rows)
        self.assertEqual(len([c for c in self.reg.cases() if c.case_no == no]), 2)
        self.assertEqual(self.reg.next_case_no("成功大隊"), "115-成-0002")
        self.assertTrue(row_no)


class AccountTests(unittest.TestCase):
    def test_password_roundtrip(self):
        h = cr.hash_password("abc123")
        self.assertTrue(cr.verify_password("abc123", h))
        self.assertFalse(cr.verify_password("abc124", h))
        self.assertNotEqual(h, cr.hash_password("abc123"))

    def test_authenticate(self):
        accts = cr.load_accounts([
            {"login": "cheng", "role": "unit", "battalion": "成功大隊", "unit": "成功分隊",
             "password_hash": cr.hash_password("pw")},
            {"login": "bad", "role": "king", "password_hash": "x"},
            {"login": "", "role": "unit", "password_hash": "x"},
        ])
        self.assertEqual(list(accts), ["cheng"])
        self.assertIsNotNone(cr.authenticate(accts, "cheng", "pw"))
        self.assertIsNone(cr.authenticate(accts, "cheng", "no"))
        self.assertIsNone(cr.authenticate(accts, "nobody", "pw"))


class DraftFromPlanTests(unittest.TestCase):
    def test_equipment_and_mixed_sources(self):
        import plan_generator as pg
        ctx = pg.context_from_inputs(pg.case_inputs("equip_rescue", date(2026, 10, 27)), "equipment") \
            if hasattr(pg, "case_inputs") else None
        if ctx is None:
            self.skipTest("case_inputs not available")
        d = cr.draft_from_plan(ctx, officer="王")
        self.assertEqual((d["purpose"], d["date_start"], d["total"], d["applied"]), ("設備費", "", 97423, 97423))
        self.assertEqual(d["source_kind"], "議員")
        self.assertIn("議員", d["source_detail"])


class WorkflowGuardTests(unittest.TestCase):
    def setUp(self):
        self.store = cr.MemoryStore()
        self.reg = cr.CaseRegistry(self.store, today=date(2026, 10, 27))
        self.unit = acct(cr.ROLE_UNIT)
        self.bn = acct(cr.ROLE_BATTALION, "bn", display="邱")
        self.sec = acct(cr.ROLE_SECTION, "sec", battalion="", unit="災害搶救科")
        self.admin = acct(cr.ROLE_SECTION, "民力訓練科", battalion="", unit="民力運用及訓練科")

    def test_main_case_sheet_does_not_grow_a_column(self):
        self.assertEqual(cr.N_COLS, 33)
        self.assertEqual(cr.FIELDS["case_no"][0], 32)
        self.assertNotIn("return_reason", cr.FIELDS)
        self.assertNotIn("退回原因", cr.standard_header_row())
        self.assertNotIn("失敗次數", cr.standard_header_row())

    def test_section_cannot_skip_battalion_review_but_admin_can_and_is_logged(self):
        no = self.reg.submit(self.unit, sample(plan_name="初審權限"))
        other = acct(cr.ROLE_SECTION, "緊急救護科", battalion="", unit="緊急救護科")
        for who in (self.sec, other):
            with self.assertRaises(cr.RegistryError) as cm:
                self.reg.update_stage(who, no, "first_review", {"first_result": "通過"})
            self.assertIn("所屬大隊", str(cm.exception))
        self.assertEqual(self.reg.get(no).status, "待大隊初審")
        self.reg.update_stage(self.admin, no, "first_review", {"first_result": "通過"})
        self.assertEqual(self.reg.get(no).status, "待業務科收件")
        self.assertEqual(self.store.read_log()[-1]["來源"], "管理者覆核")
        self.assertEqual(self.store.read_log()[-1]["帳號"], "民力訓練科")

    def test_battalion_cannot_register_another_battalions_unit(self):
        bn = acct(cr.ROLE_BATTALION, "台東大隊", battalion="台東大隊", unit="")
        with self.assertRaises(cr.RegistryError) as cm:
            self.reg.submit(bn, sample(battalion="關山大隊", unit="池上分隊", plan_name="不該成功"))
        self.assertIn("不屬於", str(cm.exception))
        self.assertEqual(self.reg.cases(), [])
        no = self.reg.submit(bn, sample(battalion="關山大隊", unit="台東分隊", plan_name="自己的分隊"))
        self.assertEqual(self.reg.get(no)["battalion"], "台東大隊")
        self.assertTrue(no.startswith("115-台-"))
        no2 = self.reg.submit(bn, sample(purpose="設備費", date_start="", date_end="", unit="台東大隊",
                                         battalion="關山大隊", plan_name="大隊自辦"))
        self.assertEqual((self.reg.get(no2)["battalion"], self.reg.get(no2)["unit"]), ("台東大隊", "台東大隊"))

    def test_return_requires_a_reason_recorded_only_in_the_log(self):
        no = self.reg.submit(self.unit, sample(plan_name="退回原因"))
        with self.assertRaises(cr.RegistryError) as cm:
            self.reg.update_stage(self.bn, no, "first_review", {"first_result": "退回分隊修正"})
        self.assertIn("退回原因", str(cm.exception))
        with self.assertRaises(cr.RegistryError):
            self.reg.update_stage(self.bn, no, "first_review", {"first_result": "退回分隊修正"}, return_reason="   ")
        self.reg.update_stage(self.bn, no, "first_review", {"first_result": "退回分隊修正"},
                              return_reason="  金額不符規定  ")
        self.assertEqual(self.reg.get(no).status, "退回分隊修正")
        self.assertEqual(self.reg.latest_return_reason(no), "金額不符規定")
        row = self.store.read_all()[self.reg.get(no).row_no - 1]
        self.assertNotIn("金額不符規定", "".join(row))
        log = self.store.read_log()[-1]
        self.assertIn("退回原因：金額不符規定", log["異動內容"])
        self.assertTrue(any("金額不符規定" in r["異動內容"] for r in self.reg.visible_log(self.unit)))
        other = acct(cr.ROLE_UNIT, "東河", battalion="成功大隊", unit="東河分隊")
        self.assertFalse(any(r.get("案件編號") == no for r in self.reg.visible_log(other)))

    def test_settle_return_also_requires_a_reason(self):
        no = self._approve("核銷退回")
        with self.assertRaises(cr.RegistryError):
            self.reg.update_stage(self.bn, no, "settle_first", {"settle_first_result": "退回分隊修正"})
        self.reg.update_stage(self.bn, no, "settle_first", {"settle_first_result": "退回分隊修正"},
                              return_reason="憑證不足")
        self.assertEqual(self.reg.latest_return_reason(no), "憑證不足")
        self.assertEqual(self.reg.get(no).status, "核銷退回分隊修正")

    def test_progress_fields_are_choices_and_old_synonyms_still_move(self):
        no = self._receive("進度選項")
        with self.assertRaises(cr.RegistryError) as cm:
            self.reg.update_stage(self.sec, no, "reply", {"approve_status": "隨便寫"})
        self.assertIn("清單", str(cm.exception))
        self.reg.update_stage(self.sec, no, "reply", {"approve_status": "核准"})
        self.assertEqual(self.reg.get(no)["approve_status"], "已核准")
        self.assertEqual(self.reg.get(no).status, "已核准")

        legacy = self._receive("舊的核准")
        self.store.write_cells(self.reg.get(legacy).row_no, {cr.FIELDS["approve_status"][0]: "核准"})
        old = self.reg.get(legacy)
        self.assertEqual(old["approve_status"], "核准")
        self.assertEqual((old.status, cr.pending_for(old)), ("已核准", cr.ROLE_BATTALION))
        self.reg.update_stage(self.bn, legacy, "settle_first", {"settle_first_result": "通過"})

        stuck = self._receive("自由文字")
        self.store.write_cells(self.reg.get(stuck).row_no, {cr.FIELDS["approve_status"][0]: "縣府審查中"})
        self.assertEqual(self.reg.get(stuck).status, "縣府審查中")
        with self.assertRaises(cr.RegistryError):
            self.reg.update_stage(self.bn, stuck, "settle_first", {"settle_first_result": "通過"})
        self.reg.update_stage(self.sec, stuck, "reply", {"approve_status": "縣府審查中"})
        self.assertEqual(self.reg.get(stuck)["approve_status"], "縣府審查中")
        self.reg.update_stage(self.sec, stuck, "reply", {"approve_status": "已核准"})
        self.assertEqual(self.reg.get(stuck).status, "已核准")

        self.reg.update_stage(self.bn, no, "settle_first", {"settle_first_result": "通過"})
        self.reg.update_stage(self.sec, no, "settle_second", {"settle_status": "辦理中"})
        self.assertEqual(self.reg.get(no).status, "核銷：辦理中")
        self.reg.update_stage(self.sec, no, "settle_second", {"settle_status": "已函文"})
        closed = self.reg.get(no)
        self.assertEqual((closed["settle_status"], closed.status), ("已函發", "已結案"))
        self.store.write_cells(closed.row_no, {cr.FIELDS["settle_status"][0]: "已函文"})
        again = self.reg.get(no)
        self.assertEqual(again.status, "已結案")
        self.assertIsNone(cr.pending_for(again))

    def test_earlier_stage_locks_once_the_next_one_starts(self):
        no = self.reg.submit(self.unit, sample(plan_name="還能改初審"))
        self.reg.update_stage(self.bn, no, "first_review", {"first_result": "通過"})
        self.reg.update_stage(self.bn, no, "first_review", {"first_result": "退回分隊修正"}, return_reason="補計畫書")
        self.assertEqual(self.reg.get(no).status, "退回分隊修正")

        locked = self._approve("鎖定後不能改")
        with self.assertRaises(cr.RegistryError) as cm:
            self.reg.update_stage(self.bn, locked, "first_review", {"first_result": "退回分隊修正"},
                                  return_reason="想反悔")
        self.assertIn("鎖定", str(cm.exception))
        with self.assertRaises(cr.RegistryError) as cm:
            self.reg.update_stage(self.sec, locked, "second_review", {"received": False})
        self.assertIn("鎖定", str(cm.exception))
        self.assertEqual(self.reg.get(locked)["first_result"], "通過")
        self.assertTrue(cr._truthy(self.reg.get(locked)["received"]))
        self.reg.update_stage(self.admin, locked, "second_review", {"received": False})
        self.assertFalse(cr._truthy(self.reg.get(locked)["received"]))
        self.assertEqual(self.store.read_log()[-1]["來源"], "管理者覆核")
        self.reg.update_stage(self.sec, locked, "note", {"note": "補記"})
        self.assertEqual(self.reg.get(locked)["note"], "補記")
        self.assertNotEqual(self.store.read_log()[-1]["來源"], "管理者覆核")

    def test_admin_cannot_take_over_another_sections_open_stage(self):
        no = self._receive("別科進行中")
        self.assertNotIn(no, [c.case_no for c in self.reg.visible_cases(self.admin)])
        with self.assertRaises(cr.RegistryError):
            self.reg.update_stage(self.admin, no, "reply", {"approve_status": "審核中"})
        self.reg.update_stage(self.admin, no, "first_review", {"first_result": "通過", "first_by": "代核"})
        self.assertEqual(self.store.read_log()[-1]["來源"], "管理者覆核")
        self.assertEqual(self.reg.get(no)["first_by"], "代核")

    def _receive(self, name):
        no = self.reg.submit(self.unit, sample(plan_name=name))
        self.reg.update_stage(self.bn, no, "first_review", {"first_result": "通過"})
        self.reg.update_stage(self.sec, no, "second_review", {"received": True, "apply_doc_no": "1"})
        return no

    def _approve(self, name):
        no = self._receive(name)
        self.reg.update_stage(self.sec, no, "reply", {"approve_status": "已核准"})
        return no


class ReviewSummaryTests(unittest.TestCase):
    def setUp(self):
        self.store = cr.MemoryStore()
        self.reg = cr.CaseRegistry(self.store, today=date(2026, 10, 27))
        self.unit = acct(cr.ROLE_UNIT)
        self.bn = acct(cr.ROLE_BATTALION, "bn", battalion="成功大隊", unit="")
        self.sec = acct(cr.ROLE_SECTION, "災害搶救科", battalion="", unit="災害搶救科")

    def test_detail_is_not_written_onto_the_main_sheet(self):
        no = self.reg.submit(self.unit, sample(plan_name="有明細"), detail={
            "contact": "王小明 0912",
            "items": [{"name": "便當", "qty": "30", "unit": "份", "price": "100", "total": "3000", "remark": "中餐"}],
            "attachments": ["活動計畫（含經費概算表）1份"],
            "note": "請審核",
        })
        main = "".join(self.store.rows[self.reg.get(no).row_no - 1])
        self.assertNotIn("便當", main)
        self.assertNotIn("0912", main)
        self.assertEqual(cr.N_COLS, 33)
        detail = self.reg.submission_detail(no)
        self.assertEqual(detail["items"][0]["name"], "便當")
        self.assertEqual(detail["attachments"], ["活動計畫（含經費概算表）1份"])
        brief = cr.submission_brief(self.reg.get(no), detail)
        fields = dict(brief["fields"])
        self.assertEqual(fields["計畫名稱"], "有明細")
        self.assertIn("成功分隊", fields["單位"])
        self.assertEqual(fields["聯絡人"], "王小明 0912")
        self.assertEqual(fields["總經費"], "40,000")
        self.assertEqual(fields["爭取經費"], "20,000")
        self.assertIn("古志成", fields["經費來源"])
        self.assertEqual(fields["目前狀態"], "待大隊初審")
        self.assertEqual(fields["備註"], "請審核")
        self.assertEqual(brief["items"][0]["remark"], "中餐")

    def test_summary_without_detail_still_shows_the_sheet_fields(self):
        no = self.reg.submit(self.unit, sample(plan_name="只有摘要"))
        self.assertIsNone(self.reg.submission_detail(no))
        fields = dict(cr.submission_brief(self.reg.get(no), None)["fields"])
        self.assertEqual(fields["聯絡人"], "王小明")
        self.assertEqual(fields["計畫名稱"], "只有摘要")
        self.assertIn("2026/12/11", fields["活動日期"])

    def test_action_cases_follow_pending_role_without_rereading(self):
        no = self.reg.submit(self.unit, sample(plan_name="待初審"))
        calls = {"n": 0}
        real = self.store.read_all

        def counting():
            calls["n"] += 1
            return real()

        self.store.read_all = counting
        queued = self.reg.action_cases(self.bn, self.reg.cases())
        self.assertEqual([c.case_no for c in queued], [no])
        again = self.reg.action_cases(self.bn, queued)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(again[0].case_no, no)
        self.assertEqual(self.reg.action_cases(self.unit, queued), [])
        self.reg.update_stage(self.bn, no, "first_review", {"first_result": "退回分隊修正"}, return_reason="補件")
        returned = self.reg.action_cases(self.unit)
        self.assertEqual([c.case_no for c in returned], [no])
        self.reg.update_stage(self.bn, no, "first_review", {"first_result": "通過"})
        self.reg.update_stage(self.sec, no, "second_review", {"received": True})
        self.assertEqual([c.case_no for c in self.reg.action_cases(self.sec)], [no])

    def test_cached_value_does_not_reload_inside_the_window(self):
        calls = {"n": 0}

        def loader():
            calls["n"] += 1
            return ["案件"]

        cache = {}
        self.assertEqual(cr.cached_value(cache, "k", 100, 45, loader), ["案件"])
        self.assertEqual(cr.cached_value(cache, "k", 120, 45, loader), ["案件"])
        self.assertEqual(calls["n"], 1)
        self.assertEqual(cr.cached_value(cache, "k", 200, 45, loader), ["案件"])
        self.assertEqual(calls["n"], 2)

    def test_account_menu_label(self):
        self.assertEqual(cr.account_menu_label(acct(cr.ROLE_BATTALION, "關山大隊", battalion="關山大隊", unit="")),
                         "大隊｜關山大隊")
        self.assertEqual(cr.account_menu_label(acct(cr.ROLE_SECTION, "民力訓練科", battalion="", unit="民力運用及訓練科")),
                         "科室｜民力訓練科")


if __name__ == "__main__":
    unittest.main()
