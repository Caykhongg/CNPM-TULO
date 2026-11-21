"""Chẩn đoán API lịch sử xAPI, chỉ đọc; không tạo đơn/duyệt thanh toán.

Nhập URL bằng ô ẩn. Báo cáo không chứa token, số tài khoản hay giá trị sao kê.
Chạy: python diagnose_xapi.py
"""
import getpass
import json
import re
import urllib.error
import urllib.request
from urllib.parse import unquote, urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def clean_message(value, token, url):
    if not isinstance(value, str):
        return None
    for secret in (url, token, unquote(token)):
        if secret:
            value = value.replace(secret, '[TOKEN_AN]')
    value = re.sub(r'https?://\S+', '[URL_AN]', value)
    value = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[EMAIL_AN]', value)
    value = re.sub(r'[A-Za-z0-9_-]{16,}', '[CHUOI_DAI_AN]', value)
    value = re.sub(r'\d{6,}', '[SO_AN]', value)
    return value[:240]


def safe_key(value, token):
    value = str(value)
    if token and token in value:
        return '[KEY_AN]'
    return value if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,40}', value) else '[KEY_AN]'


def structure(value, token, depth=0):
    if depth >= 4:
        return type(value).__name__
    if isinstance(value, dict):
        return {safe_key(k, token): structure(v, token, depth + 1) for k, v in list(value.items())[:35]}
    if isinstance(value, list):
        return {'type': 'array', 'count': len(value), 'first_item_fields': structure(value[0], token, depth + 1) if value else None}
    # Không in mã giao dịch, nội dung chuyển khoản hoặc số tiền thật.
    return 'null' if value is None else type(value).__name__


def report(data, url, http_status):
    parts = urlsplit(url)
    token = parts.path.rsplit('/', 1)[-1]
    result = {'http_status': http_status, 'endpoint': 'https://id.xapi.vn' + parts.path.rsplit('/', 1)[0] + '/TOKEN_DA_AN',
              'response_structure': structure(data, token)}
    if isinstance(data, dict):
        status = data.get('status')
        if isinstance(status, bool) or status is None or (isinstance(status, int) and 0 <= status <= 599):
            result['status_value'] = status
        elif isinstance(status, str) and status.lower() in ('success', 'error', 'failed', 'fail', 'ok', 'true', 'false'):
            result['status_value'] = status
        else:
            result['status_value'] = '[KHAC_DINH_DANG]'
        for key in ('msg', 'message', 'error'):
            message = clean_message(data.get(key), token, url)
            if message:
                result['provider_' + key] = message
        code = data.get('codeStatus')
        if isinstance(code, bool) or (type(code) is int and 0 <= code <= 9999):
            result['code_status_value'] = code
        if isinstance(data.get('data'), list):
            directions = {str(row.get('type')) for row in data['data'] if isinstance(row, dict)}
            result['direction_values'] = sorted(value if value in ('IN', 'OUT', 'CREDIT', 'DEBIT', 'CRDT', 'DBIT', '1', '2', '0') else '[TYPE_KHAC]' for value in directions)
        if isinstance(data.get('fallback'), bool):
            result['fallback_value'] = data['fallback']
        if status == 'success' and isinstance(data.get('transactions'), list):
            result['quickorder_parser'] = 'KHOP_MAU_HIEN_TAI'
        elif type(code) is int and code == 200 and isinstance(data.get('data'), list):
            result['quickorder_parser'] = 'ACB_RAW_DATA'
        else:
            result['quickorder_parser'] = 'CHUA_KHOP_MAU_HIEN_TAI'
    return result


def main():
    print('Chỉ đọc API lịch sử xAPI; không tạo đơn và không xác nhận thanh toán.')
    print('Dán URL API đầy đủ rồi nhấn Enter. Nội dung nhập sẽ không hiện trên màn hình.')
    url = getpass.getpass('URL xAPI: ').strip()
    try:
        parts = urlsplit(url)
        if (parts.scheme != 'https' or parts.netloc != 'id.xapi.vn' or parts.query or parts.fragment
                or not re.fullmatch(r'/historyapi[A-Za-z0-9]+/[A-Za-z0-9._~-]+', parts.path)):
            print('URL chưa đúng dạng API lịch sử được hỗ trợ. Kiểm tra link API xAPI cấp; không dùng link dashboard.')
            return 2
        req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'QuickOrder/1.0'})
        opener = urllib.request.build_opener(NoRedirect)
        try:
            with opener.open(req, timeout=15) as response:
                status, body = response.status, response.read(2_000_001)
        except urllib.error.HTTPError as error:
            status, body = error.code, error.read(2_000_001)
        if len(body) > 2_000_000:
            print('Phản hồi quá lớn; không in dữ liệu.'); return 2
        try:
            data = json.loads(body)
        except (ValueError, UnicodeError):
            print('HTTP:', status, '| Phản hồi không phải JSON lịch sử giao dịch.'); return 2
        print('\nBAO CAO CHAN DOAN (da an token va gia tri sao ke):')
        print(json.dumps(report(data, url, status), ensure_ascii=False, indent=2))
        print('Kết nối đọc lịch sử không đồng nghĩa một phiếu đã thanh toán.')
        return 0
    except (OSError, ValueError, urllib.error.URLError):
        print('Không đọc được phản hồi xAPI. Không in URL/token hoặc chi tiết kết nối có bí mật.')
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nĐã dừng kiểm tra.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
