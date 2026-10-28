"""案件登錄與管制的 Streamlit 畫面。邏輯都在 case_registry.py，這裡只負責顯示與收資料。

設定放在 Streamlit Secrets（沒有設定時整個功能不出現，不影響現有網站）：

    [case_registry]
    backend = "sheet"                 # 或 "memory"（示範，資料不保存）
    spreadsheet_id = "..."
    worksheet = "表單回應 1"
    [case_registry.service_account]   # 服務帳號 JSON 的內容
    ...

帳號不放在 Secrets：第一次連線時依組織架構在試算表建立「帳號」工作表（預設密碼 0000，只存雜湊）。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import case_accounts as ca
import case_registry as cr

STAGE_ORDER = ["first_review", "second_review", "reply", "settle_first", "settle_second", "defect", "note"]
MAX_LOGIN_FAILS = 5

# 各階段畫面欄位：(key, 標籤, 型態, 選項)
STAGE_WIDGETS = {
    "first_review": [("first_result", "審核結果", "select", [""] + cr.FIRST_REVIEW_RESULTS),
                     ("first_by", "審核人員（留空會填您的名稱）", "text", None)],
    "second_review": [("received", "已收件", "bool", None), ("section_dept", "承辦科室", "text", None),
                      ("section_officer", "承辦人", "text", None),
                      ("apply_doc_no", "申請補助發文字號（多筆請換行）", "area", None)],
    "reply": [("approve_status", "補助單位核准進度", "text", None), ("approve_no", "核准案號（或公文文號）", "area", None),
              ("approve_amount", "核准金額", "area", None), ("letter_back", "核准函是否回寄分隊", "text", None)],
    "settle_first": [("settle_first_result", "核銷初審結果", "select", [""] + cr.FIRST_REVIEW_RESULTS),
                     ("settle_first_by", "審核人員（留空會填您的名稱）", "text", None)],
    "settle_second": [("settle_doc_no", "核銷發文字號", "area", None), ("settle_amount", "核銷金額", "area", None),
                      ("settle_status", "核銷進度", "text", None)],
    "defect": [("no_defect", "審查無缺失", "bool", None), ("defect", "簡寫缺失", "text", None)],
    "note": [("note", "備註（日期異動等）", "area", None)],
}


# ---------------------------------------------------------------- 設定與連線
def get_config():
    try:
        cfg = st.secrets.get("case_registry")
    except Exception:
        return None
    return dict(cfg) if cfg else None


@st.cache_resource(show_spinner=False)
def _make_store(backend, spreadsheet_id, worksheet, sa_items):
    if backend == "memory":
        return cr.MemoryStore()
    return cr.SheetStore(spreadsheet_id, worksheet, dict(sa_items))


def get_registry(cfg):
    sa = cfg.get("service_account") or {}
    store = _make_store(cfg.get("backend", "sheet"), cfg.get("spreadsheet_id", ""),
                        cfg.get("worksheet", "表單回應 1"), tuple(sorted(dict(sa).items())))
    return cr.CaseRegistry(store)


@st.cache_resource(show_spinner=False)
def _seed_accounts(_store, key):
    """每個伺服器程序只檢查一次：帳號工作表不存在或缺帳號就補上。"""
    return ca.AccountBook(_store).ensure_seeded()


def get_accounts(reg):
    _seed_accounts(reg.store, id(reg.store))
    return ca.AccountBook(reg.store)


def is_enabled():
    return get_config() is not None


# ---------------------------------------------------------------- 登入
def _login_box(book):
    accounts = book.list_accounts()
    if not accounts:
        st.error("沒有可用的帳號，請通知管理者。")
        return
    st.markdown("#### 🔐 案件登錄系統登入")
    fails = st.session_state.get("case_login_fails", 0)
    if fails >= MAX_LOGIN_FAILS:
        st.error("登入失敗次數過多，請重新整理頁面後再試。")
        return

    def label(a):
        if a.role == cr.ROLE_SECTION:
            return f"科室｜{a.login}"
        if a.role == cr.ROLE_BATTALION:
            return f"大隊｜{a.login}"
        return f"{a.battalion}　{a.login}"

    with st.form("case_login"):
        pick = st.selectbox("帳號（單位名稱）", accounts, format_func=label)
        pw = st.text_input("密碼", type="password")
        go = st.form_submit_button("登入")
    if go:
        acct = book.authenticate(pick.login, pw)
        if acct:
            st.session_state["case_user"] = acct
            st.session_state["case_login_fails"] = 0
            st.rerun()
        st.session_state["case_login_fails"] = fails + 1
        st.error("密碼錯誤")
    st.caption("初次使用的密碼是 0000，登入後請先到「🔑 更改密碼」更新。")


# ---------------------------------------------------------------- 共用
def _cases_df(cases):
    return pd.DataFrame([{
        "案件編號": c.case_no, "大隊": c["battalion"], "單位": c["unit"], "計畫名稱": c["plan_name"],
        "活動日期": c["date_start"], "爭取經費": cr.to_int(c["applied"]), "目前狀態": c.status,
        "輪到": cr.ROLE_LABELS.get(cr.pending_for(c), "—"),
    } for c in cases])


def _visible(reg, acct):
    cases = reg.cases()
    if acct.role == cr.ROLE_UNIT:
        return [c for c in cases if c["unit"] == acct.unit and c["battalion"] == acct.battalion]
    if acct.role == cr.ROLE_BATTALION:
        return [c for c in cases if c["battalion"] == acct.battalion]
    return cases


def _flash():
    msg = st.session_state.pop("case_flash", None)
    if msg:
        st.success(msg)


# ---------------------------------------------------------------- 各頁
def _page_list(reg, acct):
    cases = _visible(reg, acct)
    mine = [c for c in cases if reg.is_mine(acct, c)]
    c1, c2, c3 = st.columns(3)
    c1.metric("案件數", len(cases))
    c2.metric("輪到我處理", len(mine))
    c3.metric("已結案", sum(1 for c in cases if c.status == "已結案"))
    only_mine = st.checkbox("只看輪到我處理的", value=bool(mine))
    show = mine if only_mine else cases
    if not show:
        st.info("目前沒有案件。")
        return
    st.dataframe(_cases_df(sorted(show, key=lambda c: c.case_no, reverse=True)),
                 use_container_width=True, hide_index=True)


def _page_new(reg, acct, pg):
    hand = st.session_state.get("case_handoff")
    ver = st.session_state.get("case_form_ver", 0)
    data = {}
    if hand:
        data = dict(hand)
        st.success(f"已從計畫書產生器帶入「{hand['plan_name']}」（檢核無錯誤）。請核對後補上不足的欄位。")
    else:
        st.warning("這份資料沒有經過計畫書產生器檢核。建議先用「✏️ 計畫書產生器」製作並通過檢核，再回來登錄。")
    is_unit = acct.role == cr.ROLE_UNIT
    with st.form(f"case_new_{ver}"):
        bn_list = cr.BATTALIONS
        bn_default = acct.battalion if acct.battalion in bn_list else bn_list[0]
        battalion = st.selectbox("所屬大隊", bn_list, index=bn_list.index(bn_default), disabled=is_unit)
        unit = st.text_input("承辦單位（大隊本身辦理填大隊名稱）",
                             value=acct.unit if is_unit else (data.get("unit", "") or acct.battalion), disabled=is_unit)
        officer = st.text_input("承辦人", value=data.get("officer", "") or acct.display)
        purpose = st.selectbox("經費用途", cr.PURPOSES,
                               index=cr.PURPOSES.index(data["purpose"]) if data.get("purpose") in cr.PURPOSES else 0)
        plan_name = st.text_input("計畫名稱", value=data.get("plan_name", ""))
        d1, d2 = st.columns(2)
        ds = d1.text_input("活動日期（始）YYYY/M/D", value=cr.date_text(data.get("date_start", "")))
        de = d2.text_input("活動日期（末）YYYY/M/D", value=cr.date_text(data.get("date_end", "")))
        m1, m2 = st.columns(2)
        total = m1.number_input("計畫總經費概算（新臺幣）", min_value=0, step=100, value=int(data.get("total", 0)))
        applied = m2.number_input("爭取經費（新臺幣）", min_value=0, step=100, value=int(data.get("applied", 0)))
        source_kind = st.text_input("補助款來源", value=data.get("source_kind", ""))
        source_detail = st.text_input("補助款來源細項（○○議員、○○代表、○○公所；請依來源分案填寫）",
                                      value=data.get("source_detail", ""))
        go = st.form_submit_button("送出登錄", type="primary")
    if go:
        try:
            case_no = reg.submit(acct, {
                "battalion": battalion, "unit": unit, "officer": officer, "purpose": purpose, "plan_name": plan_name,
                "date_start": ds, "date_end": de, "total": total, "applied": applied,
                "source_kind": source_kind, "source_detail": source_detail,
            }, source="計畫產生器" if hand else "手動填寫")
        except cr.RegistryError as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            st.error(f"寫入失敗，案件沒有登錄：{type(exc).__name__}。請稍後再試或通知管理者。")
            return
        st.session_state.pop("case_handoff", None)
        st.session_state["case_form_ver"] = ver + 1
        st.session_state["case_flash"] = f"✅ 已登錄。案件編號：{case_no}　請把單號寫在紙本文件上。"
        st.rerun()


def _stage_form(reg, acct, case, stage, expanded):
    widgets = STAGE_WIDGETS[stage]
    with st.expander(cr.STAGE_LABELS[stage], expanded=expanded):
        with st.form(f"stage_{stage}_{case.case_no}"):
            vals = {}
            for key, label, kind, opts in widgets:
                cur = case[key]
                if kind == "select":
                    vals[key] = st.selectbox(label, opts, index=opts.index(cur) if cur in opts else 0)
                elif kind == "bool":
                    vals[key] = st.checkbox(label, value=cr._truthy(cur))
                elif kind == "area":
                    vals[key] = st.text_area(label, value=cur)
                else:
                    default = cur or (acct.unit if key == "section_dept" else "")
                    vals[key] = st.text_input(label, value=default)
            go = st.form_submit_button("儲存")
        if go:
            try:
                diff = reg.update_stage(acct, case.case_no, stage, vals)
            except cr.RegistryError as exc:
                st.error(str(exc))
                return
            except Exception as exc:
                st.error(f"寫入失敗，沒有更新：{type(exc).__name__}")
                return
            st.session_state["case_flash"] = "已儲存。" if diff else "沒有變更。"
            st.rerun()


def _page_handle(reg, acct):
    cases = _visible(reg, acct)
    if not cases:
        st.info("目前沒有案件。")
        return
    mine = [c.case_no for c in cases if reg.is_mine(acct, c)]
    options = sorted((c.case_no for c in cases), key=lambda n: (n not in mine, n))
    by_no = {c.case_no: c for c in cases}
    pick = st.selectbox("選擇案件", options, format_func=lambda n: (
        f"{'🔔 ' if n in mine else ''}{n}｜{by_no[n]['unit']}｜{by_no[n]['plan_name'][:24]}｜{by_no[n].status}"))
    case = by_no[pick]
    st.markdown(f"**{case['plan_name']}**")
    st.caption(f"{case['battalion']} {case['unit']}　承辦人 {case['officer']}　用途 {case['purpose']}　"
               f"活動日期 {case['date_start'] or '—'}～{case['date_end'] or '—'}")
    st.markdown(f"總經費 **{cr.to_int(case['total']):,}** 元｜爭取 **{cr.to_int(case['applied']):,}** 元｜"
                f"來源 {case['source_detail']}｜目前狀態 **{case.status}**")
    if acct.role == cr.ROLE_UNIT:
        if cr.pending_for(case) == cr.ROLE_UNIT:
            _resubmit_form(reg, acct, case)
        else:
            st.info("這件案子目前不需要分隊處理。")
        return
    current = {"待大隊初審": "first_review", "待業務科收件": "second_review", "申請複審中（已收件）": "reply",
               "已核准": "settle_first", "核銷複審中": "settle_second"}.get(case.status)
    for stage in STAGE_ORDER:
        if reg.can_edit(acct, stage, case):
            _stage_form(reg, acct, case, stage, expanded=(stage == current))


def _resubmit_form(reg, acct, case):
    st.warning(f"這件案子被退回：{case.status}。修正後送出會重新交給大隊初審。")
    with st.form(f"resubmit_{case.case_no}"):
        plan_name = st.text_input("計畫名稱", value=case["plan_name"])
        officer = st.text_input("承辦人", value=case["officer"])
        m1, m2 = st.columns(2)
        total = m1.number_input("計畫總經費概算", min_value=0, step=100, value=cr.to_int(case["total"]))
        applied = m2.number_input("爭取經費", min_value=0, step=100, value=cr.to_int(case["applied"]))
        d1, d2 = st.columns(2)
        ds = d1.text_input("活動日期（始）", value=case["date_start"])
        de = d2.text_input("活動日期（末）", value=case["date_end"])
        source_kind = st.text_input("補助款來源", value=case["source_kind"])
        source_detail = st.text_input("補助款來源細項", value=case["source_detail"])
        go = st.form_submit_button("修正並重新送審", type="primary")
    if go:
        try:
            reg.resubmit(acct, case.case_no, {
                "plan_name": plan_name, "officer": officer, "total": total, "applied": applied, "date_start": ds,
                "date_end": de, "source_kind": source_kind, "source_detail": source_detail})
        except cr.RegistryError as exc:
            st.error(str(exc))
            return
        st.session_state["case_flash"] = "已重新送審。"
        st.rerun()


def _page_log(reg):
    rows = reg.store.read_log(300)
    if not rows:
        st.info("還沒有異動紀錄。")
        return
    st.dataframe(pd.DataFrame(rows[::-1]), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------- 入口
def _page_password(book, acct):
    if acct.must_change:
        st.warning("您還在使用預設密碼 0000，請更新密碼。")
    with st.form("case_pw"):
        old = st.text_input("目前的密碼", type="password")
        new = st.text_input(f"新密碼（至少 {ca.MIN_PASSWORD_LEN} 碼，不可用 0000）", type="password")
        new2 = st.text_input("再輸入一次新密碼", type="password")
        go = st.form_submit_button("更改密碼")
    if go:
        if new != new2:
            st.error("兩次輸入的新密碼不一致")
            return
        try:
            book.change_password(acct.login, old, new)
        except cr.RegistryError as exc:
            st.error(str(exc))
            return
        acct.must_change = False
        st.session_state["case_flash"] = "密碼已更新，下次請用新密碼登入。"
        st.rerun()


def _page_accounts(book, acct):
    st.caption("忘記密碼的同仁，由您重設回預設密碼 0000。系統只存雜湊，看不到原本的密碼。")
    accounts = book.list_accounts()
    pick = st.selectbox("要重設的帳號", accounts, format_func=lambda a: f"{a.battalion} {a.login}".strip())
    if st.button("重設為 0000"):
        try:
            book.reset_password(acct, pick.login)
        except cr.RegistryError as exc:
            st.error(str(exc))
            return
        st.success(f"已將「{pick.login}」重設為 0000，該帳號下次登入後請同仁自行更改。")
    st.dataframe(pd.DataFrame([{"帳號": a.login, "角色": cr.ROLE_LABELS[a.role], "所屬大隊": a.battalion,
                                "仍是預設密碼": "是" if a.must_change else ""} for a in accounts]),
                 use_container_width=True, hide_index=True)


def render_case_registry_page(pg=None):
    cfg = get_config()
    st.markdown("### 📮 案件登錄與管制")
    if cfg is None:
        st.info("案件登錄系統尚未啟用。")
        return
    try:
        reg = get_registry(cfg)
        book = get_accounts(reg)
        problems = reg.check_layout()
    except cr.StoreError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        st.error(f"無法連線到案件資料：{type(exc).__name__}")
        return

    acct = st.session_state.get("case_user")
    if acct is None:
        _login_box(book)
        return

    top, right = st.columns([5, 1])
    top.caption(f"登入：{acct.label}（{cr.ROLE_LABELS[acct.role]}"
                f"{'｜' + acct.battalion if acct.battalion else ''}{'｜' + acct.unit if acct.unit else ''}）")
    if right.button("登出"):
        for k in ("case_user", "case_handoff", "case_nav"):
            st.session_state.pop(k, None)
        st.rerun()
    if problems:
        st.error("試算表欄位與系統預期不一致，為避免寫錯欄，已停止寫入：\n\n- " + "\n- ".join(problems[:8]))
        return
    if getattr(reg, "log_failed", False):
        st.warning("異動紀錄寫入失敗，請通知管理者。")
    _flash()
    if acct.must_change:
        st.warning("您還在使用預設密碼 0000，請到「🔑 更改密碼」更新。")

    pages = ["📋 案件總表"]
    if acct.role in (cr.ROLE_UNIT, cr.ROLE_BATTALION):
        pages.append("➕ 登錄新案件")
    pages.append("✍️ 處理案件")
    if acct.role == cr.ROLE_SECTION:
        pages.append("🧾 異動紀錄")
    if acct.is_admin:
        pages.append("🔧 帳號管理")
    pages.append("🔑 更改密碼")
    if st.session_state.get("case_nav") not in pages:
        st.session_state["case_nav"] = pages[0]
    nav = st.radio("案件系統", pages, horizontal=True, label_visibility="collapsed", key="case_nav")
    if nav == "📋 案件總表":
        _page_list(reg, acct)
    elif nav == "➕ 登錄新案件":
        _page_new(reg, acct, pg)
    elif nav == "✍️ 處理案件":
        _page_handle(reg, acct)
    elif nav == "🧾 異動紀錄":
        _page_log(reg)
    elif nav == "🔧 帳號管理":
        _page_accounts(book, acct)
    else:
        _page_password(book, acct)
