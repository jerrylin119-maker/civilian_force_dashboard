import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import case_accounts as ca  # noqa: E402
import case_registry as cr  # noqa: E402

cr.PBKDF2_ROUNDS = 1000   # 測試用，加快雜湊


class AccountTests(unittest.TestCase):
    def setUp(self):
        self._force = ca.FORCE_PASSWORD_CHANGE
        ca.FORCE_PASSWORD_CHANGE = True        # 這個類別測的是「強制改密碼」開啟時的行為
        self.addCleanup(setattr, ca, "FORCE_PASSWORD_CHANGE", self._force)
        self.store = cr.MemoryStore()
        self.book = ca.AccountBook(self.store)
        self.book.ensure_seeded()

    def test_forced_change_is_off_by_default_and_flags_are_kept(self):
        """預設關閉：初始密碼的帳號可直接使用；標記留在試算表，重新開啟後立刻生效。"""
        self.assertFalse(self._force)
        ca.FORCE_PASSWORD_CHANGE = False
        acct = self.book.authenticate("成功分隊", "0000")
        self.assertIsNotNone(acct)
        self.assertFalse(acct.must_change)
        self.assertFalse(self.book.load()[ca.norm_login("成功分隊")].must_change)
        row = [r for r in self.store.read_tab(ca.ACCOUNT_TAB) if r and r[0] == "成功分隊"][0]
        self.assertEqual(str(row[ca.COL_MUST]).upper(), "TRUE")          # 試算表標記沒被清掉
        ca.FORCE_PASSWORD_CHANGE = True
        self.assertTrue(self.book.load()[ca.norm_login("成功分隊")].must_change)

    def test_org_counts_and_names(self):
        accts = ca.default_accounts()
        by_role = {r: [a for a in accts if a["role"] == r] for r in cr.ROLE_LABELS}
        self.assertEqual((len(by_role[cr.ROLE_BATTALION]), len(by_role[cr.ROLE_UNIT]), len(by_role[cr.ROLE_SECTION])),
                         (4, 27, 6))
        self.assertEqual(len({a["login"] for a in accts}), 37)          # 帳號名稱不重複
        for a in by_role[cr.ROLE_UNIT]:
            self.assertIn(a["battalion"], cr.BATTALION_CODES)           # 每個分隊都對得到合法的大隊
        for no_account in ("救災救護指揮中心", "災害管理科", "人事室", "會計室", "政風室", "科技救災分隊", "安檢隊"):
            self.assertNotIn(no_account, {a["login"] for a in accts})

    def test_seeded_tab_stores_hashes_not_plaintext(self):
        rows = self.store.read_tab(ca.ACCOUNT_TAB)
        self.assertEqual(rows[0], ca.ACCOUNT_HEADERS)
        self.assertEqual(len(rows), 38)
        self.assertTrue(all("0000" not in r[4] or "$" in r[4] for r in rows[1:]))
        self.assertTrue(all(r[4].count("$") == 1 and len(r[4]) > 40 for r in rows[1:]))
        self.assertTrue(all(r[5] == "TRUE" for r in rows[1:]))

    def test_seeding_is_idempotent_and_adds_only_missing(self):
        self.assertEqual(self.book.ensure_seeded(), 0)
        self.assertEqual(len(self.store.read_tab(ca.ACCOUNT_TAB)), 38)
        del self.store.tabs[ca.ACCOUNT_TAB][5]                         # 少一個帳號
        self.assertEqual(self.book.ensure_seeded(), 1)
        self.assertEqual(len(self.store.read_tab(ca.ACCOUNT_TAB)), 38)

    def test_login_by_name_with_default_password(self):
        a = self.book.authenticate("成功分隊", "0000")
        self.assertEqual((a.role, a.battalion, a.unit, a.must_change), (cr.ROLE_UNIT, "成功大隊", "成功分隊", True))
        b = self.book.authenticate("成功大隊", "0000")
        self.assertEqual((b.role, b.unit), (cr.ROLE_BATTALION, ""))
        s = self.book.authenticate("民力訓練科", "0000")
        self.assertEqual((s.role, s.unit, s.is_admin), (cr.ROLE_SECTION, "民力運用及訓練科", True))
        self.assertFalse(self.book.authenticate("緊急救護科", "0000").is_admin)

    def test_login_accepts_tai_variant_and_spaces(self):
        self.assertEqual(self.book.authenticate("臺東分隊", "0000").login, "台東分隊")
        self.assertEqual(self.book.authenticate(" 臺東大隊 ", "0000").login, "台東大隊")

    def test_wrong_password_and_unknown_account(self):
        self.assertIsNone(self.book.authenticate("成功分隊", "1234"))
        self.assertIsNone(self.book.authenticate("救災救護指揮中心", "0000"))

    def test_change_password(self):
        with self.assertRaises(cr.RegistryError):
            self.book.change_password("成功分隊", "錯的", "abcdef")
        for bad in ("", "   ", "0000"):
            with self.assertRaises(cr.RegistryError):
                self.book.change_password("成功分隊", "0000", bad)
        self.book.change_password("成功分隊", "0000", "123")
        self.assertIsNone(self.book.authenticate("成功分隊", "0000"))
        a = self.book.authenticate("成功分隊", "123")
        self.assertFalse(a.must_change)
        self.assertTrue(self.book.authenticate("東河分隊", "0000"))      # 其他帳號不受影響

    def test_reset_password_only_by_admin(self):
        self.book.change_password("成功分隊", "0000", "123")
        with self.assertRaises(cr.RegistryError):
            self.book.reset_password(self.book.authenticate("緊急救護科", "0000"), "成功分隊")
        with self.assertRaises(cr.RegistryError):
            self.book.reset_password(self.book.authenticate("成功大隊", "0000"), "成功分隊")
        self.book.reset_password(self.book.authenticate("民力訓練科", "0000"), "成功分隊")
        a = self.book.authenticate("成功分隊", "0000")
        self.assertTrue(a and a.must_change)
        self.assertIsNone(self.book.authenticate("成功分隊", "123"))

    def test_list_accounts_order(self):
        names = [a.login for a in self.book.list_accounts()]
        self.assertEqual(len(names), 37)
        self.assertEqual(names[0], "台東大隊")
        self.assertEqual(names[-len(ca.SECTIONS):], list(ca.SECTIONS))
        for battalion, units in ca.ORG.items():
            start = names.index(battalion)
            self.assertEqual(names[start + 1:start + 1 + len(units)], units)
        self.assertLess(names.index("池上分隊"), names.index("民力訓練科"))

    def test_new_password_only_rejects_empty_and_initial(self):
        for bad in ("", "   ", "0000", " 0000 "):
            with self.assertRaises(cr.RegistryError):
                self.book.change_password("長濱分隊", "0000", bad)
        self.book.change_password("長濱分隊", "0000", "1")
        self.assertIsNotNone(self.book.authenticate("長濱分隊", "1"))
        self.book.change_password("長濱分隊", "1", "abcdefgh")
        changed = self.book.authenticate("長濱分隊", "abcdefgh")
        self.assertFalse(changed.must_change)
        self.assertIsNone(self.book.authenticate("長濱分隊", "1"))

    def test_default_password_cannot_use_the_system_until_changed(self):
        reg = cr.CaseRegistry(self.store, today=date(2026, 11, 11))
        acct, err = self.book.login("成功分隊", "0000")
        self.assertEqual(err, "")
        self.assertTrue(acct.must_change)
        with self.assertRaises(cr.RegistryError) as cm:
            reg.submit(acct, sample())
        self.assertIn("更改密碼", str(cm.exception))
        self.book.change_password("成功分隊", "0000", "newpass1")
        ready = self.book.authenticate("成功分隊", "newpass1")
        no = reg.submit(ready, sample())
        self.assertTrue(no.startswith("115-成-"))

    def test_login_with_default_password_forces_the_flag_back_on(self):
        row = self.book._row_no("金峰分隊")
        self.store.update_tab_cells(ca.ACCOUNT_TAB, row, {ca.COL_MUST: "FALSE"})
        self.assertFalse(self.book.authenticate("金峰分隊", "0000").must_change)
        acct, err = self.book.login("金峰分隊", "0000")
        self.assertEqual(err, "")
        self.assertTrue(acct.must_change)
        self.assertTrue(self.book.load()[ca.norm_login("金峰分隊")].must_change)

    def test_wrong_password_does_not_lock_or_add_columns(self):
        for _ in range(8):
            acct, err = self.book.login("成功分隊", "wrong")
            self.assertIsNone(acct)
            self.assertEqual(err, "帳號或密碼錯誤")
        acct, err = self.book.login("成功分隊", "0000")
        self.assertIsNotNone(acct)
        self.assertEqual(err, "")
        header = self.store.read_tab(ca.ACCOUNT_TAB)[0]
        self.assertEqual(header, ["帳號", "角色", "所屬大隊", "單位", "密碼雜湊", "需更改密碼", "更新時間"])
        self.assertNotIn("失敗次數", header)
        self.assertNotIn("最後失敗時間", header)
        self.assertNotIn("鎖定至", header)

    def test_login_box_does_not_preselect_a_section_or_publish_the_password(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "case_pages.py"), encoding="utf-8") as fh:
            text = fh.read()
        start = text.index("def _login_box")
        end = text.index("\ndef ", start + 1)
        body = text[start:end]
        self.assertIn("selectbox", body)
        self.assertIn("index=None", body)
        self.assertIn("請選擇單位", body)
        self.assertNotIn("0000", body)
        self.assertNotIn("民力訓練科", body)
        self.assertNotIn("初次使用", body)


