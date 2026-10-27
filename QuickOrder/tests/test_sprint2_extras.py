"""Kiểm thử bổ sung Sprint 2: lọc đơn theo ngày (FR-39) và tải ảnh QR thanh toán (FR-32).

Chạy từ thư mục QuickOrder:
    python -m unittest discover -s tests -v
"""
import io
import os
import sys
import tempfile
import unittest

from werkzeug.security import generate_password_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PW = "matkhau123"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def load_app(tmp):
    """Nạp lại app với CSDL và thư mục ảnh riêng cho mỗi test."""
    os.environ["QO_DB"] = os.path.join(tmp, "test.db")
    os.environ["QO_UPLOADS"] = os.path.join(tmp, "uploads")
    os.environ["SECRET_KEY"] = "test-secret"
    sys.modules.pop("app", None)
    import app as qo
    return qo


class Sprint2ExtrasTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.qo = load_app(self.tmp.name)
        self.qo.app.config["TESTING"] = True
        with self.qo.db() as c:
            cat = c.execute("SELECT id FROM categories WHERE name = 'Đồ ăn'").fetchone()[0]
            add = lambda sql, *a: c.execute(sql, a).lastrowid
            self.owner_a = add("INSERT INTO users(full_name, email, password_hash, role) VALUES ('A', 'a@quan.vn', ?, 'owner')", generate_password_hash(PW))
            self.owner_b = add("INSERT INTO users(full_name, email, password_hash, role) VALUES ('B', 'b@quan.vn', ?, 'owner')", generate_password_hash(PW))
            self.shop = add("INSERT INTO shops(owner_id, name, address, phone, open_time, close_time, status) VALUES (?, 'Quán A', 'Đ1', '0900000000', '00:00', '24:00', 'APPROVED')", self.owner_a)
            self.dish = add("INSERT INTO dishes(shop_id, category_id, name, price) VALUES (?, ?, 'Phở', 40000)", self.shop, cat)

    def login(self, email):
        client = self.qo.app.test_client()
        self.assertEqual(client.post("/api/login", json={"email": email, "password": PW}).status_code, 200)
        return client

    def add_order(self, created_utc):
        with self.qo.db() as c:
            oid = c.execute("INSERT INTO orders(shop_id, status, total_amount, created_at) VALUES (?, 'PENDING', 40000, ?)",
                            (self.shop, created_utc)).lastrowid
            c.execute("INSERT INTO order_items(order_id, dish_id, quantity, unit_price) VALUES (?, ?, 1, 40000)", (oid, self.dish))
        return oid

    # ----- lọc theo ngày (giờ Việt Nam) -----
    def test_filter_orders_by_day_uses_vietnam_time(self):
        a = self.add_order("2026-10-21 16:59:00")     # 23:59 ngày 21/10 theo giờ VN
        b = self.add_order("2026-10-21 17:00:00")     # 00:00 ngày 22/10 theo giờ VN
        c = self.add_order("2026-10-22 16:59:00")     # 23:59 ngày 22/10
        owner = self.login("a@quan.vn")
        ids = lambda qs: [o["id"] for o in owner.get("/api/orders?" + qs).get_json()]
        self.assertEqual(ids("from=2026-10-22&to=2026-10-22"), [c, b])
        self.assertEqual(ids("from=2026-10-21&to=2026-10-21"), [a])
        self.assertEqual(ids("from=2026-10-22"), [c, b])       # chỉ có "từ ngày"
        self.assertEqual(ids("to=2026-10-21"), [a])            # chỉ có "đến ngày"

    def test_filter_orders_rejects_bad_dates(self):
        owner = self.login("a@quan.vn")
        for qs in ("from=abc", "from=2026-13-01", "from=2026-10-05&to=2026-10-01"):
            with self.subTest(qs=qs):
                self.assertEqual(owner.get("/api/orders?" + qs).status_code, 400)

    # ----- ảnh QR thanh toán -----
    def upload(self, client, data, name="qr.png", shop=None):
        return client.post(f"/api/shops/{shop or self.shop}/qr", data={"file": (io.BytesIO(data), name)},
                           content_type="multipart/form-data")

    def test_owner_uploads_qr_and_it_is_served(self):
        owner = self.login("a@quan.vn")
        resp = self.upload(owner, PNG)
        self.assertEqual(resp.status_code, 200)
        url = resp.get_json()["payment_qr_image"]
        self.assertRegex(url, r"^/uploads/[0-9a-f]{32}\.png$")
        got = self.qo.app.test_client().get(url)               # khách (chưa đăng nhập) xem được để chuyển khoản
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.data, PNG)
        self.assertEqual(got.headers["X-Content-Type-Options"], "nosniff")

    def test_new_upload_replaces_and_removes_old_file(self):
        owner = self.login("a@quan.vn")
        first = self.upload(owner, PNG).get_json()["payment_qr_image"]
        second = self.upload(owner, JPG, "qr.jpg").get_json()["payment_qr_image"]
        self.assertNotEqual(first, second)
        client = self.qo.app.test_client()
        self.assertEqual(client.get(first).status_code, 404)
        self.assertEqual(client.get(second).status_code, 200)

    def test_only_real_images_are_accepted(self):
        owner = self.login("a@quan.vn")
        self.assertEqual(self.upload(owner, b"<svg onload=alert(1)>", "x.png").status_code, 400)   # đuôi .png nhưng nội dung không phải ảnh
        self.assertEqual(self.upload(owner, PNG + b"\x00" * 1_000_001).status_code, 400)             # quá 1 MB
        self.assertEqual(owner.post(f"/api/shops/{self.shop}/qr", data={}, content_type="multipart/form-data").status_code, 400)

    def test_upload_permissions(self):
        self.assertEqual(self.upload(self.qo.app.test_client(), PNG).status_code, 401)
        self.assertEqual(self.upload(self.login("b@quan.vn"), PNG).status_code, 403)

    def test_uploaded_file_route_rejects_odd_names(self):
        client = self.qo.app.test_client()
        for name in ("..%2Fapp.py", "abc.png", "a" * 32 + ".svg", "A" * 32 + ".png"):
            with self.subTest(name=name):
                self.assertEqual(client.get("/uploads/" + name).status_code, 404)


if __name__ == "__main__":
    unittest.main()
