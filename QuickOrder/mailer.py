"""Gửi email mã xác nhận đăng ký khách hàng qua API của Brevo (gói miễn phí, không cần SMTP).

Biến môi trường:
    MAIL_API_KEY     khóa API của Brevo (bắt buộc khi chạy thật)
    MAIL_FROM        địa chỉ người gửi đã xác minh trên Brevo (bắt buộc khi chạy thật)
    MAIL_FROM_NAME   tên người gửi (tùy chọn, mặc định QuickOrder)
    MAIL_CONSOLE     đặt "1" để chỉ in mã ra terminal, không gửi thư (dùng khi thử trên máy)

Mã xác nhận không bao giờ được ghi vào log. Khi gửi lỗi, lý do từ Brevo (mã lỗi và thông báo) được ghi vào log máy chủ.
"""
import json
import logging
import os
import urllib.error
import urllib.request

API_URL = "https://api.brevo.com/v3/smtp/email"
API_KEY = os.environ.get("MAIL_API_KEY", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "")
MAIL_FROM_NAME = os.environ.get("MAIL_FROM_NAME", "QuickOrder")
CONSOLE = os.environ.get("MAIL_CONSOLE") == "1"

log = logging.getLogger("mailer")
SEND_FAILED = "Không gửi được email xác nhận. Vui lòng thử lại sau ít phút."


class MailError(Exception):
    """Không gửi được email. Thông báo này được hiển thị cho người dùng."""


def _brevo_reason(e):
    """Mã và thông báo lỗi Brevo trả về, dùng để ghi log. Không chứa nội dung thư."""
    try:
        data = json.loads(e.read().decode("utf-8", "replace"))
        return f"{data.get('code', '')}: {data.get('message', '')}"[:300]
    except Exception:
        return "(không đọc được nội dung lỗi)"


def send_code(to, code):
    if CONSOLE:
        print(f"[MAIL_CONSOLE] Mã xác nhận gửi tới {to}: {code}", flush=True)
        return
    if not API_KEY or not MAIL_FROM:
        log.error("Thiếu MAIL_API_KEY hoặc MAIL_FROM trên máy chủ, chưa gửi được mã xác nhận.")
        raise MailError("Hệ thống chưa cấu hình gửi email. Vui lòng báo quản trị viên.")
    payload = {
        "sender": {"name": MAIL_FROM_NAME, "email": MAIL_FROM},
        "to": [{"email": to}],
        "subject": f"{code} là mã xác nhận QuickOrder",
        "textContent": (
            f"Mã xác nhận đăng ký tài khoản QuickOrder của bạn là: {code}\n\n"
            "Mã có hiệu lực trong 10 phút. Nếu bạn không yêu cầu đăng ký, hãy bỏ qua email này."
        ),
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"api-key": API_KEY, "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
    except urllib.error.HTTPError as e:
        # Brevo từ chối: thường là khóa API sai, hoặc email người gửi chưa được xác minh
        log.error("Brevo từ chối gửi thư (HTTP %s): %s", e.code, _brevo_reason(e))
        raise MailError(SEND_FAILED) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log.error("Không kết nối được tới Brevo: %s", e)
        raise MailError(SEND_FAILED) from e
