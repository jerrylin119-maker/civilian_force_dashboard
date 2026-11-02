import datetime as dt
import sys

sys.path.insert(0, ".")
from streamlit.testing.v1 import AppTest


def app():
    from welfare_guide import render_welfare_guide
    render_welfare_guide()


def texts(at):
    out = []
    for kind in ("markdown", "success", "info", "warning", "caption"):
        out += [e.value for e in getattr(at, kind)]
    return "\n".join(out)


at = AppTest.from_function(app, default_timeout=30).run()
assert not at.exception, at.exception
assert "先選事故情形" in texts(at)

# 喪葬 + 救災義消 + 5/1(4/26 之後)=國泰
at.radio(key="wg_case").set_value("喪葬").run()
at.radio(key="wg_cat").set_value("救災義消").run()
at.checkbox(key="wg_ev_known").set_value(True).run()
at.date_input(key="wg_date").set_value(dt.date(2026, 5, 1)).run()
assert not at.exception, at.exception
t = texts(at)
assert "團體保險用 國泰人壽" in t, t
assert "共 8 項,須全部備齊" in t
assert "民力運用及訓練科、綜合企劃及安全衛生科、會計室、政風室" in t

# 日期改成 4/1 = 新光(9 項)
at.date_input(key="wg_date").set_value(dt.date(2026, 4, 1)).run()
t = texts(at)
assert "團體保險用 新光人壽" in t and "共 9 項" in t, t

# 邊界:4/26 含以前用新光,4/27 用國泰
at.date_input(key="wg_date").set_value(dt.date(2026, 4, 26)).run()
assert "團體保險用 新光人壽" in texts(at)
at.date_input(key="wg_date").set_value(dt.date(2026, 4, 27)).run()
assert "團體保險用 國泰人壽" in texts(at)

# 退隊:團保不適用,會辦單位提示待確認(只選福利互助)
at.radio(key="wg_case").set_value("退隊").run()
assert not at.exception, at.exception
t = texts(at)
assert "團體保險:**不適用**" in t.replace(" ", ""), t
assert "附件二" in t

# 失能、住院、因公受傷
for name in ["失能", "住院醫療(重大傷病)", "因公受傷(執行任務受傷)"]:
    at.radio(key="wg_case").set_value(name).run()
    assert not at.exception, (name, at.exception)

# 因公受傷 + 防宣 + 今天之後 = 國泰;勾掉基金會 -> 3 個單位
at.radio(key="wg_cat").set_value("防宣義消").run()
at.date_input(key="wg_date").set_value(dt.date(2026, 10, 31)).run()
t = texts(at)
assert "團體保險用 國泰人壽" in t
at.checkbox(key="wg_use_fund_因公受傷(執行任務受傷)").set_value(False).run()
t = texts(at)
assert "民力運用及訓練科、綜合企劃及安全衛生科、會計室" in t
assert "政風室" not in t.split("陳報單要會辦")[1].split("步驟 3")[0]

# 勾掉福利互助、只剩團保 -> 民力科
at.checkbox(key="wg_use_ben_因公受傷(執行任務受傷)").set_value(False).run()
at.checkbox(key="wg_use_fund_因公受傷(執行任務受傷)").set_value(False).run()
t = texts(at)
seg = t.split("陳報單要會辦")[1].split("步驟 3")[0]
assert "民力運用及訓練科" in seg and "綜合企劃" not in seg, seg
print("全部通過")
