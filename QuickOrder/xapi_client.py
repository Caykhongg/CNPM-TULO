"""Đọc lịch sử xapi.vn từ SERVER. Không gửi URL có token xuống trình duyệt.

Hỗ trợ mẫu chuẩn status=success/transactions và mẫu ACB codeStatus=200/data.
Mọi giao dịch được đưa về transactionID/amount/description/type IN/OUT trước khi đối soát.
"""
import json
import os
import re
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit


class PaymentError(Exception):
    pass


def validate_url(url):
    try:
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.netloc != "id.xapi.vn" or parts.query or parts.fragment
                or not re.fullmatch(r"/historyapi[A-Za-z0-9]+/[A-Za-z0-9._~-]+", parts.path)):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise PaymentError("URL xAPI không hợp lệ. Dùng đúng URL lịch sử HTTPS tại id.xapi.vn do xAPI cấp.") from None


def config_for(shop):
    try:
        cfg = json.loads(os.environ.get(f"XAPI_SHOP_{shop['id']}", "{}"))
        url = cfg.get("history_url", "")
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.netloc != "id.xapi.vn" or parts.query or parts.fragment
                or not re.fullmatch(r"/historyapi[A-Za-z0-9]+/[A-Za-z0-9._~-]+", parts.path)):
            raise ValueError
        bank, account = str(cfg["bank_bin"]), str(cfg["account_number"])
        if (not re.fullmatch(r"[0-9]{6}", bank) or not re.fullmatch(r"[A-Za-z0-9]{6,19}", account)
                or bank != shop["bank_bin"] or account != shop["bank_account_number"]
                or not shop["bank_account_name"]):
            raise ValueError
        return {"history_url": url, "bank_bin": bank, "account_number": account}
    except (ValueError, TypeError, KeyError, AttributeError):
        raise PaymentError("Quán chưa cấu hình chuyển khoản tự động hoặc tài khoản nhận chưa khớp. Vui lòng chọn tiền mặt hoặc báo chủ quán.") from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def parse_history(data, config):
    if not isinstance(data, dict):
        raise PaymentError('API không trả một bản lịch sử JSON hợp lệ.')
    endpoint = urlsplit(config['history_url']).path.rsplit('/', 1)[0]
    if endpoint == '/historyapiacb':
        if config.get('bank_bin') not in (None, '970416'):
            raise PaymentError('URL API ACB không khớp ngân hàng đang chọn. Hãy chọn ACB và đúng tài khoản nhận.')
        if 'codeStatus' in data and (type(data['codeStatus']) is not int or data['codeStatus'] != 200):
            code = data['codeStatus']
            detail = str(code) if type(code) is int and 0 <= code <= 9999 else 'không đúng định dạng'
            raise PaymentError('API ACB chưa xác nhận lấy lịch sử thành công (codeStatus: ' + detail + '). Kiểm tra token/gói dịch vụ trên xAPI.')
    if data.get('status') == 'success' and isinstance(data.get('transactions'), list):
        return data['transactions']
    if endpoint == '/historyapiacb':
        if 'codeStatus' not in data:
            raise PaymentError('API ACB chưa trả codeStatus để xác nhận lịch sử hợp lệ.')
        if 'status' in data and data['status'] != 'success':
            raise PaymentError('API ACB trả trạng thái mâu thuẫn. Chưa sử dụng dữ liệu này để xác nhận thanh toán.')
        rows = data.get('data')
        if not isinstance(rows, list):
            raise PaymentError('API ACB chưa trả danh sách giao dịch trong trường data.')
        result = []
        for row in rows:
            if not isinstance(row, dict) or row.get('type') not in ('IN', 'OUT'):
                raise PaymentError('API ACB có chiều giao dịch chưa hỗ trợ. Cần đối chiếu giá trị type; chưa bật xác nhận tự động.')
            currency = row.get('currency')
            if currency is not None and currency != 'VND':
                raise PaymentError('API ACB trả loại tiền khác VND hoặc chưa xác định. Chưa tự xác nhận thanh toán.')
            account = row.get('account')
            expected = config.get('account_number')
            if account not in (None, '') and expected and str(account).strip() != expected:
                raise PaymentError('Tài khoản trong lịch sử ACB không khớp số tài khoản của quán. Hãy kiểm tra lại ngân hàng nhận tiền và token.')
            # Ưu tiên mã giao dịch xAPI đã chuẩn hóa; dùng mã ACB gốc khi chưa có.
            tid = next((row.get(k) for k in ('transactionID', 'rawTransactionID', 'transactionNumber')
                        if row.get(k) not in (None, '')), None)
            if isinstance(tid, bool) or not isinstance(tid, (str, int)):
                raise PaymentError('Một giao dịch ACB chưa có mã đối soát hợp lệ.')
            if not isinstance(row.get('description'), str):
                raise PaymentError('Một giao dịch ACB chưa có nội dung chuyển khoản hợp lệ.')
            result.append({'transactionID': str(tid), 'amount': row.get('amount'),
                           'description': row['description'], 'type': row['type']})
        return result
    raise PaymentError('xAPI chưa trả lịch sử giao dịch hợp lệ. Kiểm tra token, gói dịch vụ và đúng URL API lịch sử của ngân hàng.')


def fetch_transactions(config):
    """Không log exception gốc vì URL chứa token. Chặn redirect sang host khác."""
    req = urllib.request.Request(config["history_url"], headers={"Accept": "application/json", "User-Agent": "QuickOrder/1.0"})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=12) as response:
            if response.status != 200:
                raise ValueError
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError
            data = json.loads(raw)
        return parse_history(data, config)
    except urllib.error.HTTPError as error:
        raise PaymentError(f"xAPI trả HTTP {error.code}. Kiểm tra token, URL API lịch sử và trạng thái tài khoản ngân hàng trên xAPI.") from None
    except (OSError, ValueError, TypeError, urllib.error.URLError):
        raise PaymentError("Chưa kiểm tra được giao dịch từ xAPI. Hệ thống sẽ thử lại; nếu đã chuyển tiền, vui lòng không chuyển thêm.") from None


def incoming(transaction):
    """Chỉ nhận tiền VÀO, số VND nguyên dương; không suy diễn 'status success' là đã trả tiền."""
    if not isinstance(transaction, dict) or transaction.get("type") != "IN":
        return None
    tid, description, raw_amount = transaction.get("transactionID"), transaction.get("description"), transaction.get("amount")
    if (not isinstance(tid, str) or not tid.strip() or len(tid) > 160 or not isinstance(description, str)
            or len(description) > 4000 or isinstance(raw_amount, bool)):
        return None
    try:
        amount = Decimal(str(raw_amount))
        if not amount.is_finite() or amount != amount.to_integral_value() or not 0 < amount < 10**13:
            return None
    except (InvalidOperation, ValueError):
        return None
    codes = set(re.findall(r"(?<![A-Z0-9])QO[A-F0-9]{16}(?![A-Z0-9])", description.upper()))
    if len(codes) != 1:
        return None
    return {"id": tid.strip(), "amount": int(amount), "description": description, "code": codes.pop()}
