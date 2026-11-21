"""Quyền chủ quán, token mã hóa, QR thủ công/tự động, đổi tài khoản và đối soát nền."""
import json
import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import test_xapi_payments as fixtures
import bank_connections
import xapi_client


class OwnerBankTests(unittest.TestCase):
    create = fixtures.PaymentTests.create
    waiting = fixtures.PaymentTests.waiting
    tx = fixtures.PaymentTests.tx
    count_orders = fixtures.PaymentTests.count_orders

    def setUp(self):
        fixtures.PaymentTests.setUp(self)
        settings = patch.dict(os.environ, {'XAPI_SHOP_1': '', 'SECRET_KEY': 'owner-banks-tests-fixed-key-at-least-32-characters'})
        settings.start(); self.addCleanup(settings.stop)

    def save(self, credential='', client=None, bank='970423', account='123456789', mode=None):
        body = dict(bank_bin=bank, account_number=account, account_name='NGUYEN VAN A', credential=credential)
        if mode:
            body['mode'] = mode
        return (client or self.owner).put('/api/shops/1/payment-config', json=body)

    def connect(self, credential='OWNER_PRIVATE_TOKEN', **kwargs):
        with patch.object(xapi_client, 'fetch_transactions', return_value=[]):
            response = self.save(credential, **kwargs)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response

    def manual_confirm(self, p, tid='BANK-REFERENCE-001', client=None):
        return (client or self.owner).post('/api/shops/1/payment-checkouts/' + p['id'] + '/confirm', json={'transaction_id': tid})

    def test_catalog_lists_bank_names_and_bins_without_credentials(self):
        data = self.guest.get('/api/payment-banks').get_json()
        self.assertTrue(any(b['bin'] == '970423' for b in data['banks']))
        self.assertGreater(len(data['banks']), 30)

    def test_no_token_saves_manual_mode_and_still_produces_dynamic_qr(self):
        response = self.save()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['mode'], 'MANUAL')
        p = self.waiting()
        self.assertEqual(p['verification_mode'], 'MANUAL')
        self.assertIn('amount=90000', p['qr_url'])
        self.assertIn(p['transfer_code'], p['qr_url'])
        self.assertEqual(self.count_orders(), 0)

    def test_manual_customer_poll_never_calls_xapi_or_accepts_browser_success(self):
        self.save(); p = self.waiting()
        with patch.object(xapi_client, 'fetch_transactions') as fetch:
            r = self.guest.post('/api/payments/' + p['id'] + '/check', json={'token': p['access_token'], 'success': True})
        fetch.assert_not_called()
        self.assertEqual(r.get_json()['state'], 'WAITING')

    def test_only_own_shop_can_save_token_or_read_configuration(self):
        for client, status in ((self.guest, 401), (self.customer, 403), (self.other, 403)):
            with patch.object(xapi_client, 'fetch_transactions') as fetch:
                self.assertEqual(self.save('PRIVATE', client=client).status_code, status)
            fetch.assert_not_called()
            self.assertEqual(client.get('/api/shops/1/payment-config').status_code, status)

    def test_connect_checks_provider_and_encrypts_token_without_exposing_it(self):
        token = 'OWNER_PRIVATE_TOKEN'
        response = self.connect(token)
        self.assertTrue(response.get_json()['has_token'])
        with self.qo.db() as c:
            row = c.execute('SELECT * FROM payment_connections').fetchone()
            self.assertNotIn(token, row['credentials_enc'])
            self.assertIn(token, bank_connections.decode_url(row['credentials_enc']))
        for route in ('/api/shops/1', '/api/shops', '/api/shops/1/payment-config'):
            self.assertNotIn(token, self.owner.get(route).get_data(as_text=True))

    def test_plain_token_for_unmapped_bank_requires_official_url(self):
        with patch.object(xapi_client, 'fetch_transactions') as fetch:
            response = self.save('PRIVATE', bank='970422')
        self.assertEqual(response.status_code, 400)
        self.assertIn('URL', response.get_json()['error'])
        fetch.assert_not_called()

    def test_official_full_url_connects_without_guessing_bank_endpoint(self):
        self.connect('https://id.xapi.vn/historyapiBANKVERSION/OWNER_PRIVATE_TOKEN', bank='970422')
        p = self.waiting()
        self.assertEqual((p['bank_bin'], p['verification_mode']), ('970422', 'AUTO'))

    def test_secret_url_cannot_redirect_server_to_another_host(self):
        with patch.object(xapi_client, 'fetch_transactions') as fetch:
            r = self.save('https://evil.example/historyapiANY/PRIVATE')
        self.assertEqual(r.status_code, 400)
        fetch.assert_not_called()

    def test_bad_token_does_not_overwrite_working_connection_or_bank(self):
        self.connect()
        with patch.object(xapi_client, 'fetch_transactions', side_effect=xapi_client.PaymentError('Token không sử dụng được')):
            r = self.save('BAD_TOKEN', account='987654321')
        self.assertEqual(r.status_code, 400)
        data = self.owner.get('/api/shops/1/payment-config').get_json()
        self.assertEqual((data['mode'], data['account_number']), ('AUTO', '123456789'))

    def test_blank_token_retains_existing_auto_connection_when_selected(self):
        self.connect()
        with patch.object(xapi_client, 'fetch_transactions') as fetch:
            response = self.save(mode='AUTO')
        self.assertEqual(response.status_code, 200)
        fetch.assert_not_called()
        self.assertEqual(response.get_json()['mode'], 'AUTO')

    def test_disabling_auto_only_affects_new_checkouts(self):
        self.connect()
        old = self.waiting()
        self.save(mode='MANUAL')
        new = self.waiting(client_request_id='b' * 32)
        self.assertEqual((old['verification_mode'], new['verification_mode']), ('AUTO', 'MANUAL'))
        with patch.object(xapi_client, 'fetch_transactions', return_value=[self.tx(old)]):
            self.qo.payment_service.reconcile_shop(1)
        self.assertEqual(self.count_orders(), 1)

    def test_token_auto_creates_one_order_from_matched_transaction(self):
        self.connect(); p = self.waiting(self.customer)
        with patch.object(xapi_client, 'fetch_transactions', return_value=[self.tx(p)]):
            self.qo.payment_service.reconcile_shop(1)
        result = self.customer.get('/api/payments/' + p['id']).get_json()
        self.assertEqual(result['state'], 'PAID')
        self.assertEqual(result['order']['payment_source'], 'XAPI')

    def test_manual_confirmation_requires_owner_and_real_bank_reference(self):
        self.save(); p = self.waiting(self.customer)
        for client, status in ((self.guest, 401), (self.customer, 403), (self.other, 403)):
            self.assertEqual(self.manual_confirm(p, client=client).status_code, status)
        self.assertEqual(self.manual_confirm(p, tid='').status_code, 400)
        response = self.manual_confirm(p)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['state'], 'PAID')
        self.assertEqual(response.get_json()['order']['payment_source'], 'MANUAL')
        self.assertEqual(len(self.owner.get('/api/orders').get_json()), 1)

    def test_duplicate_manual_click_is_idempotent_and_reference_cannot_pay_second_invoice(self):
        self.save(); a = self.waiting(); b = self.waiting(client_request_id='b' * 32)
        self.assertEqual(self.manual_confirm(a).status_code, 200)
        self.assertEqual(self.manual_confirm(a).status_code, 200)
        self.assertEqual(self.manual_confirm(b).status_code, 409)
        self.assertEqual(self.count_orders(), 1)

    def test_owner_cannot_manually_bypass_auto_verification(self):
        self.connect(); p = self.waiting()
        self.assertEqual(self.manual_confirm(p).status_code, 409)
        self.assertEqual(self.count_orders(), 0)

    def test_manual_confirmation_and_expiry_race_cannot_submit_expired_order(self):
        self.save(); p = self.waiting()
        with self.qo.db() as c:
            c.execute('UPDATE payment_checkouts SET expires_at=0')
        self.assertEqual(self.manual_confirm(p).status_code, 409)
        self.assertEqual(self.count_orders(), 0)

    def test_old_qr_uses_old_account_after_shop_changes_bank(self):
        self.connect(); old = self.waiting()
        self.connect('NEW_BANK_TOKEN', account='987654321')
        new = self.waiting(client_request_id='b' * 32)
        def history(cfg):
            if cfg['account_number'] == '123456789':
                return [self.tx(old)]
            return []
        with patch.object(xapi_client, 'fetch_transactions', side_effect=history):
            self.qo.payment_service.reconcile_shop(1)
        self.assertEqual(self.count_orders(), 1)
        self.assertEqual(new['account_number'], '987654321')
        old_result = self.guest.get('/api/payments/' + old['id'] + '?token=' + old['access_token']).get_json()
        self.assertEqual(old_result['state'], 'PAID')

    def test_worker_reconciles_without_customer_browser_request(self):
        self.connect(); p = self.waiting()
        service = self.qo.payment_service
        with patch.object(xapi_client, 'fetch_transactions', return_value=[self.tx(p)]):
            service.app.config['TESTING'] = False
            try:
                service.ensure_worker()
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline and self.count_orders() == 0:
                    time.sleep(0.05)
                self.assertEqual(self.count_orders(), 1)
                thread = service._worker
                service.ensure_worker()
                self.assertIs(service._worker, thread)
            finally:
                service.stop_worker()
                service.app.config['TESTING'] = True

    def test_worker_never_approves_a_manual_invoice(self):
        self.save(); p = self.waiting()
        with patch.object(xapi_client, 'fetch_transactions') as fetch:
            self.qo.payment_service.reconcile_shop(1)
        fetch.assert_not_called()
        self.assertEqual(self.count_orders(), 0)

    def test_manual_confirm_is_atomic_with_two_staff_sessions(self):
        self.save(); p = self.waiting()
        second = self.qo.app.test_client()
        with second.session_transaction() as session:
            session['uid'] = 1
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda client: self.manual_confirm(p, client=client).status_code, [self.owner, second]))
        self.assertEqual(results, [200, 200])
        self.assertEqual(self.count_orders(), 1)

    def test_upgrade_keeps_previous_auto_invoice_and_adds_private_connection_columns(self):
        with patch.dict(os.environ, {'XAPI_SHOP_1': json.dumps(self.cfg)}):
            p = self.waiting()
            with self.qo.db() as c:
                for column in ('connection_id', 'verification_mode'):
                    c.execute('ALTER TABLE payment_checkouts DROP COLUMN ' + column)
                for column in ('verification_method', 'confirmed_by'):
                    c.execute('ALTER TABLE payment_receipts DROP COLUMN ' + column)
            self.qo.init_db()
            row = self.guest.get('/api/payments/' + p['id'] + '?token=' + p['access_token']).get_json()
            self.assertEqual((row['id'], row['transfer_code'], row['verification_mode']), (p['id'], p['transfer_code'], 'AUTO'))
            self.assertEqual(self.count_orders(), 0)

    def test_rotated_token_reconciles_old_and_new_invoices_with_one_history_request(self):
        self.connect(); old = self.waiting()
        self.connect('ROTATED_PRIVATE_TOKEN'); new = self.waiting(client_request_id='b' * 32)
        with patch.object(xapi_client, 'fetch_transactions', return_value=[self.tx(old), self.tx(new, transactionID='BANK-002')]) as fetch:
            self.qo.payment_service.reconcile_shop(1)
        self.assertEqual(fetch.call_count, 1)
        self.assertIn('ROTATED_PRIVATE_TOKEN', fetch.call_args.args[0]['history_url'])
        self.assertEqual(self.count_orders(), 2)

    def test_saving_legacy_env_connection_without_retyping_token_migrates_it_encrypted(self):
        with patch.dict(os.environ, {'XAPI_SHOP_1': json.dumps(self.cfg)}):
            with patch.object(xapi_client, 'fetch_transactions', return_value=[]):
                result = self.save(mode='AUTO')
        self.assertEqual(result.status_code, 200)
        with self.qo.db() as c:
            settings = c.execute('SELECT * FROM shop_payment_settings WHERE shop_id=1').fetchone()
            row = c.execute('SELECT * FROM payment_connections WHERE id=?', (settings['connection_id'],)).fetchone()
            self.assertEqual(settings['mode'], 'AUTO')
            self.assertNotIn('PRIVATE_TEST_TOKEN', row['credentials_enc'])


if __name__ == '__main__':
    unittest.main()
