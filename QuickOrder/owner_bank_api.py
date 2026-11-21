"""Cấu hình ngân hàng và duyệt chuyển khoản thủ công: chỉ chủ quán của đúng quán/admin."""
import json
import re
import sqlite3
import time

from flask import abort, jsonify
import bank_connections
import xapi_client


class OwnerBankAPI:
    def catalog(self):
        return jsonify(banks=bank_connections.CATALOG)

    def owner_config(self, sid):
        u = self.login_required('owner', 'admin')
        with self.db() as c:
            self.shop_for(c, sid, u)
            shop = c.execute('SELECT * FROM shops WHERE id=?', (sid,)).fetchone()
            result = dict(bank_bin=shop['bank_bin'], account_number=shop['bank_account_number'] or '',
                          account_name=shop['bank_account_name'], mode='MANUAL', has_token=False, ready=False)
            try:
                cfg = bank_connections.current_config(c, shop)
                result.update(mode=cfg['mode'], ready=cfg['mode'] == 'AUTO', has_token=cfg['mode'] == 'AUTO')
            except xapi_client.PaymentError as error:
                result.update(mode='AUTO', has_token=True, message=str(error))
        result['message'] = result.get('message') or ('Đã kết nối xAPI. Tự xác nhận khi có giao dịch khớp.' if result['mode'] == 'AUTO'
                                                     else 'Chưa dùng xAPI. Quán tự kiểm tra tiền và xác nhận chuyển khoản.')
        return jsonify(result)

    def save_bank(self, sid):
        u, data = self.login_required('owner', 'admin'), self.json_body()
        with self.db() as c:
            self.shop_for(c, sid, u)
            shop = c.execute('SELECT * FROM shops WHERE id=?', (sid,)).fetchone()
            settings = c.execute('SELECT * FROM shop_payment_settings WHERE shop_id=?', (sid,)).fetchone()
        try:
            recipient = bank_connections.recipient(data)
            credential = data.get('credential') or ''
            if not isinstance(credential, str):
                raise xapi_client.PaymentError('Token/URL xAPI phải là chuỗi.')
            credential = credential.strip()
            mode = data.get('mode', 'AUTO' if credential else 'MANUAL')
            if mode not in ('MANUAL', 'AUTO'):
                raise xapi_client.PaymentError('Chọn chế độ xác nhận thanh toán hợp lệ.')
            new_cipher, connection_id = None, None
            if mode == 'AUTO':
                if credential:
                    # Kiểm tra khóa lưu trữ trước khi gửi token tới xAPI; lỗi không ghi đè cấu hình đang chạy.
                    bank_connections.cipher()
                    url = bank_connections.from_input(credential, recipient['bank_bin'])
                    xapi_client.fetch_transactions({**recipient, 'history_url': url})
                    new_cipher = bank_connections.encode_url(url)
                elif (settings and settings['mode'] == 'AUTO' and settings['connection_id']
                      and shop['bank_bin'] == recipient['bank_bin'] and shop['bank_account_number'] == recipient['account_number']):
                    connection_id = settings['connection_id']
                elif (not settings and shop['bank_bin'] == recipient['bank_bin']
                      and shop['bank_account_number'] == recipient['account_number']):
                    # Chủ quán lưu lại bản cũ dùng .env: chuyển token đó sang kho mã hóa, không bắt nhập lại.
                    legacy = xapi_client.config_for(shop)
                    bank_connections.cipher()
                    xapi_client.fetch_transactions(legacy)
                    new_cipher = bank_connections.encode_url(legacy['history_url'])
                else:
                    raise xapi_client.PaymentError('Nhập token hoặc URL API lịch sử xAPI để bật tự động cho tài khoản này.')
        except xapi_client.PaymentError as error:
            return jsonify(error=str(error)), 400
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            self.shop_for(c, sid, u)
            if new_cipher:
                connection_id = c.execute('INSERT INTO payment_connections(shop_id,bank_bin,account_number,credentials_enc,verified_at) VALUES (?,?,?,?,?)',
                                          (sid, recipient['bank_bin'], recipient['account_number'], new_cipher, int(time.time()))).lastrowid
            elif connection_id:
                # Một tab khác có thể vừa đổi cấu hình trong lúc chờ request; không dùng nhầm tài khoản.
                conn = c.execute('SELECT * FROM payment_connections WHERE id=? AND shop_id=?', (connection_id, sid)).fetchone()
                if not conn or conn['bank_bin'] != recipient['bank_bin'] or conn['account_number'] != recipient['account_number']:
                    return jsonify(error='Kết nối vừa thay đổi. Hãy tải lại thông tin quán.'), 409
            c.execute('UPDATE shops SET bank_bin=?,bank_account_number=?,bank_account_name=? WHERE id=?',
                      (recipient['bank_bin'], recipient['account_number'], recipient['account_name'], sid))
            c.execute('INSERT INTO shop_payment_settings(shop_id,mode,connection_id) VALUES (?,?,?) ON CONFLICT(shop_id) DO UPDATE SET mode=excluded.mode,connection_id=excluded.connection_id',
                      (sid, mode, connection_id if mode == 'AUTO' else None))
        self._wake.set()
        return self.owner_config(sid)

    def test_bank(self, sid):
        u = self.login_required('owner', 'admin')
        with self.db() as c:
            self.shop_for(c, sid, u)
            shop = c.execute('SELECT * FROM shops WHERE id=?', (sid,)).fetchone()
            try:
                cfg = bank_connections.current_config(c, shop)
            except xapi_client.PaymentError as error:
                return jsonify(error=str(error)), 400
        if cfg['mode'] != 'AUTO':
            return jsonify(error='Quán đang xác nhận thủ công, chưa có kết nối xAPI.'), 409
        try:
            rows = xapi_client.fetch_transactions(cfg)
        except xapi_client.PaymentError as error:
            return jsonify(error=str(error)), 502
        return jsonify(ok=True, transaction_count=len(rows), message='Đã đọc được lịch sử từ xAPI. Hãy kiểm tra tài khoản nhận bằng một giao dịch thật trước khi nhận khách.')

    def owner_queue(self, sid):
        u = self.login_required('owner', 'admin')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            self.shop_for(c, sid, u)
            self.expire(c)
            rows = c.execute("SELECT * FROM payment_checkouts WHERE shop_id=? AND state='WAITING' ORDER BY created_at DESC LIMIT 100", (sid,)).fetchall()
            result = []
            for row in rows:
                item = self.view(c, row)
                spec = json.loads(row['snapshot'])
                item['customer_name'] = spec['customer_name']
                item['can_confirm'] = row['verification_mode'] == 'MANUAL'
                result.append(item)
        return jsonify(result)

    def confirm_manual(self, sid, pid):
        u, data = self.login_required('owner', 'admin'), self.json_body()
        tid = str(data.get('transaction_id') or '').strip()
        if not re.fullmatch(r'[A-Za-z0-9._:/-]{3,160}', tid):
            return jsonify(error='Nhập mã giao dịch trên sao kê ngân hàng (3–160 ký tự).'), 400
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            self.shop_for(c, sid, u)
            self.expire(c)
            row = c.execute('SELECT * FROM payment_checkouts WHERE id=? AND shop_id=?', (pid, sid)).fetchone()
            if not row:
                abort(404)
            if row['verification_mode'] != 'MANUAL':
                return jsonify(error='Phiếu này đang đối soát tự động bằng xAPI.'), 409
            if row['state'] == 'PAID':
                return jsonify(self.view(c, row))
            if row['state'] != 'WAITING':
                return jsonify(error='Phiếu đã hết hạn hoặc cần đối soát riêng. Không tự gửi đơn.'), 409
            try:
                rid = c.execute('INSERT INTO payment_receipts(checkout_id,bank_bin,account_number,transaction_id,amount,description,verification_method,confirmed_by) VALUES (?,?,?,?,?,?,?,?)',
                                (pid, row['bank_bin'], row['account_number'], tid, row['amount'], 'Chủ quán xác nhận: ' + row['transfer_code'], 'MANUAL', u['id'])).lastrowid
            except sqlite3.IntegrityError:
                return jsonify(error='Mã giao dịch này đã được dùng cho một phiếu khác.'), 409
            shop = c.execute('SELECT * FROM shops WHERE id=?', (sid,)).fetchone()
            problem = self.promote(c, row, shop, 'MANUAL')
            if problem:
                self.mark_review(c, row, rid, problem)
            result = self.view(c, c.execute('SELECT * FROM payment_checkouts WHERE id=?', (pid,)).fetchone())
        return jsonify(result)
