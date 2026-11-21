"""Đối soát ACB raw data: giữ xác nhận codeStatus, chiều tiền, tiền tệ và tài khoản."""
import io
import json
import os
import unittest
from unittest.mock import patch, MagicMock

import test_xapi_payments as fixtures
import bank_connections
import xapi_client

CONFIG = {'history_url': 'https://id.xapi.vn/historyapiacb/PRIVATE_TEST_TOKEN',
          'bank_bin': '970416', 'account_number': '123456789'}


def transaction(**changes):
    row = {'transactionID': 'ACB-001', 'rawTransactionID': 'RAW-001', 'transactionNumber': '1001',
           'amount': 90000, 'description': 'THANH TOAN QO1234567890ABCDEF', 'type': 'IN',
           'currency': 'VND', 'account': '123456789'}
    row.update(changes)
    return row


def response(rows, **changes):
    value = {'codeStatus': 200, 'data': rows, 'description': '', 'source': 'test', 'fallback': False}
    value.update(changes)
    return value


def http_payload(data):
    opener = MagicMock()
    stream = opener.open.return_value.__enter__.return_value
    stream.status = 200
    stream.read.return_value = json.dumps(data).encode()
    return patch.object(xapi_client.urllib.request, 'build_opener', return_value=opener)


class AcbAdapterTests(unittest.TestCase):
    def test_acb_plain_token_builds_endpoint_observed_in_user_diagnostic(self):
        self.assertEqual(bank_connections.from_input('PRIVATE_TEST_TOKEN', '970416'), CONFIG['history_url'])

    def test_acb_data_is_normalized_and_outgoing_is_never_a_payment(self):
        rows = xapi_client.parse_history(response([transaction(), transaction(type='OUT', transactionID='ACB-002')]), CONFIG)
        self.assertEqual(rows[0]['transactionID'], 'ACB-001')
        self.assertEqual(xapi_client.incoming(rows[0])['amount'], 90000)
        self.assertIsNone(xapi_client.incoming(rows[1]))

    def test_http_200_does_not_override_failed_bank_status(self):
        for code in (401, 403, 500, True, '200', 200.0, None):
            with self.subTest(code=code):
                with self.assertRaises(xapi_client.PaymentError):
                    xapi_client.parse_history(response([transaction()], codeStatus=code), CONFIG)

    def test_conflicting_status_or_wrong_bank_is_rejected(self):
        with self.assertRaises(xapi_client.PaymentError):
            xapi_client.parse_history(response([transaction()], status='error'), CONFIG)
        with self.assertRaises(xapi_client.PaymentError):
            xapi_client.parse_history(response([transaction()]), {**CONFIG, 'bank_bin': '970423'})
        with self.assertRaises(xapi_client.PaymentError):
            xapi_client.parse_history({'status': 'success', 'transactions': [], 'codeStatus': 401}, CONFIG)

    def test_unsupported_direction_is_rejected_instead_of_guessed(self):
        for direction in ('CREDIT', 'DEBIT', '1', None, ''):
            with self.assertRaises(xapi_client.PaymentError):
                xapi_client.parse_history(response([transaction(type=direction)]), CONFIG)

    def test_foreign_currency_or_different_account_is_rejected(self):
        for row in (transaction(currency='USD'), transaction(account='987654321')):
            with self.assertRaises(xapi_client.PaymentError):
                xapi_client.parse_history(response([row]), CONFIG)

    def test_native_transaction_number_can_be_used_when_gateway_id_missing(self):
        row = transaction(transactionID=None, rawTransactionID=None, transactionNumber=12345)
        self.assertEqual(xapi_client.parse_history(response([row]), CONFIG)[0]['transactionID'], '12345')

    def test_negative_incoming_is_not_turned_into_positive_money(self):
        row = xapi_client.parse_history(response([transaction(amount=-90000)]), CONFIG)[0]
        self.assertIsNone(xapi_client.incoming(row))

    def test_empty_history_is_supported_but_null_history_is_not(self):
        self.assertEqual(xapi_client.parse_history(response([]), CONFIG), [])
        with self.assertRaises(xapi_client.PaymentError):
            xapi_client.parse_history(response(None), CONFIG)

    def test_only_acb_endpoint_accepts_acb_response(self):
        with self.assertRaises(xapi_client.PaymentError):
            xapi_client.parse_history(response([]), {**CONFIG, 'history_url': 'https://id.xapi.vn/historyapitpbv2/TOKEN'})

    def test_http_transport_uses_acb_adapter_and_keeps_standard_format(self):
        with http_payload(response([transaction()])):
            self.assertEqual(xapi_client.fetch_transactions(CONFIG)[0]['transactionID'], 'ACB-001')
        standard = {'status': 'success', 'transactions': [transaction()]}
        self.assertEqual(xapi_client.parse_history(standard, CONFIG), standard['transactions'])


class AcbPaymentFlowTests(unittest.TestCase):
    create = fixtures.PaymentTests.create
    waiting = fixtures.PaymentTests.waiting
    count_orders = fixtures.PaymentTests.count_orders

    def setUp(self):
        fixtures.PaymentTests.setUp(self)
        config = patch.dict(os.environ, {'XAPI_SHOP_1': '', 'SECRET_KEY': 'acb-tests-fixed-secret-key-at-least-32-characters'})
        config.start(); self.addCleanup(config.stop)

    def connect(self, data):
        with http_payload(data):
            return self.owner.put('/api/shops/1/payment-config', json={
                'bank_bin': '970416', 'account_number': '123456789', 'account_name': 'NGUYEN VAN A',
                'credential': 'PRIVATE_TEST_TOKEN', 'mode': 'AUTO'})

    def test_acb_bank_can_connect_and_create_one_paid_order_from_raw_response(self):
        connected = self.connect(response([]))
        self.assertEqual(connected.status_code, 200, connected.get_json())
        p = self.waiting(self.customer)
        rows = [transaction(description=p['transfer_code']), transaction(type='OUT', transactionID='ACB-OUT', description=p['transfer_code'])]
        with http_payload(response(rows)):
            self.qo.payment_service.reconcile_shop(1)
            with self.qo.db() as c:
                c.execute('DELETE FROM payment_source_locks')
            self.qo.payment_service.reconcile_shop(1)
        result = self.customer.get('/api/payments/' + p['id']).get_json()
        self.assertEqual(result['state'], 'PAID')
        self.assertEqual(result['order']['payment_source'], 'XAPI')
        self.assertEqual(self.count_orders(), 1)

    def test_acb_failed_status_never_saves_auto_configuration(self):
        result = self.connect(response([transaction()], codeStatus=401))
        self.assertEqual(result.status_code, 400)
        self.assertEqual(self.owner.get('/api/shops/1/payment-config').get_json()['mode'], 'MANUAL')

    def test_acb_outgoing_never_submits_an_order(self):
        self.assertEqual(self.connect(response([])).status_code, 200)
        p = self.waiting()
        with http_payload(response([transaction(type='OUT', description=p['transfer_code'])])):
            self.qo.payment_service.reconcile_shop(1)
        self.assertEqual(self.count_orders(), 0)


if __name__ == '__main__':
    unittest.main()
