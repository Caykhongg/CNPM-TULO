"""Phiếu chờ chuyển khoản độc lập với orders: chỉ có giao dịch hợp lệ mới gửi đơn cho quán."""
import hmac
import json
import os
import secrets
import sqlite3
import time
import threading
from urllib.parse import urlencode

from flask import abort, jsonify, request
import xapi_client
import bank_connections
from owner_bank_api import OwnerBankAPI

TTL = 15 * 60
POLL_SECONDS = 5
REVIEW_DAYS = 30


class PaymentService(OwnerBankAPI):
    def __init__(self, app, **deps):
        self.app = app
        self.__dict__.update(deps)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._worker_lock = threading.Lock()
        self._worker = None
        app.before_request(self.ensure_worker)
        app.add_url_rule('/api/payment-banks', 'payment_banks', self.catalog, methods=['GET'])
        app.add_url_rule('/api/shops/<int:sid>/payment-config', 'payment_config_save', self.save_bank, methods=['PUT'])
        app.add_url_rule('/api/shops/<int:sid>/payment-config/test', 'payment_config_test', self.test_bank, methods=['POST'])
        app.add_url_rule('/api/shops/<int:sid>/payment-checkouts', 'payment_queue', self.owner_queue, methods=['GET'])
        app.add_url_rule('/api/shops/<int:sid>/payment-checkouts/<pid>/confirm', 'payment_manual_confirm', self.confirm_manual, methods=['POST'])
        app.add_url_rule('/api/payments/<pid>', 'payment_get', self.get, methods=['GET'])
        app.add_url_rule('/api/payments/<pid>/check', 'payment_check', self.check, methods=['POST'])
        app.add_url_rule('/api/payments/mine', 'payments_mine', self.mine, methods=['GET'])
        app.add_url_rule('/api/shops/<int:sid>/payment-config', 'payment_config', self.owner_config, methods=['GET'])
        app.add_url_rule('/api/shops/<int:sid>/payment-receipts', 'payment_receipts', self.receipts, methods=['GET'])
        app.add_url_rule('/api/shops/<int:sid>/payment-receipts/<int:rid>/resolve', 'payment_resolve', self.resolve, methods=['PUT'])
        app.add_url_rule('/api/internal/payments/reconcile', 'payments_reconcile', self.internal_reconcile, methods=['POST'])

    def expire(self, c):
        rows = c.execute("SELECT * FROM payment_checkouts WHERE state='WAITING' AND expires_at <= ?", (int(time.time()),)).fetchall()
        for row in rows:
            done = c.execute("UPDATE payment_checkouts SET state='EXPIRED' WHERE id=? AND state='WAITING'", (row['id'],))
            if done.rowcount:
                self.release(c, row)

    def release(self, c, row):
        if row['coupon_reserved']:
            done = c.execute('UPDATE payment_checkouts SET coupon_reserved=0 WHERE id=? AND coupon_reserved=1', (row['id'],))
            if done.rowcount and row['coupon_id']:
                c.execute('UPDATE coupons SET used_count=MAX(used_count-1,0) WHERE id=?', (row['coupon_id'],))

    def create(self, c, shop, spec, token, request_id):
        pid, code, now = secrets.token_hex(16), 'QO' + secrets.token_hex(8).upper(), int(time.time())
        cfg = bank_connections.current_config(c, shop)
        c.execute("""INSERT INTO payment_checkouts
            (id, shop_id, user_id, request_id, access_hash, transfer_code, amount, bank_bin, account_number,
             account_name, snapshot, coupon_code, coupon_id, coupon_reserved, created_at, expires_at, verification_mode, connection_id)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, shop['id'], spec['user_id'], request_id, self.token_hash(token), code, spec['total'],
             shop['bank_bin'], shop['bank_account_number'], shop['bank_account_name'], json.dumps(spec, ensure_ascii=False),
             spec['coupon_code'], spec['coupon_id'], bool(spec['coupon_code']), now, now + TTL, cfg['mode'], cfg['connection_id']))
        self._wake.set()
        row = c.execute('SELECT * FROM payment_checkouts WHERE id=?', (pid,)).fetchone()
        result = self.view(c, row)
        result['access_token'] = token
        return jsonify(result), 201

    def duplicate(self, c, row, shop_id, request_id):
        if row['shop_id'] != shop_id:
            return jsonify(error='client_request_id đã được dùng cho quán khác.'), 409
        result = self.view(c, row)
        result.update(access_token=self.request_token(request_id), duplicate=True)
        return jsonify(result), 200

    def view(self, c, row):
        shop = c.execute('SELECT name,phone FROM shops WHERE id=?', (row['shop_id'],)).fetchone()
        result = {k: row[k] for k in ('id', 'shop_id', 'state', 'transfer_code', 'amount', 'bank_bin', 'account_number',
                                      'account_name', 'created_at', 'expires_at', 'order_id', 'verification_mode')}
        result.update(kind='PAYMENT_CHECKOUT', shop_name=shop['name'], shop_phone=shop['phone'])
        snapshot = json.loads(row['snapshot'])
        result['items'] = [{'dish_id': line[0], 'quantity': line[1],
                            'option_ids': [int(x) for x in line[4].split(',') if x]} for line in snapshot['lines']]
        if row['state'] == 'WAITING':
            result['qr_url'] = ('https://img.vietqr.io/image/' + row['bank_bin'] + '-' + row['account_number'] + '-compact2.svg?'
                                + urlencode({'amount': row['amount'], 'addInfo': row['transfer_code'], 'accountName': row['account_name']}))
        if row['order_id']:
            result['order'] = self.order_json(c, row['order_id'])
        return result

    def authorized(self, c, pid, token):
        row = c.execute('SELECT * FROM payment_checkouts WHERE id=?', (pid,)).fetchone()
        u = self.current_user()
        mine = row and u and u['role'] == 'customer' and u['id'] == row['user_id']
        if not row or not (mine or self.token_ok(row, token)):
            abort(404)
        return row

    def get(self, pid):
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            self.authorized(c, pid, request.args.get('token', ''))
            self.expire(c)
            result = self.view(c, c.execute('SELECT * FROM payment_checkouts WHERE id=?', (pid,)).fetchone())
        return jsonify(result)

    def check(self, pid):
        d = self.json_body()
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = self.authorized(c, pid, str(d.get('token') or ''))
            self.expire(c)
            auto = row['verification_mode'] == 'AUTO'
            sid = row['shop_id']
        failure = None
        if auto:
            try:
                self.reconcile_shop(sid)
            except xapi_client.PaymentError as error:
                failure = str(error)
        with self.db() as c:
            result = self.view(c, c.execute('SELECT * FROM payment_checkouts WHERE id=?', (pid,)).fetchone())
        if failure and result['state'] != 'PAID':
            return jsonify(error=failure), 503
        return jsonify(result)

    def mine(self):
        u = self.login_required('customer')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            self.expire(c)
            rows = c.execute("SELECT * FROM payment_checkouts WHERE user_id=? AND state!='PAID' ORDER BY created_at DESC LIMIT 30", (u['id'],)).fetchall()
            return jsonify([self.view(c, r) for r in rows])

    def ensure_worker(self):
        if self.app.testing or os.environ.get('PAYMENT_WORKER', '1') == '0':
            return
        with self._worker_lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self.worker_loop, name='qo-bank-reconcile', daemon=True)
                self._worker.start()

    def worker_loop(self):
        while not self._stop.is_set():
            try:
                with self.db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    self.expire(c)
                    ids = [r[0] for r in c.execute("SELECT DISTINCT shop_id FROM payment_checkouts WHERE verification_mode='AUTO' AND created_at>=?", (int(time.time()) - REVIEW_DAYS * 86400,))]
                for sid in ids:
                    if self._stop.is_set():
                        break
                    try:
                        self.reconcile_shop(sid)
                    except xapi_client.PaymentError:
                        self.app.logger.warning('Chưa đối soát được ngân hàng của quán #%s; sẽ thử lại.', sid)
            except Exception as error:
                # Không in URL/request chứa token khi provider hoặc CSDL gặp lỗi.
                self.app.logger.warning('Tác vụ ngân hàng sẽ thử lại (%s).', type(error).__name__)
            self._wake.wait(POLL_SECONDS)
            self._wake.clear()

    def stop_worker(self):
        self._stop.set()
        self._wake.set()
        if self._worker:
            self._worker.join(timeout=15)

    def promote(self, c, row, shop, source):
        if shop['status'] != 'APPROVED' or not self.is_open_now(shop):
            return 'Quán đang đóng cửa hoặc ngừng nhận đơn lúc xác nhận tiền.'
        spec = json.loads(row['snapshot'])
        valid = c.execute('SELECT 1 FROM shop_tables WHERE id=? AND shop_id=? AND qr_token=?',
                          (spec['table_id'], row['shop_id'], spec['qr_token'])).fetchone()
        if not valid or any(not c.execute("SELECT 1 FROM dishes WHERE id=? AND shop_id=? AND is_available=1 AND is_deleted=0",
                                         (line[0], row['shop_id'])).fetchone() for line in spec['lines']):
            return 'Bàn/món đã thay đổi hoặc hết món sau khi tạo QR. Cần quán đối soát.'
        c.execute('SAVEPOINT create_paid_order')
        try:
            oid = self.insert_order(c, spec, row['access_hash'], row['request_id'], paid=True, source=source)
        except sqlite3.IntegrityError:
            c.execute('ROLLBACK TO create_paid_order')
            return 'Không tạo được đơn từ dữ liệu đã lưu; cần quán kiểm tra khoản tiền.'
        finally:
            c.execute('RELEASE create_paid_order')
        c.execute("UPDATE payment_checkouts SET state='PAID',order_id=?,coupon_reserved=0 WHERE id=?", (oid, row['id']))
        return ''

    def mark_review(self, c, row, rid, problem):
        c.execute('UPDATE payment_receipts SET review_reason=? WHERE id=?', (problem, rid))
        if row['state'] != 'PAID':
            c.execute("UPDATE payment_checkouts SET state='REVIEW' WHERE id=?", (row['id'],))
            self.release(c, row)

    def source_configs(self, c, sid):
        shop = c.execute('SELECT * FROM shops WHERE id=?', (sid,)).fetchone()
        if not shop:
            return [], []
        # Một lần đọc lịch sử cho mỗi tài khoản, kể cả khi chủ quán vừa đổi token.
        rows = c.execute("SELECT DISTINCT bank_bin,account_number FROM payment_checkouts WHERE shop_id=? AND verification_mode='AUTO' AND created_at>=?",
                         (sid, int(time.time()) - REVIEW_DAYS * 86400)).fetchall()
        configs, errors = [], []
        for row in rows:
            try:
                conn = c.execute('SELECT * FROM payment_connections WHERE shop_id=? AND bank_bin=? AND account_number=? ORDER BY verified_at DESC,id DESC LIMIT 1',
                                 (sid, row['bank_bin'], row['account_number'])).fetchone()
                if conn:
                    cfg = bank_connections.stored_config(conn)
                else:
                    legacy = {**dict(shop), 'bank_bin': row['bank_bin'], 'bank_account_number': row['account_number']}
                    cfg = {**xapi_client.config_for(legacy), 'connection_id': None}
                key = f"account:{sid}:{row['bank_bin']}:{row['account_number']}"
                configs.append((key, cfg))
            except xapi_client.PaymentError as error:
                errors.append(str(error))
        return configs, errors

    def reconcile_shop(self, sid):
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            self.expire(c)
            configs, errors = self.source_configs(c, sid)
        created = 0
        for key, cfg in configs:
            now = int(time.time())
            with self.db() as c:
                c.execute('BEGIN IMMEDIATE')
                c.execute('INSERT OR IGNORE INTO payment_source_locks(source_key,next_poll) VALUES (?,0)', (key,))
                lease = c.execute('UPDATE payment_source_locks SET next_poll=? WHERE source_key=? AND next_poll<=?', (now + 20, key, now))
                if not lease.rowcount:
                    continue
            try:
                transactions = xapi_client.fetch_transactions(cfg)
                with self.db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    self.expire(c)
                    shop = c.execute('SELECT * FROM shops WHERE id=?', (sid,)).fetchone()
                    for raw in transactions:
                        tx = xapi_client.incoming(raw)
                        if not tx:
                            continue
                        row = c.execute("""SELECT * FROM payment_checkouts WHERE shop_id=? AND transfer_code=? AND bank_bin=?
                            AND account_number=? AND verification_mode='AUTO' AND created_at>=?""",
                            (sid, tx['code'], cfg['bank_bin'], cfg['account_number'], now - REVIEW_DAYS * 86400)).fetchone()
                        if not row:
                            continue
                        got = c.execute('INSERT OR IGNORE INTO payment_receipts(checkout_id,bank_bin,account_number,transaction_id,amount,description) VALUES (?,?,?,?,?,?)',
                                        (row['id'], cfg['bank_bin'], cfg['account_number'], tx['id'], tx['amount'], tx['description']))
                        if not got.rowcount:
                            continue
                        if row['state'] != 'WAITING':
                            problem = 'Tiền đến khi phiếu đã hết hạn/đã thanh toán hoặc đang cần đối soát.'
                        elif tx['amount'] != row['amount']:
                            problem = 'Số tiền chuyển không khớp. Cần quán đối soát, không tự gửi đơn.'
                        else:
                            problem = self.promote(c, row, shop, 'XAPI')
                            if not problem:
                                created += 1
                        if problem:
                            self.mark_review(c, row, got.lastrowid, problem)
            except xapi_client.PaymentError as error:
                errors.append(str(error))
            finally:
                with self.db() as c:
                    c.execute('UPDATE payment_source_locks SET next_poll=? WHERE source_key=?', (int(time.time()) + POLL_SECONDS, key))
        if errors:
            raise xapi_client.PaymentError(errors[0])
        return created

    def flag_cancelled(self, c, oid):
        c.execute("""UPDATE payment_receipts SET review_reason='Đơn đã thanh toán tự động nay bị hủy. Cần quán liên hệ khách và xử lý hoàn tiền thủ công.', resolved_note=''
            WHERE checkout_id IN (SELECT id FROM payment_checkouts WHERE order_id=?) AND review_reason=''""", (oid,))

    def receipts(self, sid):
        u = self.login_required('owner', 'admin')
        with self.db() as c:
            self.shop_for(c, sid, u)
            rows = c.execute("""SELECT r.id,r.checkout_id,r.transaction_id,r.amount,r.review_reason,r.resolved_note,
                r.created_at,p.transfer_code,p.amount AS expected_amount,p.order_id
                FROM payment_receipts r JOIN payment_checkouts p ON p.id=r.checkout_id
                WHERE p.shop_id=? AND r.review_reason!='' ORDER BY r.id DESC LIMIT 100""", (sid,)).fetchall()
            return jsonify([dict(r) for r in rows])

    def resolve(self, sid, rid):
        u = self.login_required('owner', 'admin')
        d = self.json_body()
        note = str(d.get('note') or '').strip()
        if not 5 <= len(note) <= 500:
            return jsonify(error='Nhập ghi chú xử lý từ 5 đến 500 ký tự.'), 400
        with self.db() as c:
            self.shop_for(c, sid, u)
            row = c.execute("SELECT r.id FROM payment_receipts r JOIN payment_checkouts p ON p.id=r.checkout_id WHERE r.id=? AND p.shop_id=? AND r.review_reason!=''", (rid, sid)).fetchone()
            if not row:
                abort(404)
            c.execute('UPDATE payment_receipts SET resolved_note=? WHERE id=?', (note, rid))
        return jsonify(ok=True)

    def internal_reconcile(self):
        expected = os.environ.get('PAYMENT_RECONCILE_SECRET', '')
        supplied = request.headers.get('Authorization', '')
        if len(expected) < 32 or not hmac.compare_digest(supplied.encode('utf-8'), ('Bearer ' + expected).encode('utf-8')):
            abort(403)
        # Đây là tác vụ do server/scheduler gọi, không nhận dữ liệu giao dịch từ người dùng.
        with self.db() as c:
            ids = [r[0] for r in c.execute("SELECT DISTINCT shop_id FROM payment_checkouts WHERE verification_mode='AUTO' AND created_at>=?",
                                          (int(time.time()) - REVIEW_DAYS * 86400,))]
        created, failed = 0, []
        for sid in ids:
            try:
                created += self.reconcile_shop(sid)
            except xapi_client.PaymentError:
                failed.append(sid)
        return jsonify(created_orders=created, failed_shops=failed), 503 if failed else 200
