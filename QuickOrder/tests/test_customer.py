"""Kiểm thử đăng ký khách hàng có xác nhận email, và hồ sơ khách.

Chạy từ thư mục QuickOrder:
    python -m unittest discover -s tests -v
(pytest cũng chạy được các test này.)
"""
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

EMAIL = "an@example.com"
PASSWORD = "matkhau123"


def load_app(db_path):
    """Nạp lại app với một CSDL riêng, để mỗi test bắt đầu từ dữ liệu trống."""
    os.environ["QO_DB"] = db_path
    os.environ["SECRET_KEY"] = "test-secret"
    sys.modules.pop("app", None)
    import app as qo
    return qo


class CustomerSignupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.qo = load_app(os.path.join(self.tmp.name, "test.db"))
        self.qo.app.config["TESTING"] = True
        self.client = self.qo.app.test_client()
        self.sent = {}
        patcher = mock.patch.object(
            self.qo.mailer, "send_code",
            side_effect=lambda to, code: self.sent.__setitem__(to, code))
        patcher.start()
        self.addCleanup(patcher.stop)

    # ----- tiện ích -----
    def signup(self, email=EMAIL, **extra):
        body = {"full_name": "Nguyễn Văn An", "phone": "0912345678", "email": email, "password": PASSWORD}
        body.update(extra)
        return self.client.post("/api/customer/signup", json=body)

    def verify(self, code, email=EMAIL):
        return self.client.post("/api/customer/verify", json={"email": email, "code": code})

    def resend(self, email=EMAIL):
        return self.client.post("/api/customer/resend", json={"email": email})

    def db_row(self, sql, *args):
        with self.qo.db() as c:
            return c.execute(sql, args).fetchone()

    def set_pending(self, **cols):
        """Sửa trực tiếp dòng chờ xác nhận để giả lập thời gian trôi qua."""
        with self.qo.db() as c:
            for name, value in cols.items():
                c.execute(f"UPDATE pending_signups SET {name} = ? WHERE email = ?", (value, EMAIL))

    def wrong_code_for(self):
        return "000000" if self.sent[EMAIL] != "000000" else "111111"

    def count_users(self, email=EMAIL):
        return self.db_row("SELECT COUNT(*) FROM users WHERE email = ?", email)[0]

    # ----- đăng ký và xác nhận -----
    def test_signup_sends_code_but_creates_no_account_yet(self):
        resp = self.signup()
        self.assertEqual(resp.status_code, 200)
        self.assertIn(EMAIL, self.sent)
        self.assertEqual(len(self.sent[EMAIL]), 6)
        self.assertEqual(self.count_users(), 0)

    def test_correct_code_creates_customer_and_logs_in(self):
        self.signup()
        resp = self.verify(self.sent[EMAIL])
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["role"], "customer")
        me = self.client.get("/api/me").get_json()
        self.assertEqual(me["email"], EMAIL)
        self.assertEqual(me["full_name"], "Nguyễn Văn An")
        self.assertEqual(me["phone"], "0912345678")
        self.assertIsNone(self.db_row("SELECT 1 FROM pending_signups WHERE email = ?", EMAIL))

    def test_code_is_stored_as_hash_only(self):
        self.signup()
        row = self.db_row("SELECT code_hash, password_hash FROM pending_signups WHERE email = ?", EMAIL)
        self.assertNotIn(self.sent[EMAIL], row["code_hash"])
        self.assertNotEqual(row["password_hash"], PASSWORD)

    def test_five_wrong_codes_lock_until_resend(self):
        self.signup()
        for _ in range(5):
            self.assertEqual(self.verify(self.wrong_code_for()).status_code, 400)
        # Lần thứ 6 bị chặn ngay cả khi nhập đúng mã
        self.assertEqual(self.verify(self.sent[EMAIL]).status_code, 429)
        self.assertEqual(self.count_users(), 0)

    def test_expired_code_is_rejected(self):
        self.signup()
        self.set_pending(expires_at=int(time.time()) - 1)
        resp = self.verify(self.sent[EMAIL])
        self.assertEqual(resp.status_code, 400)
        self.assertIn("hết hạn", resp.get_json()["error"])
        self.assertEqual(self.count_users(), 0)

    def test_malformed_code_is_rejected_without_counting_try(self):
        self.signup()
        self.assertEqual(self.verify("12345").status_code, 400)
        self.assertEqual(self.verify("abcdef").status_code, 400)
        self.assertEqual(self.db_row("SELECT tries FROM pending_signups WHERE email = ?", EMAIL)["tries"], 0)

    def test_code_for_unknown_email_gives_same_error(self):
        resp = self.verify("123456", email="khong-co@example.com")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("không đúng", resp.get_json()["error"])

    def test_verify_uses_code_only_once(self):
        self.signup()
        code = self.sent[EMAIL]
        self.assertEqual(self.verify(code).status_code, 201)
        self.client.post("/api/logout")
        self.assertEqual(self.verify(code).status_code, 400)

    # ----- gửi lại mã và giới hạn -----
    def test_resend_within_60_seconds_is_refused(self):
        self.signup()
        resp = self.resend()
        self.assertEqual(resp.status_code, 429)
        self.assertIn("giây", resp.get_json()["error"])

    def test_resend_after_wait_issues_new_code_and_resets_tries(self):
        self.signup()
        self.verify(self.wrong_code_for())
        self.set_pending(last_sent_at=int(time.time()) - 61)
        self.assertEqual(self.resend().status_code, 200)
        self.assertEqual(self.db_row("SELECT tries FROM pending_signups WHERE email = ?", EMAIL)["tries"], 0)
        self.assertEqual(self.verify(self.sent[EMAIL]).status_code, 201)

    def test_at_most_five_codes_per_hour(self):
        self.signup()                                  # lần 1
        for _ in range(4):                             # lần 2 đến 5
            self.set_pending(last_sent_at=int(time.time()) - 61)
            self.assertEqual(self.resend().status_code, 200)
        self.set_pending(last_sent_at=int(time.time()) - 61)
        resp = self.resend()                           # lần 6 trong cùng 1 giờ
        self.assertEqual(resp.status_code, 429)
        self.assertIn("1 giờ", resp.get_json()["error"])

    def test_resend_for_unknown_email_sends_nothing(self):
        resp = self.resend("khong-dang-ky@example.com")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("khong-dang-ky@example.com", self.sent)

    # ----- email đã có tài khoản và lỗi gửi thư -----
    def test_existing_account_gets_no_code_and_same_message(self):
        with self.qo.db() as c:
            c.execute("INSERT INTO users (full_name, email, password_hash, role) VALUES ('Cũ', ?, 'x', 'customer')",
                      (EMAIL,))
        resp = self.signup()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["message"], self.qo.SENT_MSG)
        self.assertNotIn(EMAIL, self.sent)

    def test_mail_failure_returns_502(self):
        with mock.patch.object(self.qo.mailer, "send_code",
                               side_effect=self.qo.mailer.MailError("Không gửi được email.")):
            resp = self.signup()
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(resp.get_json()["error"], "Không gửi được email.")

    def test_invalid_input_is_rejected(self):
        self.assertEqual(self.signup(password="ngan").status_code, 400)            # dưới 8 ký tự
        self.assertEqual(self.signup(email="khong-phai-email").status_code, 400)
        self.assertEqual(self.signup(phone="abc").status_code, 400)
        self.assertEqual(self.signup(full_name="   ").status_code, 400)
        self.assertNotIn(EMAIL, self.sent)

    # ----- hồ sơ -----
    def test_logged_in_customer_can_update_name_and_phone(self):
        self.signup()
        self.verify(self.sent[EMAIL])
        resp = self.client.put("/api/me", json={"full_name": "Trần Thị Bình", "phone": "098 765 4321"})
        self.assertEqual(resp.status_code, 200)
        me = resp.get_json()
        self.assertEqual(me["full_name"], "Trần Thị Bình")
        self.assertEqual(me["phone"], "0987654321")

    def test_profile_update_cannot_change_role_or_email(self):
        self.signup()
        self.verify(self.sent[EMAIL])
        resp = self.client.put("/api/me", json={
            "full_name": "Ai Đó", "phone": "0988888888", "role": "admin", "email": "hack@example.com"})
        self.assertEqual(resp.status_code, 200)
        me = resp.get_json()
        self.assertEqual(me["role"], "customer")
        self.assertEqual(me["email"], EMAIL)

    def test_profile_update_rejects_invalid_phone(self):
        self.signup()
        self.verify(self.sent[EMAIL])
        self.assertEqual(self.client.put("/api/me", json={"full_name": "A", "phone": "12"}).status_code, 400)

    def test_guest_cannot_update_profile(self):
        self.assertEqual(self.client.put("/api/me", json={"full_name": "A", "phone": "0912345678"}).status_code, 401)

    def test_customer_can_log_in_again_with_password(self):
        self.signup()
        self.verify(self.sent[EMAIL])
        self.client.post("/api/logout")
        resp = self.client.post("/api/login", json={"email": EMAIL, "password": PASSWORD})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["role"], "customer")

    def test_customer_cannot_use_owner_or_admin_api(self):
        self.signup()
        self.verify(self.sent[EMAIL])
        self.assertEqual(self.client.post("/api/shops", json={"name": "Quán giả"}).status_code, 403)
        self.assertEqual(self.client.post("/api/categories", json={"name": "Lạ"}).status_code, 403)
        self.assertEqual(self.client.get("/api/users").status_code, 405)


class OldDatabaseTests(unittest.TestCase):
    def test_existing_database_gets_pending_table_on_startup(self):
        """CSDL đã có từ trước vẫn được tạo thêm bảng đăng ký mới khi khởi động."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "old.db")
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                         "full_name TEXT NOT NULL DEFAULT '', email TEXT NOT NULL UNIQUE COLLATE NOCASE, "
                         "phone TEXT, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'owner', "
                         "is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            conn.commit()
            conn.close()
            qo = load_app(path)
            with qo.db() as c:
                tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertIn("pending_signups", tables)


if __name__ == "__main__":
    unittest.main()
