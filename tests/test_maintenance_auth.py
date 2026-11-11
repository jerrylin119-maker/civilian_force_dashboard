import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maintenance_auth as ma  # noqa: E402


class MaintenanceAuthTests(unittest.TestCase):
    def test_missing_secret_disables_login_and_drops_old_passwords(self):
        for value in (None, "", "   "):
            passwords = ma.maintenance_passwords(value)
            self.assertEqual(passwords, set())
            for old in ("119", "admin119", "minli119"):
                self.assertNotIn(old, passwords)

    def test_configured_secret_is_the_only_password(self):
        self.assertEqual(ma.maintenance_passwords("  正確的密碼  "), {"正確的密碼"})
        self.assertNotIn("119", ma.maintenance_passwords("正確的密碼"))

    def test_app_source_has_no_hardcoded_fallback(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "app.py"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn("admin119", text)
        self.assertNotIn("minli119", text)
        self.assertNotIn("預設科內維護密碼", text)
        self.assertIn("maintenance_passwords", text)
        self.assertIn("MAINTENANCE_DISABLED_MESSAGE", text)


if __name__ == "__main__":
    unittest.main()
