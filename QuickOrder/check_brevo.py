"""Kiểm tra cấu hình; thêm --to email-cua-ban để gửi một email thử, không tạo tài khoản."""
import argparse
import logging
import secrets

import mailer


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to", help="Email của bạn để nhận một email thử kết nối Brevo")
    args = parser.parse_args(argv)
    config = mailer.settings()
    print("API key:", "ĐÃ CẤU HÌNH" if config["api_key"] else "CHƯA CẤU HÌNH")
    print("Email người gửi:", config["sender"] or "CHƯA CẤU HÌNH")
    print("MAIL_CONSOLE:", "1 - CHỈ IN MÃ, KHÔNG GỬI EMAIL" if config["console"] else "0 - gửi qua Brevo")
    if config["console"]:
        print("Đặt MAIL_CONSOLE=0 để kiểm tra gửi email thật.")
        return 2
    try:
        mailer.validate_settings(config)
    except mailer.MailError as error:
        print("LỖI:", error.diagnostic, "-", str(error))
        return 2
    if not args.to:
        print('Cấu hình local hợp lệ. Để thử khóa/sender thực tế, chạy: python check_brevo.py --to "email-cua-ban"')
        print("Chưa gọi Brevo và chưa gửi thư trong lần kiểm tra này.")
        return 0
    try:
        message_id = mailer.send_code(args.to, f"{secrets.randbelow(10**6):06d}")
    except mailer.MailError as error:
        print("LỖI:", error.diagnostic, "-", str(error))
        print("Xem dòng log Brevo phía trên để xác định API key, quyền, IP hoặc sender bị từ chối.")
        return 1
    print("OK: Brevo đã tiếp nhận email thử.")
    if message_id:
        print("messageId:", message_id)
    print("Kiểm tra hộp thư, Spam và Brevo Transactional Logs.")
    print("Email này chỉ thử kết nối, không tạo tài khoản và mã của nó không dùng để xác minh trên website.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
