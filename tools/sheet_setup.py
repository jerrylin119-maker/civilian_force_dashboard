"""案件登錄的設定小工具（在自己的電腦執行，金鑰檔不會被送到任何地方）。

  檢查連線與標題（只讀，不改試算表）：
      python tools/sheet_setup.py check  金鑰.json  試算表ID
  寫一筆測試案件（會在試算表多一列，之後自己刪除）：
      python tools/sheet_setup.py write-test  金鑰.json  試算表ID
  產生貼到 Streamlit Secrets 的設定檔（輸出檔含金鑰，勿放進專案資料夾或上傳）：
      python tools/sheet_setup.py secrets  金鑰.json  試算表ID  輸出.toml
  產生帳號密碼雜湊（會提示輸入密碼，輸入時不顯示）：
      python tools/sheet_setup.py hash
"""
import getpass
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import case_registry as cr  # noqa: E402

WORKSHEET = "表單回應 1"


def load_key(path):
    with open(path, encoding="utf-8") as fh:
        info = json.load(fh)
    if info.get("type") != "service_account" or "private_key" not in info:
        sys.exit("這不是服務帳戶的 JSON 金鑰檔。")
    return info


def open_registry(key_path, sheet_id):
    info = load_key(key_path)
    print(f"服務帳戶：{info['client_email']}")
    try:
        store = cr.SheetStore(sheet_id, WORKSHEET, info)
    except cr.StoreError as exc:
        sys.exit(f"連線失敗：{exc}\n請確認：試算表已分享給上面的服務帳戶（編輯者）、已啟用 Google Sheets API、工作表名稱是「{WORKSHEET}」。")
    return cr.CaseRegistry(store)


def cmd_check(key_path, sheet_id):
    reg = open_registry(key_path, sheet_id)
    problems = reg.check_layout()
    if problems:
        print("標題列有問題，系統會拒絕寫入：")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print(f"連線成功，標題列 33 欄全部對得上。目前有 {len(reg.cases())} 件案件。")


def cmd_write_test(key_path, sheet_id):
    reg = open_registry(key_path, sheet_id)
    if reg.check_layout():
        sys.exit("標題列有問題，先執行 check。")
    acct = cr.Account("setup-test", cr.ROLE_UNIT, battalion="成功大隊", unit="測試分隊")
    no = reg.submit(acct, {"battalion": "成功大隊", "unit": "測試分隊", "officer": "測試", "purpose": "活動費",
                           "plan_name": "【測試案件，請刪除】", "date_start": "2026/12/11", "date_end": "2026/12/11",
                           "total": 1000, "applied": 500, "source_kind": "議員", "source_detail": "測試議員"},
                     source="setup 測試")
    back = reg.get(no)
    print(f"已寫入測試案件 {no}（第 {back.row_no} 列）。請到試算表確認：")
    print("  - 該列的所屬大隊、計畫名稱、金額、案件編號（AG 欄）是否在對的欄位")
    print("  - 「異動紀錄」工作表是否多一列")
    print("確認後把這一列和紀錄刪除。")


def cmd_secrets(key_path, sheet_id, out):
    info = load_key(key_path)
    q = json.dumps
    lines = ["[case_registry]", 'backend = "sheet"', f"spreadsheet_id = {q(sheet_id)}",
             f"worksheet = {q(WORKSHEET)}", "", "[case_registry.service_account]"]
    for k, v in info.items():
        lines.append(f"{k} = {q(v, ensure_ascii=False)}")
    lines += ["", "# 帳號請接著加在下面，格式見 docs/案件登錄系統架構.md", ""]
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"已輸出到 {out}。內容含金鑰：只貼進 Streamlit 的 Secrets 設定，之後請刪除這個檔案。")


def cmd_hash():
    pw = getpass.getpass("輸入密碼：")
    if getpass.getpass("再輸入一次：") != pw:
        sys.exit("兩次不一致。")
    print(cr.hash_password(pw))


if __name__ == "__main__":
    args = sys.argv[1:]
    cmds = {"check": (cmd_check, 2), "write-test": (cmd_write_test, 2), "secrets": (cmd_secrets, 3), "hash": (cmd_hash, 0)}
    if not args or args[0] not in cmds or len(args) - 1 != cmds[args[0]][1]:
        sys.exit(__doc__)
    cmds[args[0]][0](*args[1:])
