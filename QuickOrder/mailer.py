"""Gửi OTP qua Brevo HTTPS API; hỗ trợ .env local và biến môi trường trên Render."""
import json
import logging
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

# Biến môi trường của terminal/Render được ưu tiên hơn file .env local.
load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)

API_URL = "https://api.brevo.com/v3/smtp/email"
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
log = logging.getLogger("mailer")
SEND_FAILED = "Không gửi được email xác nhận. Vui lòng thử lại sau ít phút."


class MailError(Exception):
    """Thông báo an toàn cho giao diện; diagnostic dùng để xác định lỗi cấu hình/gửi."""
    def __init__(self, message, diagnostic="MAIL_FAILED"):
        super().__init__(message)
        self.diagnostic = diagnostic


def settings():
    """Đọc cấu hình lúc gửi, không giữ giá trị cũ từ thời điểm import module."""
    def pick(primary, alias="", default=""):
        value = os.environ.get(primary, "").strip()
        return value or (os.environ.get(alias, "").strip() if alias else "") or default

    return {
        "api_key": pick("MAIL_API_KEY", "BREVO_API_KEY"),
        "sender": pick("MAIL_FROM", "BREVO_SENDER_EMAIL"),
        "name": pick("MAIL_FROM_NAME", "BREVO_SENDER_NAME", "QuickOrder"),
        "console": os.environ.get("MAIL_CONSOLE", "0").strip() == "1",
    }


def validate_settings(config):
    if not config["api_key"] or not config["sender"]:
        raise MailError(
            "Hệ thống chưa cấu hình gửi email. Vui lòng báo quản trị viên.",
            "MAIL_NOT_CONFIGURED",
        )
    if not EMAIL_RE.fullmatch(config["sender"]):
        raise MailError("Email người gửi chưa được cấu hình đúng.", "MAIL_FROM_INVALID")
    if any(ch.isspace() for ch in config["api_key"]):
        raise MailError("Cấu hình khóa gửi email không hợp lệ.", "MAIL_KEY_INVALID")


def _brevo_reason(error, config, code):
    try:
        data = json.loads(error.read().decode("utf-8", "replace"))
        detail = f"{data.get('code', '')}: {data.get('message', '')}"
    except (ValueError, AttributeError, OSError):
        detail = "Không đọc được thông báo lỗi của Brevo."
    # Lý do được ghi vào log, nhưng không ghi API key và OTP.
    return detail.replace(config["api_key"], "[API_KEY]").replace(code, "[OTP]")[:500]


def send_code(to, code):
    if not isinstance(to, str) or not EMAIL_RE.fullmatch(to.strip()):
        raise MailError("Email nhận mã không hợp lệ.", "MAIL_TO_INVALID")
    if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code):
        raise MailError("Mã xác nhận phải gồm 6 chữ số.", "MAIL_CODE_INVALID")
    config = settings()
    if config["console"]:
        print(f"[MAIL_CONSOLE] Mã xác nhận gửi tới {to}: {code}", flush=True)
        return None
    try:
        validate_settings(config)
    except MailError as error:
        log.error("Cấu hình gửi thư không hợp lệ [%s]", error.diagnostic)
        raise

    payload = {
        "sender": {"name": config["name"], "email": config["sender"]},
        "to": [{"email": to.strip()}],
        "subject": "Mã xác nhận đăng ký QuickOrder",
        "textContent": (
            f"Mã xác nhận đăng ký tài khoản QuickOrder của bạn là: {code}\n\n"
            "Mã có hiệu lực trong 10 phút. Nếu bạn không yêu cầu đăng ký, hãy bỏ qua email này."
        ),
        "htmlContent": (
            "<html><body><h2>Xác nhận tài khoản QuickOrder</h2>"
            f"<p>Mã xác nhận của bạn: <strong>{code}</strong></p>"
            "<p>Mã có hiệu lực trong 10 phút.</p>"
            "<p>Nếu bạn không yêu cầu đăng ký, hãy bỏ qua email này.</p></body></html>"
        ),
    }
    request = urllib.request.Request(
        API_URL, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"api-key": config["api_key"], "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status = response.getcode()
            body = response.read()
    except urllib.error.HTTPError as error:
        log.error("Brevo HTTP %s: %s", error.code, _brevo_reason(error, config, code))
        raise MailError(SEND_FAILED, f"BREVO_HTTP_{error.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        # Không in request/payload/khóa API ra log khi kết nối lỗi.
        log.error("Không kết nối được tới Brevo (%s).", type(error).__name__)
        raise MailError(SEND_FAILED, "BREVO_CONNECTION_FAILED") from None

    if status != 201:
        log.error("Brevo trả trạng thái không mong đợi: HTTP %s", status)
        raise MailError(SEND_FAILED, "BREVO_UNEXPECTED_RESPONSE")
    try:
        data = json.loads(body)
        message_id = data.get("messageId") if isinstance(data, dict) else None
    except (ValueError, TypeError):
        message_id = None
    # 201: Brevo đã tiếp nhận. Không đồng nghĩa email đã tới hộp thư người nhận.
    return message_id
