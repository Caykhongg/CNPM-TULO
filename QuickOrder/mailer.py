"""Gửi email mã xác nhận đăng ký khách hàng qua API của Brevo (gói miễn phí, không cần SMTP).

Biến môi trường:
    MAIL_API_KEY     khóa API của Brevo (bắt buộc khi chạy thật)
    MAIL_FROM        địa chỉ người gửi đã xác minh trên Brevo (bắt buộc khi chạy thật)
    MAIL_FROM_NAME   tên người gửi (tùy chọn, mặc định QuickOrder)
    MAIL_CONSOLE     đặt "1" để chỉ in mã ra terminal, không gửi thư (dùng khi thử trên máy)

Mã xác nhận không bao giờ được ghi vào log khi MAIL_CONSOLE không bật.
"""
import json
import os
import urllib.error
import urllib.request

API_URL = "https://api.brevo.com/v3/smtp/email"
API_KEY = os.environ.get("MAIL_API_KEY", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "")
MAIL_FROM_NAME = os.environ.get("MAIL_FROM_NAME", "QuickOrder")
CONSOLE = os.environ.get("MAIL_CONSOLE") == "1"


class MailError(Exception):
    """Không gửi được email. Thông báo này được hiển thị cho người dùng."""


def send_code(to, code):
    if CONSOLE:
        print(f"[MAIL_CONSOLE] Mã xác nhận gửi tới {to}: {code}", flush=True)
        return
    if not API_KEY or not MAIL_FROM:
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
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise MailError("Không gửi được email xác nhận. Vui lòng thử lại sau ít phút.") from e
