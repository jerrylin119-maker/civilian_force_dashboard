"""科內維護模式的密碼。

只接受 Streamlit Secrets 的 admin_password。沒有設定時不使用任何寫死的密碼，
維護模式直接停用。
"""

MAINTENANCE_DISABLED_MESSAGE = (
    "尚未設定管理密碼，維護模式已停用。請在 Streamlit Secrets 設定 admin_password 後，重新整理再登入。"
)


def maintenance_passwords(secret_value):
    """有效的維護密碼。secret 沒設或是空白時回傳空集合。"""
    text = "" if secret_value is None else str(secret_value).strip()
    if not text:
        return set()
    return {text}