def sample():
    return {"battalion": "成功大隊", "unit": "成功分隊", "officer": "王", "purpose": "活動費",
            "plan_name": "測試計畫", "date_start": date(2026, 12, 11), "date_end": date(2026, 12, 11),
            "total": 40000, "applied": 20000, "source_kind": "議員", "source_detail": "王議員"}


class DeptRuleTests(unittest.TestCase):
    def setUp(self):
        self.reg = cr.CaseRegistry(cr.MemoryStore(), today=date(2026, 10, 27))
        self.book = ca.AccountBook(self.reg.store)
        self.book.ensure_seeded()
        for name in ("成功分隊", "成功大隊", "民力訓練科", "災害搶救科"):
            self.book.change_password(name, "0000", "newpass1")
        self.unit = self.book.authenticate("成功分隊", "newpass1")
        self.bn = self.book.authenticate("成功大隊", "newpass1")
        self.civil = self.book.authenticate("民力訓練科", "newpass1")
        self.rescue = self.book.authenticate("災害搶救科", "newpass1")
        self.no = self.reg.submit(self.unit, sample())
        self.reg.update_stage(self.bn, self.no, "first_review",
                              {"first_result": "通過", "review_checks": [k for k, _ in cr.review_items(True)]})

    def test_sections_cannot_submit(self):
        with self.assertRaises(cr.RegistryError):
            self.reg.submit(self.civil, sample())

    def test_battalion_can_submit_for_itself(self):
        no = self.reg.submit(self.bn, dict(sample(), unit="成功大隊"))
        self.assertEqual(self.reg.get(no)["unit"], "成功大隊")

    def test_unassigned_case_visible_to_all_sections_then_only_to_owner(self):
        civil_list = lambda who: [c.case_no for c in self.reg.visible_cases(who)]
        other = self.book.authenticate("資通作業科", "0000")
        for who in (self.civil, self.rescue, other):                     # 還沒接案，各科都看得到、都能接
            self.assertIn(self.no, civil_list(who))
            self.assertTrue(self.reg.is_mine(who, self.reg.get(self.no)))
        self.reg.update_stage(self.rescue, self.no, "second_review", {"received": True})
        c = self.reg.get(self.no)
        self.assertEqual(c["section_dept"], "災害搶救科")
        self.assertIn(self.no, civil_list(self.rescue))
        self.assertNotIn(self.no, civil_list(self.civil))                # 民力訓練科也看不到
        self.assertNotIn(self.no, civil_list(other))
        for who in (self.civil, other):
            self.assertFalse(self.reg.can_edit(who, "reply", c))
            self.assertFalse(self.reg.can_edit(who, "note", c))
            with self.assertRaises(cr.RegistryError):
                self.reg.update_stage(who, self.no, "reply", {"approve_status": "已核准"})
        self.assertTrue(self.reg.can_edit(self.rescue, "reply", c))
        self.assertIn(self.no, civil_list(self.unit))                    # 分隊、大隊不受影響
        self.assertIn(self.no, civil_list(self.bn))

    def test_handing_over_to_another_section(self):
        self.reg.update_stage(self.rescue, self.no, "second_review", {"received": True})
        self.reg.update_stage(self.rescue, self.no, "second_review", {"section_dept": "民力運用及訓練科"})
        c = self.reg.get(self.no)
        self.assertEqual(c["section_dept"], "民力運用及訓練科")
        self.assertIn(self.no, [x.case_no for x in self.reg.visible_cases(self.civil)])
        self.assertNotIn(self.no, [x.case_no for x in self.reg.visible_cases(self.rescue)])

    def test_dept_must_be_a_known_section(self):
        with self.assertRaises(cr.RegistryError):
            self.reg.update_stage(self.rescue, self.no, "second_review", {"received": True, "section_dept": "亂寫科"})

    def test_dept_names_match_account_names(self):
        self.assertEqual(tuple(ca.SECTIONS.values()), cr.SECTION_DEPTS)

    def test_battalion_and_unit_visibility(self):
        other_bn = self.book.authenticate("關山大隊", "0000")
        other_unit = self.book.authenticate("東河分隊", "0000")
        self.assertEqual(self.reg.visible_cases(other_bn), [])
        self.assertEqual(self.reg.visible_cases(other_unit), [])

    def test_is_mine_for_unit_and_battalion(self):
        c = self.reg.get(self.no)
        self.assertFalse(self.reg.is_mine(self.unit, c))
        self.assertFalse(self.reg.is_mine(self.bn, c))
        self.assertTrue(self.reg.is_mine(self.civil, c))
        other_unit = self.book.authenticate("東河分隊", "0000")
        no2 = self.reg.submit(self.unit, dict(sample(), plan_name="第二件計畫"))
        self.reg.update_stage(self.bn, no2, "first_review", {"first_result": "退回分隊修正"}, return_reason="請修正金額")
        self.assertTrue(self.reg.is_mine(self.unit, self.reg.get(no2)))
        self.assertFalse(self.reg.is_mine(other_unit, self.reg.get(no2)))


if __name__ == "__main__":
    unittest.main()
