"""Không gọi xAPI/ngân hàng thật. Kiểm tra chỉ giao dịch tiền vào đã đối chiếu mới tạo đơn."""
import json
import os
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import xapi_client


class PaymentTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = {'history_url': 'https://id.xapi.vn/historyapitpbv2/PRIVATE_TEST_TOKEN',
                    'bank_bin': '970423', 'account_number': '123456789'}
        env = patch.dict(os.environ, {'QO_DB': str(Path(tmp.name) / 'test.db'), 'SECRET_KEY': 'payment-tests',
                                      'XAPI_SHOP_1': json.dumps(self.cfg), 'PAYMENT_RECONCILE_SECRET': 'a' * 48})
        env.start(); self.addCleanup(env.stop)
        sys.modules.pop('app', None)
        import app
        self.qo = app
        app.app.config['TESTING'] = True
        self.guest, self.customer, self.owner, self.other = [app.app.test_client() for _ in range(4)]
        with app.db() as c:
            for uid, role in ((1, 'owner'), (2, 'customer'), (3, 'owner')):
                c.execute('INSERT INTO users(id,email,password_hash,role) VALUES (?,?,?,?)', (uid, f'{uid}@test.vn', 'unused', role))
            c.execute("""INSERT INTO shops(id,owner_id,name,address,phone,status,open_time,close_time,bank_bin,bank_account_number,bank_account_name)
                VALUES (1,1,'Quán thử','Test','0901234567','APPROVED','00:00','24:00','970423','123456789','NGUYEN VAN A')""")
            c.execute("INSERT INTO shops(id,owner_id,name,address,phone,status,open_time,close_time) VALUES (2,3,'Quán khác','T','0901234568','APPROVED','00:00','24:00')")
            c.execute("INSERT INTO shop_tables(id,shop_id,table_number,qr_token) VALUES (1,1,'1','qr-test')")
            c.execute("INSERT INTO categories(id,shop_id,name) VALUES (100,1,'Trà')")
            c.execute("INSERT INTO dishes(id,shop_id,category_id,name,price) VALUES (1,1,100,'Trà sữa',40000)")
            c.execute("INSERT INTO option_groups(id,dish_id,name) VALUES (1,1,'Topping')")
            c.execute("INSERT INTO options(id,group_id,name,extra_price) VALUES (1,1,'Trân châu',5000)")
        for client, uid in ((self.owner, 1), (self.customer, 2), (self.other, 3)):
            with client.session_transaction() as s:
                s['uid'] = uid

    def create(self, client=None, **extra):
        body = dict(shop_id=1, table_id=1, qr_token='qr-test', payment_method='TRANSFER',
                    client_request_id='a' * 32, items=[{'dish_id': 1, 'quantity': 2, 'option_ids': [1]}])
        body.update(extra)
        return (client or self.guest).post('/api/orders', json=body)

    def waiting(self, client=None, **extra):
        r = self.create(client, **extra)
        self.assertEqual(r.status_code, 201, r.get_json())
        p = r.get_json()
        self.assertEqual(p['kind'], 'PAYMENT_CHECKOUT')
        return p

    def tx(self, p, **extra):
        t = dict(transactionID='bank-001', type='IN', amount=p['amount'],
                 description='NGUYEN VAN A ' + p['transfer_code'] + ' chuyen tien')
        t.update(extra)
        return t

    def check(self, p, transactions, client=None):
        with self.qo.db() as c:
            c.execute('DELETE FROM payment_poll_locks')
            c.execute('DELETE FROM payment_source_locks')
        with patch.object(xapi_client, 'fetch_transactions', return_value=transactions):
            return (client or self.guest).post('/api/payments/' + p['id'] + '/check', json={'token': p['access_token']})

    def count_orders(self):
        with self.qo.db() as c:
            return c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]

    def coupon(self):
        with self.qo.db() as c:
            c.execute("INSERT INTO coupons(shop_id,code,discount_type,discount_value,max_uses) VALUES (1,'GIAM10','AMOUNT',10000,1)")

    def uses(self):
        with self.qo.db() as c:
            return c.execute('SELECT used_count FROM coupons').fetchone()[0]

    def test_cash_is_immediately_sent_to_shop(self):
        r = self.create(payment_method='CASH')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()['payment_status'], 'UNPAID')
        self.assertEqual(len(self.owner.get('/api/orders').get_json()), 1)

    def test_transfer_has_qr_but_no_order_no_bill_no_history(self):
        p = self.waiting(self.customer)
        self.assertEqual(p['state'], 'WAITING')
        self.assertEqual(p['amount'], 90000)
        self.assertIn('amount=90000', p['qr_url'])
        self.assertIn(p['transfer_code'], p['qr_url'])
        self.assertEqual(self.owner.get('/api/orders').get_json(), [])
        self.assertEqual(self.owner.get('/api/shops/1/bills').get_json(), [])
        self.assertEqual(self.count_orders(), 0)
        self.assertEqual(len(self.customer.get('/api/payments/mine').get_json()), 1)

    def test_client_cannot_set_amount_status_or_paid(self):
        p = self.waiting(amount=1, total_amount=1, payment_status='PAID', state='PAID', status='COMPLETED')
        self.assertEqual((p['state'], p['amount']), ('WAITING', 90000))
        self.assertEqual(self.count_orders(), 0)

    def test_unconfigured_transfer_does_not_reserve_coupon(self):
        self.coupon()
        with patch.dict(os.environ, {'XAPI_SHOP_1': '{}'}):
            self.assertEqual(self.create(coupon_code='GIAM10').status_code, 409)
        self.assertEqual(self.uses(), 0)

    def test_recipient_mismatch_is_rejected(self):
        with patch.dict(os.environ, {'XAPI_SHOP_1': json.dumps({**self.cfg, 'account_number': '987654321'})}):
            self.assertEqual(self.create().status_code, 409)

    def test_url_token_and_snapshot_are_not_public(self):
        p = self.waiting()
        for result in (p, self.guest.get('/api/shops/1').get_json(), self.owner.get('/api/shops/1/payment-config').get_json()):
            self.assertNotIn('PRIVATE_TEST_TOKEN', json.dumps(result))
            self.assertNotIn('snapshot', result)
            self.assertNotIn('access_hash', result)

    def test_empty_successful_history_does_not_mean_paid(self):
        p = self.waiting()
        self.assertEqual(self.check(p, []).get_json()['state'], 'WAITING')
        self.assertEqual(self.count_orders(), 0)

    def test_outgoing_wrong_code_and_code_substrings_never_pay(self):
        p = self.waiting()
        bad = [self.tx(p, type='OUT'), self.tx(p, transactionID='2', description='OTHER'),
               self.tx(p, transactionID='3', description=p['transfer_code'] + 'A')]
        self.assertEqual(self.check(p, bad).get_json()['state'], 'WAITING')
        self.assertEqual(self.count_orders(), 0)

    def test_exact_payment_creates_one_paid_order_and_history(self):
        p = self.waiting(self.customer)
        r = self.check(p, [self.tx(p)])
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data['state'], 'PAID')
        self.assertEqual((data['order']['payment_status'], data['order']['status']), ('PAID', 'PENDING'))
        self.assertEqual(len(self.owner.get('/api/orders').get_json()), 1)
        oid = data['order_id']
        self.assertEqual(self.guest.get(f'/api/orders/{oid}?token=' + p['access_token']).status_code, 200)
        self.assertEqual(self.customer.get(f'/api/orders/{oid}').status_code, 200)

    def test_repeat_bank_transaction_and_retry_never_create_second_order(self):
        self.coupon()
        p = self.waiting(coupon_code='GIAM10')
        for _ in range(3):
            self.assertEqual(self.check(p, [self.tx(p), self.tx(p)]).get_json()['state'], 'PAID')
        self.assertEqual(self.count_orders(), 1)
        self.assertEqual(self.uses(), 1)
        retry = self.create(coupon_code='GIAM10').get_json()
        self.assertTrue(retry['duplicate'])
        self.assertEqual(retry['order_id'], 1)

    def test_duplicate_checkout_preserves_code_token_and_reservation(self):
        self.coupon()
        a = self.waiting(coupon_code='GIAM10')
        b = self.create(coupon_code='GIAM10').get_json()
        self.assertEqual((a['id'], a['transfer_code'], a['access_token']), (b['id'], b['transfer_code'], b['access_token']))
        self.assertEqual(self.uses(), 1)

    def test_wrong_amount_goes_to_review_and_releases_coupon_once(self):
        self.coupon()
        p = self.waiting(coupon_code='GIAM10')
        self.assertEqual(self.check(p, [self.tx(p, amount=1)]).get_json()['state'], 'REVIEW')
        self.check(p, [self.tx(p, amount=1)])
        self.assertEqual(self.uses(), 0)
        self.assertEqual(self.count_orders(), 0)
        rows = self.owner.get('/api/shops/1/payment-receipts').get_json()
        self.assertEqual((len(rows), rows[0]['amount']), (1, 1))

    def test_expired_checkout_releases_coupon_and_late_money_needs_review(self):
        self.coupon()
        p = self.waiting(coupon_code='GIAM10')
        with self.qo.db() as c:
            c.execute('UPDATE payment_checkouts SET expires_at=?', (int(time.time()) - 1,))
        url = '/api/payments/' + p['id'] + '?token=' + p['access_token']
        self.assertEqual(self.guest.get(url).get_json()['state'], 'EXPIRED')
        self.assertEqual(self.uses(), 0)
        self.assertEqual(self.check(p, [self.tx(p)]).get_json()['state'], 'REVIEW')
        self.assertEqual((self.count_orders(), self.uses()), (0, 0))

    def test_changed_menu_price_keeps_snapshot_price_and_option_name(self):
        p = self.waiting()
        with self.qo.db() as c:
            c.execute('UPDATE dishes SET price=999999 WHERE id=1')
            c.execute("UPDATE options SET name='Đã đổi tên',extra_price=999 WHERE id=1")
        order = self.check(p, [self.tx(p)]).get_json()['order']
        self.assertEqual(order['total_amount'], 90000)
        self.assertEqual(order['items'][0]['options'][0]['name'], 'Trân châu')

    def test_shop_locked_or_dish_sold_out_after_qr_requires_review(self):
        p = self.waiting()
        with self.qo.db() as c:
            c.execute("UPDATE shops SET status='LOCKED' WHERE id=1")
        self.assertEqual(self.check(p, [self.tx(p)]).get_json()['state'], 'REVIEW')
        self.assertEqual(self.count_orders(), 0)

    def test_provider_error_is_not_success_and_does_not_drop_checkout(self):
        p = self.waiting()
        with patch.object(xapi_client, 'fetch_transactions', side_effect=xapi_client.PaymentError('Chưa kết nối được')):
            r = self.guest.post('/api/payments/' + p['id'] + '/check', json={'token': p['access_token']})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(self.count_orders(), 0)

    def test_checkout_is_private_but_owner_customer_can_resume(self):
        p = self.waiting(self.customer)
        url = '/api/payments/' + p['id']
        self.assertEqual(self.guest.get(url).status_code, 404)
        self.assertEqual(self.other.post(url + '/check', json={'token': 'fake'}).status_code, 404)
        self.assertEqual(self.customer.get(url).status_code, 200)

    def test_owner_cannot_revert_automatically_paid_order(self):
        p = self.waiting()
        oid = self.check(p, [self.tx(p)]).get_json()['order_id']
        r = self.owner.put(f'/api/orders/{oid}/payment', json={'payment_status': 'UNPAID'})
        self.assertEqual(r.status_code, 409)

    def test_internal_scheduler_requires_secret_and_runs_without_browser(self):
        p = self.waiting()
        url = '/api/internal/payments/reconcile'
        self.assertEqual(self.guest.post(url).status_code, 403)
        with patch.object(xapi_client, 'fetch_transactions', return_value=[self.tx(p)]):
            r = self.guest.post(url, headers={'Authorization': 'Bearer ' + 'a' * 48})
        self.assertEqual(r.get_json()['created_orders'], 1)
        self.assertEqual(self.count_orders(), 1)

    def test_parallel_reconciliation_only_fetches_and_creates_once(self):
        p = self.waiting()
        with patch.object(xapi_client, 'fetch_transactions', return_value=[self.tx(p)]) as fetch:
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(self.qo.payment_service.reconcile_shop, [1, 1]))
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(self.count_orders(), 1)

    def test_review_is_scoped_and_resolution_is_only_a_note(self):
        p = self.waiting()
        self.check(p, [self.tx(p, amount=1)])
        rid = self.owner.get('/api/shops/1/payment-receipts').get_json()[0]['id']
        self.assertEqual(self.other.get('/api/shops/1/payment-receipts').status_code, 403)
        url = f'/api/shops/1/payment-receipts/{rid}/resolve'
        self.assertEqual(self.other.put(url, json={'note': 'Đã xử lý'}).status_code, 403)
        self.assertEqual(self.owner.put(url, json={'note': 'Đã liên hệ khách và hoàn tiền thủ công'}).status_code, 200)
        self.assertEqual(self.count_orders(), 0)

    def test_second_distinct_transfer_is_flagged_without_second_order(self):
        p = self.waiting()
        self.check(p, [self.tx(p)])
        self.check(p, [self.tx(p), self.tx(p, transactionID='bank-002')])
        self.assertEqual(self.count_orders(), 1)
        self.assertEqual(len(self.owner.get('/api/shops/1/payment-receipts').get_json()), 1)

    def test_forged_success_in_browser_request_is_ignored(self):
        p = self.waiting()
        with patch.object(xapi_client, 'fetch_transactions', return_value=[]):
            r = self.guest.post('/api/payments/' + p['id'] + '/check', json={
                'token': p['access_token'], 'success': True, 'state': 'PAID', 'transactions': [self.tx(p)]})
        self.assertEqual(r.get_json()['state'], 'WAITING')
        self.assertEqual(self.count_orders(), 0)

    def test_expiry_releases_reservation_even_if_owner_renamed_coupon(self):
        self.coupon()
        p = self.waiting(coupon_code='GIAM10')
        with self.qo.db() as c:
            c.execute("UPDATE coupons SET code='TENMOI'")
            c.execute('UPDATE payment_checkouts SET expires_at=0')
        self.guest.get('/api/payments/' + p['id'] + '?token=' + p['access_token'])
        self.assertEqual(self.uses(), 0)

    def test_cancelling_paid_order_creates_refund_review_record(self):
        p = self.waiting()
        oid = self.check(p, [self.tx(p)]).get_json()['order_id']
        r = self.guest.put(f'/api/orders/{oid}/cancel', json={'token': p['access_token']})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['payment_status'], 'PAID')
        review = self.owner.get('/api/shops/1/payment-receipts').get_json()
        self.assertEqual(len(review), 1)
        self.assertIn('hoàn tiền', review[0]['review_reason'])


class XapiAdapterTests(unittest.TestCase):
    def test_invalid_amounts_do_not_become_payments(self):
        for value in (True, False, 'NaN', 'Infinity', -1, 0, '1,000', 0.5):
            tx = dict(type='IN', transactionID='abc', amount=value, description='QO1234567890ABCDEF')
            self.assertIsNone(xapi_client.incoming(tx), value)

    def test_only_expected_xapi_https_history_endpoints_are_allowed(self):
        shop = dict(id=9, bank_bin='970423', bank_account_number='123456789', bank_account_name='A')
        urls = ('http://id.xapi.vn/historyapitpbv2/TOKEN', 'https://evil.test/historyapitpbv2/TOKEN',
                'https://id.xapi.vn@evil.test/historyapitpbv2/TOKEN', 'https://id.xapi.vn/historyapitpbv2/TOKEN?evil=1')
        for url in urls:
            with patch.dict(os.environ, {'XAPI_SHOP_9': json.dumps(dict(history_url=url, bank_bin='970423', account_number='123456789'))}):
                with self.assertRaises(xapi_client.PaymentError):
                    xapi_client.config_for(shop)


if __name__ == '__main__':
    unittest.main()
