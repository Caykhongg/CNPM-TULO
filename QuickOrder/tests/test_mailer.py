"""Brevo: kiểm thử bằng HTTP giả lập, không gửi email thật."""
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Import sau khi đã cài requirements; không dùng khóa thật trong các test.
import mailer
import check_brevo

FAKE_KEY = "fake-brevo-key-for-tests"
CODE = "123456"
ENV = {"MAIL_API_KEY": FAKE_KEY, "MAIL_FROM": "sender@example.com", "MAIL_CONSOLE": "0"}


def fake_response(status=201, body=b'{"messageId":"test-message-id"}'):
    response = MagicMock()
    response.__enter__.return_value = response
    response.getcode.return_value = status
    response.read.return_value = body
    return response


class MailerTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, ENV, clear=True)
        env.start()
        self.addCleanup(env.stop)
        transport = patch.object(mailer.urllib.request, "urlopen", return_value=fake_response())
        self.http = transport.start()
        self.addCleanup(transport.stop)

    def test_https_request_payload_and_message_id(self):
        self.assertEqual(mailer.send_code("customer@example.com", CODE), "test-message-id")
        request = self.http.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Api-key"), FAKE_KEY)
        payload = json.loads(request.data)
        self.assertEqual(payload["sender"]["email"], "sender@example.com")
        self.assertEqual(payload["to"], [{"email": "customer@example.com"}])
        self.assertIn(CODE, payload["textContent"])
        self.assertIn(CODE, payload["htmlContent"])

    def test_missing_configuration_stops_before_network(self):
        os.environ.pop("MAIL_API_KEY")
        with self.assertRaises(mailer.MailError) as error:
            mailer.send_code("customer@example.com", CODE)
        self.assertEqual(error.exception.diagnostic, "MAIL_NOT_CONFIGURED")
        self.http.assert_not_called()

    def test_whitespace_trimmed(self):
        os.environ["MAIL_API_KEY"] = "  " + FAKE_KEY + "\n"
        os.environ["MAIL_FROM"] = " sender@example.com "
        mailer.send_code("customer@example.com", CODE)
        self.assertEqual(self.http.call_args.args[0].get_header("Api-key"), FAKE_KEY)

    def test_aliases_supported(self):
        os.environ.pop("MAIL_API_KEY")
        os.environ.pop("MAIL_FROM")
        os.environ.update(BREVO_API_KEY=FAKE_KEY, BREVO_SENDER_EMAIL="alias@example.com")
        mailer.send_code("customer@example.com", CODE)
        self.assertEqual(json.loads(self.http.call_args.args[0].data)["sender"]["email"], "alias@example.com")

    def test_environment_changes_are_not_cached(self):
        mailer.send_code("customer@example.com", CODE)
        os.environ["MAIL_FROM"] = "new@example.com"
        mailer.send_code("customer@example.com", CODE)
        self.assertEqual(json.loads(self.http.call_args.args[0].data)["sender"]["email"], "new@example.com")

    def test_console_mode_does_not_send(self):
        os.environ["MAIL_CONSOLE"] = "1"
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertIsNone(mailer.send_code("customer@example.com", CODE))
        self.assertIn(CODE, output.getvalue())
        self.http.assert_not_called()

    def test_http_error_has_diagnostic_without_secret_in_logs(self):
        body = json.dumps({"code": "unauthorized", "message": FAKE_KEY + " " + CODE}).encode()
        self.http.side_effect = urllib.error.HTTPError(mailer.API_URL, 401, "Unauthorized", {}, io.BytesIO(body))
        with self.assertLogs("mailer", level="ERROR") as logs, self.assertRaises(mailer.MailError) as error:
            mailer.send_code("customer@example.com", CODE)
        self.assertEqual(error.exception.diagnostic, "BREVO_HTTP_401")
        self.assertNotIn(FAKE_KEY, str(logs.output))
        self.assertNotIn(CODE, str(logs.output))
        self.assertNotIn("unauthorized", str(error.exception))

    def test_timeout_reported_as_connection_failure(self):
        self.http.side_effect = TimeoutError("timeout")
        with self.assertRaises(mailer.MailError) as error:
            mailer.send_code("customer@example.com", CODE)
        self.assertEqual(error.exception.diagnostic, "BREVO_CONNECTION_FAILED")

    def test_invalid_inputs_stop_before_network(self):
        for to, code in [("invalid", CODE), ("customer@example.com", "abc"), ("customer@example.com", 123456)]:
            with self.assertRaises(mailer.MailError):
                mailer.send_code(to, code)
        self.http.assert_not_called()

    def test_invalid_sender_configuration(self):
        os.environ["MAIL_FROM"] = "invalid"
        with self.assertRaises(mailer.MailError) as error:
            mailer.send_code("customer@example.com", CODE)
        self.assertEqual(error.exception.diagnostic, "MAIL_FROM_INVALID")
        self.http.assert_not_called()

    def test_unexpected_http_status_is_not_success(self):
        self.http.return_value = fake_response(202)
        with self.assertRaises(mailer.MailError) as error:
            mailer.send_code("customer@example.com", CODE)
        self.assertEqual(error.exception.diagnostic, "BREVO_UNEXPECTED_RESPONSE")

    def test_accepted_without_message_id_does_not_resend(self):
        self.http.return_value = fake_response(201, b'')
        self.assertIsNone(mailer.send_code("customer@example.com", CODE))
        self.assertEqual(self.http.call_count, 1)

    def test_diagnostic_without_recipient_makes_no_api_call(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(check_brevo.main([]), 0)
        self.assertNotIn(FAKE_KEY, output.getvalue())
        self.http.assert_not_called()

    def test_diagnostic_refuses_console_for_real_send(self):
        os.environ["MAIL_CONSOLE"] = "1"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check_brevo.main(["--to", "customer@example.com"]), 2)
        self.http.assert_not_called()

    def test_diagnostic_send_reports_message_id_not_otp(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(check_brevo.main(["--to", "customer@example.com"]), 0)
        sent_code = re.search(r"\b\d{6}\b", json.loads(self.http.call_args.args[0].data)["textContent"])[0]
        self.assertIn("test-message-id", output.getvalue())
        self.assertNotIn(sent_code, output.getvalue())
        self.assertNotIn(FAKE_KEY, output.getvalue())


class SignupBrevoIntegrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {**ENV, "QO_DB": str(Path(tmp.name)/"signup.db"), "SECRET_KEY": "mailer-test"}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        sys.modules.pop("app", None)
        import app
        self.qo = app
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()
        self.body = {"email": "new.customer@example.com", "full_name": "Khách thử", "phone": "0912345678", "password": "LocalTest@123"}
        transport = patch.object(mailer.urllib.request, "urlopen", return_value=fake_response())
        self.http = transport.start()
        self.addCleanup(transport.stop)

    def test_register_send_verify_uses_same_code(self):
        response = self.client.post("/api/customer/signup", json=self.body)
        self.assertEqual(response.status_code, 200, response.get_json())
        code = re.search(r"\b\d{6}\b", json.loads(self.http.call_args.args[0].data)["textContent"])[0]
        r = self.client.post("/api/customer/verify", json={"email": self.body["email"], "code": code})
        self.assertEqual(r.status_code, 201, r.get_json())
        self.assertEqual(self.client.get("/api/me").get_json()["role"], "customer")

    def test_provider_failure_allows_immediate_retry(self):
        self.http.side_effect = urllib.error.HTTPError(mailer.API_URL, 400, "Bad Request", {}, io.BytesIO(b'{"code":"invalid_parameter","message":"sender invalid"}'))
        r = self.client.post("/api/customer/signup", json=self.body)
        self.assertEqual(r.status_code, 502)
        self.assertNotIn("sender invalid", r.get_json()["error"])
        with self.qo.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM pending_signups").fetchone()[0], 0)
        self.http.side_effect = None
        self.assertEqual(self.client.post("/api/customer/signup", json=self.body).status_code, 200)


if __name__ == "__main__":
    unittest.main()
