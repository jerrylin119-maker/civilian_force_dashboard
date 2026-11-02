"""義消福利互助及團體保險申請流程(給大隊、分隊承辦人)。

用法:在看板的福利互助頁面 import 之後呼叫一次。

    from welfare_guide import render_welfare_guide
    render_welfare_guide()

只依賴 streamlit(>=1.38),不讀取任何檔案或資料庫。內容依「本縣義勇消防人員福利互助及
團體保險申請注意事項」整理,草稿 v0.2。表單連結都是雲端硬碟的實際檔案,需要有權限的
帳號才能開啟。
"""
from __future__ import annotations

import datetime as dt

import streamlit as st

_P = "wg_"  # session_state key 前綴,避免和看板其他元件衝突


def _file(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view"


def _dir(folder_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{folder_id}"


# ---------------------------------------------------------------- 連結
L = {
    "app1": _file("1SH9BoHJoa6_b0qA9CC9zRasBmQLhCF_j"),
    "receipt": _file("1yj1IRnzg07YsQIxaRooAIkdN-FspThjX"),
    "proxy": _file("1QIasbZ27M_VNC4BTmMJy2SVad2eWxyDM"),
    "quit2": _file("1yiMYsLkPItfvxqEVMu0h20itqqDdwwxZ"),
    "quit3": _file("1cb49ciYAwzsK2-NLc0syuFNzzPQduJbr"),
    "fund_form": _file("1tSSWnU4NillRvqb9a1ItIx4w73QdDqjY"),
    "report": _file("163S5jGbLT2BOrU_kL3PwefVtf4kSEd9i"),
    "notice": _file("1w0bkj3RDeOQ50s4q55ASh8SFpYZCqG0K"),
    "slides": _file("1lEz790lFjnYSHidtqFH8i_88RpTOHkNV"),
    "law": _file("1R7VoCFHxlpjdncqcHBq1z2mcGYwZhsNL"),
    "ctrl": "https://reurl.cc/mp1ed9",
}

# 義消類別:新光人壽適用到 cut(含),之後用國泰人壽
CATS = {
    "救災義消": {
        "cut": dt.date(2026, 4, 26), "cut_text": "115 年 4 月 26 日", "cathay_from": "115 年 4 月 27 日",
        "sino": _dir("1b9YMn1bgdWJ-wbsz6FVpYMXFWV2aysGC"), "cathay": _dir("1ITPAQBIKRyIx6KYatentonFpZGC8ooB0"),
    },
    "防宣義消": {
        "cut": dt.date(2026, 6, 5), "cut_text": "115 年 6 月 5 日", "cathay_from": "115 年 6 月 6 日",
        "sino": _dir("1H0nKagbPQyXDKfZoYVSat9ngAqFcWPas"), "cathay": _dir("12k7GzcN73WsOr4DSxlR04rTH2dD-Kywf"),
    },
    "救護義消": {
        "cut": dt.date(2026, 8, 3), "cut_text": "115 年 8 月 3 日", "cathay_from": "115 年 8 月 4 日",
        "sino": _dir("1FFfvtd8wf4WBIPU2FnnGNI0tgA29p_TN"), "cathay": _dir("1rRelHC72EbfgnJcebN5ZuFQ5Y6ggIkCf"),
    },
}

INDEX_ROWS = [
    ("申請注意事項(原檔)", [("PDF", L["notice"]), ("簡報版", L["slides"])]),
    ("福利互助辦法(113.11.12 修正)", [("開啟", L["law"])]),
    ("福利互助申請表格資料夾", [("開啟", _dir("1UVrHgdpvvLiOVu94hlAi2pjRwDRQKk3n"))]),
    ("義消保險表單資料夾", [("開啟", _dir("1IYjdEqJ8Igb91YLlsC1t8kgRPLO3IA6S"))]),
    ("消防發展基金會表格資料夾", [("開啟", _dir("1KGR-ZXtUw8EvxPyl5W1tH8T71cyIYdyj"))]),
    ("福利互助申請及切結書(附件一)", [("開啟", L["app1"])]),
    ("福利互助金收據(表一)", [("開啟", L["receipt"])]),
    ("遺族領款委託書(表二)", [("開啟", L["proxy"])]),
    ("退隊證明書(附件二)", [("開啟", L["quit2"])]),
    ("義消自願退隊證明書(附件三)", [("開啟", L["quit3"])]),
    ("慰問金給付申請表(基金會)", [("開啟", L["fund_form"])]),
    ("災害事件調查報告書樣本(基金會)", [("開啟", L["report"])]),
    ("管制表", [("開啟", L["ctrl"])]),
    ("國泰人壽表單", [(n, c["cathay"]) for n, c in CATS.items()]),
    ("新光人壽表單", [(n, c["sino"]) for n, c in CATS.items()]),
]

BASE_INS = ["診斷證明書(正本)", "收據(正本)", "存摺(影本)", "受益人身分證正反面(影本)"]
DEATH_INS = {
    "cathay": [
        "國泰團險理賠申請書", "死亡證明書或相驗屍體證明書(正本)", "法定繼承人聲明暨同意書",
        "除戶戶籍謄本(正本)", "全戶戶籍謄本(原始手抄本,正本)", "存摺(影本)",
        "受益人身分證正反面(影本)", "意外身故:事故三聯單",
    ],
    "sino": [
        "新光團險理賠申請書", "死亡證明書或相驗屍體證明書(正本)", "推派具領同意書", "繼承系統表",
        "除戶戶籍謄本(正本)", "全戶戶籍謄本(原始手抄本,正本)", "存摺(影本)",
        "受益人身分證正反面(影本)", "意外身故:事故三聯單",
    ],
}
COMPANY_NAME = {"cathay": "國泰人壽", "sino": "新光人壽"}

# 保險公司表單檔案(各義消類別資料夾裡的同名複本),依 (義消類別, 公司) 取。
# claim=理賠申請書、heir=法定繼承人聲明暨同意書、proxy=推派具領同意書、tree=繼承系統表
FORMS = {
    ("救災義消", "cathay"): {"claim": "1jjT4AAp9aphEUC8XVRNBqva7caIw_eoy", "heir": "1-KukwQYcejFmTUFKN4CPBlddjm9YdWUJ"},
    ("救災義消", "sino"): {
        "claim": "16xLH5R2MB7cHobBrI-MjlSRm_Apjxrgb", "proxy": "1Q_7qmRw3cgnG1E4ELWWOQ-1h3cIdje21",
        "tree": "1ndrZPFToM26pfO0pdu8UOal5VA6pcwkh",
    },
    ("防宣義消", "cathay"): {"claim": "1cpqaCzkeD7SzzoXEzvRittWMpTiIb9bU", "heir": "1aBcOU5Td3IGzSe_pBgOR7AZl4zDSH02m"},
    ("防宣義消", "sino"): {
        "claim": "15Cd5LHhBmVyRrCvTwUb8xIU-Dzk2seac", "proxy": "14OsE3TxpYgwRwNzcfx30gfpzE9psIfeF",
        "tree": "1KmSU1hoylRKW0S7VYJ-FUwd4wSrEUVpZ",
    },
    ("救護義消", "cathay"): {"claim": "1pNG_x46eHefHIqprSdWwVHcwwp04VJMl", "heir": "1Z9aj2OspswYDe4Kgc582Uwq_hbHU7Q4a"},
    ("救護義消", "sino"): {
        "claim": "1gfZBIWsJjVHCbOV6gdg1TQNiD2Hi6eK0", "proxy": "1t3dRgAUijbFkyAGNjYNOwUsnHwm8uZN4",
        "tree": "1mWLP4bL2P3Po_cf1cv10Gz7pJvpxdzhm",
    },
}
# 喪葬團保清單裡,有表單檔案可以直接開啟的項目
FORM_KEY = {
    "國泰團險理賠申請書": "claim", "法定繼承人聲明暨同意書": "heir",
    "新光團險理賠申請書": "claim", "推派具領同意書": "proxy", "繼承系統表": "tree",
}


def _form_item(text: str, cat: str | None, company: str | None, kind: str):
    """文件項目:有對應表單檔案就回傳 (文字, 連結),沒有就回傳純文字。"""
    fid = FORMS.get((cat, company), {}).get(kind)
    return (text, _file(fid)) if fid else text

# 文件項目:字串,或 (文字, 連結)
CASES = {
    "住院醫療(重大傷病)": {
        "ins": True, "fund": False, "fund_note": "", "notes": [],
        "ben_docs": ["診斷證明書"], "ins_kind": "base", "fund_docs": [],
    },
    "失能": {
        "ins": False, "fund": False, "fund_note": "基金會的失能補助另依補助要點辦理,注意事項沒有列出。", "notes": [],
        "ben_docs": ["身心障礙證明書", "身心障礙手冊"], "ins_kind": None, "fund_docs": [],
    },
    "喪葬": {
        "ins": True, "fund": True, "fund_note": "", "notes": ["喪葬為自殺的,不予補助。"],
        "ben_docs": ["死亡診斷書", "除戶戶籍謄本(影本)", ("遺族領款委託書(表二),互助人身故須附", L["proxy"])],
        "ins_kind": "death",
        "fund_docs": [
            ("慰問金給付申請表", L["fund_form"]),
            "檢附文件表:黏貼服務證、申請人身分證正反面、存摺(皆影本)",
            "死亡診斷書(正本)", "除戶戶籍謄本(除戶全部,正本)",
        ],
    },
    "退隊": {
        "ins": False, "fund": False, "fund_note": "",
        "notes": ["勒令退隊的,不予受理。", "自願退隊並放棄退隊互助金的,改用義消自願退隊證明書(附件三),不申請互助金。"],
        "ben_docs": ["服務證(正本)", ("退隊證明書(附件二,申請福利互助金用)(正本)", L["quit2"])],
        "ins_kind": None, "fund_docs": [],
    },
    "因公受傷(執行任務受傷)": {
        "ins": True, "fund": True, "fund_note": "",
        "notes": [
            "基金會規定:因公受傷要在受傷後 24 小時內就醫。",
            "申請因公殉職、死亡、全失能、半失能時,基金會還要附災害事件專案調查報告。",
        ],
        "ben_docs": [
            "診斷證明書", "協勤簽到退紀錄、派遣令、出勤工作紀錄",
            "搜救報告或救護紀錄表等其他出勤證明(確切項目請對照注意事項原檔)",
        ],
        "ins_kind": "base",
        "fund_docs": [
            ("慰問金給付申請表", L["fund_form"]),
            "檢附文件表:黏貼服務證、申請人身分證正反面、存摺(皆影本)",
            "協勤簽到退紀錄、派遣令、出勤工作紀錄等", "診斷證明書(正本)",
        ],
    },
}


# ---------------------------------------------------------------- 元件
def _doc_group(title: str, items: list, key: str) -> None:
    st.markdown(f"**{title}**")
    for i, item in enumerate(items):
        text, url = (item, None) if isinstance(item, str) else item
        c1, c2 = st.columns([1, 14])
        with c1:
            st.checkbox(text, key=f"{_P}chk_{key}_{i}", label_visibility="collapsed")
        with c2:
            st.markdown(f"[{text}]({url})" if url else text)


def _insurer(cat: str | None, ev: dt.date | None):
    """回傳 (狀態, 公司代碼或 None)。狀態:need_cat、need_date、ok。"""
    if not cat:
        return "need_cat", None
    if not ev:
        return "need_date", None
    return "ok", ("sino" if ev <= CATS[cat]["cut"] else "cathay")


def _links(pairs) -> str:
    return "、".join(f"[{t}]({u})" for t, u in pairs)


def render_welfare_guide() -> None:
    st.markdown("#### 義消福利互助及團體保險申請流程")
    st.caption(
        "給大隊、分隊承辦人。草稿 v0.2,尚未經承辦人審閱,依「本縣義勇消防人員福利互助及團體保險申請"
        "注意事項」整理,最後以原檔為準。福利互助與團體保險合在同一個流程,需要時再加基金會慰問金。"
    )

    # ---- 步驟 1
    st.markdown("##### 步驟 1:確認可不可以申請")
    st.markdown(
        "- 只供義勇消防人員申請本縣福利互助與團體保險。\n"
        "- 事件限義消本人發生事故後才能提出申請。義消身故時,由受益人(遺族)辦理。\n"
        "- 喪葬為自殺的,不予補助。勒令退隊的,不予受理。\n"
        "- 福利互助的住院醫療,限重大傷病住院。"
    )
    st.caption(
        "時效:福利互助金要在事實發生次日起 6 個月內申請(住院自出院次日起算)。基金會慰問金與團體保險的"
        "時效,資料不一致或沒寫,見最下方待確認事項。"
    )

    # ---- 步驟 2
    st.markdown("##### 步驟 2:選申請項目,看這一件要申請哪幾種")
    case_name = st.radio("事故情形", list(CASES), index=None, horizontal=True, key=f"{_P}case")
    cat = st.radio("義消類別(團體保險才需要)", list(CATS), index=None, horizontal=True, key=f"{_P}cat")
    ev_known = st.checkbox("我知道事件發生日(團體保險用來判斷保險公司)", key=f"{_P}ev_known")
    ev = st.date_input("事件發生日", value=dt.date.today(), key=f"{_P}date") if ev_known else None

    company = None
    use_ben = use_ins = use_fund = False
    k = CASES.get(case_name) if case_name else None

    if not k:
        st.info("先選事故情形,這裡會列出這一件要申請哪幾種、保險公司與會辦單位。")
    else:
        st.markdown(
            f"福利互助:**可申請**　團體保險:**{'可申請' if k['ins'] else '不適用'}**　"
            f"基金會慰問金:**{'可申請' if k['fund'] else ('另依補助要點' if k['fund_note'] else '無')}**"
        )
        st.markdown("**這一件要申請:**")
        use_ben = st.checkbox("福利互助", value=True, key=f"{_P}use_ben_{case_name}")
        if k["ins"]:
            use_ins = st.checkbox("團體保險", value=True, key=f"{_P}use_ins_{case_name}")
        if k["fund"]:
            use_fund = st.checkbox("基金會慰問金", value=True, key=f"{_P}use_fund_{case_name}")
        if k["fund_note"]:
            st.info(k["fund_note"])
        for n in k["notes"]:
            st.warning(n)

        if use_ins:
            status, company = _insurer(cat, ev)
            if status == "need_cat":
                st.warning("團體保險要用哪一家的表單,取決於義消類別與事件發生日,請在上面選義消類別與事件發生日。")
            elif status == "need_date":
                c = CATS[cat]
                st.info(
                    f"{cat}的事件發生在 {c['cut_text']}(含)以前用新光人壽,在 {c['cathay_from']} 00 時以後用國泰人壽。"
                    "請再選事件發生日。"
                )
            else:
                c = CATS[cat]
                folder = c[company]
                st.success(f"團體保險用 {COMPANY_NAME[company]}。{cat},事件發生日 {ev.isoformat()}。")
                st.markdown(f"[開啟 {cat} {COMPANY_NAME[company]} 表單資料夾]({folder})")

        st.markdown("**陳報單要會辦**")
        if use_ben and use_ins and use_fund:
            st.write("民力運用及訓練科、綜合企劃及安全衛生科、會計室、政風室")
        elif use_ben and use_ins:
            st.write("民力運用及訓練科、綜合企劃及安全衛生科、會計室")
        elif use_ins and not use_ben and not use_fund:
            st.write("民力運用及訓練科")
        else:
            st.caption("注意事項只列了三種組合(福利互助加團保、只申請團保、福利互助加團保加基金會)。"
                       "你選的這個組合沒有列,會辦單位待確認。")

    # ---- 步驟 3
    st.markdown("##### 步驟 3:備齊文件")
    if not k:
        st.info("先在步驟 2 選事故情形,這裡會列出對應的文件清單,可以逐項打勾。")
    else:
        slug = case_name
        if use_ben:
            _doc_group(
                "福利互助:每一項都要附",
                [("福利互助申請及切結書(附件一)", L["app1"]), ("領取福利互助金收據(表一)", L["receipt"]),
                 "郵局或其他金融機構存摺(影本)", "受益人身分證正反面(影本)"],
                f"{slug}_ben_common",
            )
            _doc_group(f"福利互助:{case_name}另附", k["ben_docs"], f"{slug}_ben")
        if k["ins"] and use_ins:
            title = "團體保險" + (f"({COMPANY_NAME[company]})" if company else "")
            if k["ins_kind"] == "death":
                if company:
                    docs = DEATH_INS[company]
                    items = [_form_item(d, cat, company, FORM_KEY[d]) if d in FORM_KEY else d for d in docs]
                    _doc_group(f"{title}:共 {len(docs)} 項" + (",須全部備齊" if company == "cathay" else ""),
                               items, f"{slug}_ins_{company}")
                else:
                    st.markdown("**團體保險(喪葬)**")
                    st.caption("保險公司還沒確定,國泰人壽共 8 項,新光人壽共 9 項。選好義消類別與事件發生日,這裡會顯示對應的清單。")
                    st.markdown("申請書:" + _links(
                        [(f"{COMPANY_NAME[c]}團險理賠申請書", _file(FORMS[(cat or "救災義消", c)]["claim"])) for c in COMPANY_NAME]
                    ))
            else:
                if company:
                    claims = [_form_item(f"{COMPANY_NAME[company]}團險理賠申請書", cat, company, "claim")]
                else:
                    # 還不知道是哪一家:兩家的申請書都先列出來,選好義消類別與事件發生日後只剩對應的一家
                    claims = [_form_item(f"{COMPANY_NAME[c]}團險理賠申請書(用哪一家依義消類別與事件發生日判斷,見步驟 2)",
                                         cat or "救災義消", c, "claim") for c in COMPANY_NAME]
                _doc_group(title, claims + BASE_INS, f"{slug}_ins_{company or 'x'}")
        if k["fund"] and use_fund:
            _doc_group("基金會慰問金", k["fund_docs"], f"{slug}_fund")
            if case_name.startswith("因公受傷"):
                st.markdown(f"[災害事件調查報告書樣本]({L['report']})")
        if case_name == "退隊":
            st.markdown(f"[義消自願退隊證明書(附件三)]({L['quit3']})")
        if case_name.startswith("因公受傷"):
            st.markdown(f"[對照注意事項原檔]({L['notice']})")

    # ---- 步驟 4 到 7
    st.markdown("##### 步驟 4:影印與整理")
    st.markdown(
        "- 診斷證明書、存摺影本、身分證影本這類重複文件,依項目各印一份、分開檢附。福利互助、團體保險、"
        "基金會三種各附一份。\n"
        "- 不要合併成一份,也不要漏印,後面的審查與撥款才不會被退回。\n"
        "- 標「正本」的文件,不能用影本代替。"
    )
    st.markdown("##### 步驟 5:填管制表")
    st.markdown(f"每一件申請,都要到「115 年各大隊辦理福利互助及保險申請」管制表填寫。[開啟管制表]({L['ctrl']})")
    st.markdown("##### 步驟 6:寫陳報單、會辦")
    st.markdown("- 陳報單寫兩件事:簡述申請的義消人員,以及事件日期。\n- 會辦單位依步驟 2 的結果決定,也可以看下表。")
    st.table(
        {
            "這一件申請的種類": ["福利互助加團體保險", "只申請團體保險", "福利互助、團體保險加消防發展基金會"],
            "陳報單要會辦": [
                "民力運用及訓練科、綜合企劃及安全衛生科、會計室",
                "民力運用及訓練科",
                "民力運用及訓練科、綜合企劃及安全衛生科、會計室、政風室",
            ],
        }
    )
    st.markdown("##### 步驟 7:送件前檢核")
    for i, t in enumerate([
        "申請項目與要申請的種類(福利互助、團體保險、基金會)已確認",
        "該項目的文件已依步驟 3 備齊,正本與影本沒有搞錯",
        "重複文件各種申請各印一份,分開附",
        "管制表已填",
        "陳報單已寫,會辦單位正確",
        "團體保險依義消類別與事件日期,用對保險公司的表單",
    ]):
        st.checkbox(t, key=f"{_P}final_{i}")
    st.caption("送件後民力科怎麼審查、簽核、撥款,資料中沒有說明,待承辦人補充。")

    # ---- 索引與待確認
    with st.expander("表單與原始文件索引"):
        for name, pairs in INDEX_ROWS:
            st.markdown(f"- {name}:{_links(pairs)}")
    with st.expander("待確認事項"):
        st.markdown(
            "1. 團體保險的申請時效是多久。基金會慰問金的時效,新版要點寫 6 個月,舊版一覽表寫 3 個月,以哪個為準。\n"
            "2. 因公受傷的福利互助文件,注意事項原檔轉成文字時有一段內容不完整,需要對照原檔補正。\n"
            "3. 三個義消類別資料夾裡的保險表單檔案大小相同,可能是同一份表單的重複複本。\n"
            "4. 送件後民力科的審查、簽核、撥款流程,以及送件的窗口與方式。\n"
            "5. 失能的基金會補助與慰問,注意事項沒有列出,需要時另行查詢基金會補助要點。"
        )
