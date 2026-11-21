"""Gọi tác vụ đối soát qua HTTP, dùng được local và từ scheduler bên ngoài Render.

python reconcile_payments.py --url http://127.0.0.1:5000 --loop
python reconcile_payments.py --url https://your-app.onrender.com

Lấy PAYMENT_RECONCILE_SECRET từ .env/môi trường. Không đưa secret vào tham số dòng lệnh.
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import mailer  # nạp .env cùng cơ chế với app, không gửi mail
from xapi_client import NoRedirect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='URL gốc của QuickOrder, không phải URL xAPI')
    parser.add_argument('--loop', action='store_true', help='Lặp 5 giây; dừng bằng Ctrl+C')
    args = parser.parse_args()
    parts = urlsplit(args.url)
    if (parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('', '/')
            or not parts.hostname or (parts.scheme != 'https' and not (parts.scheme == 'http' and parts.hostname in ('127.0.0.1', 'localhost')))):
        parser.error('URL phải là HTTPS hoặc localhost HTTP, chỉ gồm URL gốc ứng dụng.')
    secret = os.environ.get('PAYMENT_RECONCILE_SECRET', '')
    if len(secret) < 32:
        parser.error('Cần PAYMENT_RECONCILE_SECRET ít nhất 32 ký tự trong .env/môi trường.')
    request = urllib.request.Request(args.url.rstrip('/') + '/api/internal/payments/reconcile', data=b'{}',
                                    headers={'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'}, method='POST')
    result = 0
    try:
        while True:
            try:
                with urllib.request.build_opener(NoRedirect).open(request, timeout=60) as response:
                    data = json.load(response)
                print('Đối soát xong. Đơn mới:', data['created_orders'], '| Quán lỗi:', data['failed_shops'], flush=True)
                result = 0
            except (OSError, ValueError, KeyError, urllib.error.URLError):
                print('Chưa đối soát được. Kiểm tra server, secret và kết nối xAPI; không đánh dấu đã thanh toán.', flush=True)
                result = 1
            if not args.loop:
                return result
            time.sleep(5)
    except KeyboardInterrupt:
        print('Đã dừng tác vụ đối soát.')
        return result


if __name__ == '__main__':
    raise SystemExit(main())
