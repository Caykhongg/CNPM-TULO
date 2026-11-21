"""Thông tin kết nối ngân hàng riêng của quán. URL chứa token chỉ giải mã ở server."""
import base64
import hashlib
import json
import os
import re
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
import xapi_client

CATALOG = json.loads(Path(__file__).with_name('bank_catalog.json').read_text(encoding='utf-8'))['banks']
BY_BIN = {b['bin']: b for b in CATALOG}
# Chỉ đưa vào đường dẫn đã có trong tài liệu xapi.vn. Các ngân hàng/phiên bản khác dùng URL do xAPI cấp.
ENDPOINTS = {'970423': '/historyapitpbv2/{token}', '970416': '/historyapiacb/{token}'}


def recipient(data):
    bank = str(data.get('bank_bin') or '').strip()
    account = str(data.get('account_number') or '').strip()
    name = str(data.get('account_name') or '').strip()
    if bank not in BY_BIN or not re.fullmatch(r'[A-Za-z0-9]{6,19}', account) or not 2 <= len(name) <= 100:
        raise xapi_client.PaymentError('Hãy chọn ngân hàng, nhập số tài khoản 6–19 chữ/số và tên chủ tài khoản.')
    return dict(bank_bin=bank, account_number=account, account_name=name)


def cipher():
    raw = os.environ.get('PAYMENT_ENCRYPTION_KEY', '')
    if raw:
        try:
            return Fernet(raw.encode())
        except (ValueError, TypeError):
            raise xapi_client.PaymentError('PAYMENT_ENCRYPTION_KEY trên server chưa hợp lệ. Vui lòng báo quản trị.') from None
    secret = os.environ.get('SECRET_KEY', '')
    if len(secret) < 32:
        raise xapi_client.PaymentError('Server cần SECRET_KEY cố định ít nhất 32 ký tự để lưu token ngân hàng an toàn. Vui lòng báo quản trị.')
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b'quickorder-bank-v1:' + secret.encode()).digest()))


def encode_url(url):
    return cipher().encrypt(url.encode()).decode()


def decode_url(value):
    try:
        return cipher().decrypt(value.encode()).decode()
    except (InvalidToken, UnicodeError):
        raise xapi_client.PaymentError('Không đọc được token đã lưu. Kiểm tra khóa mã hóa server hoặc kết nối lại ngân hàng.') from None


def from_input(value, bank):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 2000:
        raise xapi_client.PaymentError('Nhập token hoặc URL API lịch sử giao dịch do xAPI cấp.')
    value = value.strip()
    if value.startswith('https://'):
        url = value
    else:
        if not re.fullmatch(r'[A-Za-z0-9._~-]+', value):
            raise xapi_client.PaymentError('Token không hợp lệ. Có thể dán nguyên URL API lịch sử do xAPI cấp.')
        endpoints = dict(ENDPOINTS)
        try:
            extra = json.loads(os.environ.get('XAPI_ENDPOINTS_JSON', '{}'))
            if isinstance(extra, dict):
                endpoints.update(extra)
        except ValueError:
            pass
        template = endpoints.get(bank)
        if not isinstance(template, str) or template.count('{token}') != 1:
            raise xapi_client.PaymentError('Ngân hàng này chưa có mẫu API mặc định. Hãy dán nguyên URL API lịch sử xAPI cấp vào ô token.')
        url = 'https://id.xapi.vn' + template.replace('{token}', value)
    xapi_client.validate_url(url)
    return url


def stored_config(row):
    url = decode_url(row['credentials_enc'])
    xapi_client.validate_url(url)
    return {'history_url': url, 'bank_bin': row['bank_bin'], 'account_number': row['account_number'],
            'connection_id': row['id'], 'mode': 'AUTO'}


def current_config(c, shop):
    settings = c.execute('SELECT * FROM shop_payment_settings WHERE shop_id=?', (shop['id'],)).fetchone()
    if settings:
        if settings['mode'] == 'MANUAL':
            return {'mode': 'MANUAL', 'connection_id': None}
        row = c.execute('SELECT * FROM payment_connections WHERE id=? AND shop_id=?',
                        (settings['connection_id'], shop['id'])).fetchone()
        if not row or row['bank_bin'] != shop['bank_bin'] or row['account_number'] != shop['bank_account_number']:
            raise xapi_client.PaymentError('Thông tin ngân hàng đã thay đổi. Hãy lưu lại kết nối thanh toán của quán.')
        return stored_config(row)
    # Tương thích cấu hình .env của bản cũ; sau khi chủ quán lưu trên web thì không dùng biến này nữa.
    if os.environ.get(f"XAPI_SHOP_{shop['id']}", '').strip():
        return {**xapi_client.config_for(shop), 'mode': 'AUTO', 'connection_id': None}
    return {'mode': 'MANUAL', 'connection_id': None}
