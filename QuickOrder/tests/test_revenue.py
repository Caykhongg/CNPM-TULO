"""Kiểm thử thống kê doanh thu (SRS FR-47, FR-48).

Chạy từ thư mục QuickOrder:
    python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PW = "matkhau123"
VN = timezone(timedelta(hours=7))


def load_app(db_path):
    """Nạp lại app với một CSDL riêng cho mỗi test."""
    os.environ["QO_DB"] = db_path
    os.environ["SECRET_KEY"] = "test-secret"
    sys.modules.pop("app", None)
    import app as qo
    return qo


class RevenueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.qo = load_app(os.path.join(self.tmp.name, "test.db"))
        self.qo.app.config["TESTING"] = True
        self.seed()

    # ----- dữ liệu mẫu -----
    def seed(self):
        with self.qo.db() as c:
            cat = c.execute("SELECT id FROM categories WHERE name = 'Đồ ăn'").fetchone()[0]

            def add(sql, *args):
                return c.execute(sql, args).lastrowid

            self.owner = add("INSERT INTO users(full_name, email, password_hash, role) VALUES ('Chủ A', 'a@quan.vn', ?, 'owner')", generate_password_hash(PW))
            add("INSERT INTO users(full_name, email, password_hash, role) VALUES ('Chủ B', 'b@quan.vn', ?, 'owner')", generate_password_hash(PW))
            self.shop = add("INSERT INTO shops(owner_id, name, address, phone, open_time, close_time, status) VALUES (?, 'Quán A', 'Đường 1', '0900000000', '00:00', '24:00', 'APPROVED')", self.owner)
            self.tea = add("INSERT INTO dishes(shop_id, category_id, name, price) VALUES (?, ?, 'Trà sữa', 50000)", self.shop, cat)
            self.pho = add("INSERT INTO dishes(shop_id, category_id, name, price) VALUES (?, ?, 'Phở', 40000)", self.shop, cat)

    def add_order(self, created_utc, status, items):
        """Thêm đơn trực tiếp, giờ tạo tính theo UTC (đúng như cột created_at).
        items: danh sách (dish_id, số lượng, đơn giá)."""
        total = sum(q * p for _, q, p in items)
        with self.qo.db() as c:
            oid = c.execute(
                "INSERT INTO orders(shop_id, status, total_amount, created_at, customer_name) VALUES (?, ?, ?, ?, 'Khách')",
                (self.shop, status, total, created_utc)).lastrowid
            for dish, qty, price in items:
                c.execute("INSERT INTO order_items(order_id, dish_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                          (oid, dish, qty, price))
        return oid

    def login(self, email):
        client = self.qo.app.test_client()
        resp = client.post("/api/login", json={"email": email, "password": PW})
        self.assertEqual(resp.status_code, 200, resp.get_json())
        return client

    def stats(self, client, **params):
        resp = client.get("/api/revenue", query_string={"shop_id": self.shop, **params})
        self.assertEqual(resp.status_code, 200, resp.get_json())
        return resp.get_json()

    # ----- quyền truy cập -----
    def test_chi_chu_quan_moi_xem_duoc(self):
        guest = self.qo.app.test_client()
        self.assertIn(guest.get("/api/revenue", query_string={"shop_id": self.shop}).status_code, (401, 403))
        self.assertEqual(self.login("b@quan.vn").get("/api/revenue", query_string={"shop_id": self.shop}).status_code, 403)
        self.assertEqual(self.login("a@quan.vn").get("/api/revenue", query_string={"shop_id": 9999}).status_code, 404)

    # ----- quy tắc tính doanh thu -----
    def test_chi_don_hoan_thanh_duoc_tinh_doanh_thu(self):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self.add_order(now, "COMPLETED", [(self.tea, 2, 60000)])     # 120.000
        self.add_order(now, "COMPLETED", [(self.pho, 1, 40000)])     # 40.000
        self.add_order(now, "PENDING", [(self.tea, 1, 50000)])
        self.add_order(now, "PREPARING", [(self.tea, 1, 50000)])
        self.add_order(now, "CANCELLED", [(self.pho, 3, 40000)])
        # Đơn đang chờ từ ba ngày trước vẫn phải được đếm trong "đang chờ" hiện tại
        old = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        self.add_order(old, "PENDING", [(self.pho, 1, 40000)])

        d = self.stats(self.login("a@quan.vn"), range="today")
        self.assertEqual(d["summary"], {"orders": 5, "completed": 2, "cancelled": 1, "revenue": 160000, "average": 80000})
        self.assertEqual(d["now"], {"pending": 2, "working": 1})

    def test_ngay_theo_gio_viet_nam(self):
        # 17:30 UTC ngày 21/10 là 00:30 ngày 22/10 theo giờ Việt Nam
        self.add_order("2026-10-21 17:30:00", "COMPLETED", [(self.tea, 1, 50000)])
        # 16:59 UTC ngày 21/10 là 23:59 cùng ngày 21/10
        self.add_order("2026-10-21 16:59:00", "COMPLETED", [(self.tea, 1, 50000)])
        d = self.stats(self.login("a@quan.vn"), **{"from": "2026-10-21", "to": "2026-10-22"})
        by_day = {p["key"]: p for p in d["series"]}
        self.assertEqual(by_day["2026-10-21"]["completed"], 1)
        self.assertEqual(by_day["2026-10-22"]["completed"], 1)

    def test_bieu_do_co_du_cac_ngay(self):
        self.add_order("2026-10-22 03:00:00", "COMPLETED", [(self.tea, 1, 50000)])   # 10:00 VN ngày 22/10
        d = self.stats(self.login("a@quan.vn"), **{"from": "2026-10-20", "to": "2026-10-23"}, group="day")
        self.assertEqual([p["key"] for p in d["series"]], ["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"])
        self.assertEqual([p["revenue"] for p in d["series"]], [0, 0, 50000, 0])

    def test_nhom_theo_thang(self):
        self.add_order("2026-09-30 18:00:00", "COMPLETED", [(self.tea, 1, 50000)])   # 01:00 VN ngày 01/10 -> tháng 10
        self.add_order("2026-10-15 03:00:00", "COMPLETED", [(self.pho, 2, 40000)])   # 80.000
        d = self.stats(self.login("a@quan.vn"), **{"from": "2026-09-15", "to": "2026-11-02"}, group="month")
        self.assertEqual([p["key"] for p in d["series"]], ["2026-09", "2026-10", "2026-11"])
        self.assertEqual([p["completed"] for p in d["series"]], [0, 2, 0])
        self.assertEqual([p["revenue"] for p in d["series"]], [0, 130000, 0])

    def test_mon_ban_chay_xep_theo_so_luong(self):
        self.add_order("2026-10-10 03:00:00", "COMPLETED", [(self.pho, 2, 40000), (self.tea, 1, 50000)])
        self.add_order("2026-10-11 03:00:00", "COMPLETED", [(self.tea, 4, 50000)])
        self.add_order("2026-10-11 04:00:00", "CANCELLED", [(self.pho, 30, 40000)])   # đơn hủy không tính
        d = self.stats(self.login("a@quan.vn"), **{"from": "2026-10-01", "to": "2026-10-31"})
        self.assertEqual([(x["name"], x["quantity"], x["revenue"]) for x in d["dishes"]],
                         [("Trà sữa", 5, 250000), ("Phở", 2, 80000)])

    # ----- khoảng thời gian -----
    def test_moc_thoi_gian_theo_gio_viet_nam(self):
        client = self.login("a@quan.vn")
        today = datetime.now(VN).date()
        d = self.stats(client, range="today")
        self.assertEqual((d["from"], d["to"]), (today.isoformat(), today.isoformat()))
        self.assertEqual(self.stats(client, range="7d")["from"], (today - timedelta(days=6)).isoformat())
        self.assertEqual(self.stats(client, range="30d")["from"], (today - timedelta(days=29)).isoformat())
        self.assertEqual(self.stats(client, range="month")["from"], today.replace(day=1).isoformat())

    def test_gioi_han_khoang_366_ngay(self):
        client = self.login("a@quan.vn")
        self.stats(client, **{"from": "2026-01-01", "to": "2027-01-01"})   # đúng 366 ngày
        resp = client.get("/api/revenue", query_string={"shop_id": self.shop, "from": "2026-01-01", "to": "2027-01-02"})
        self.assertEqual(resp.status_code, 400)

    def test_tham_so_sai_bi_tu_choi(self):
        client = self.login("a@quan.vn")
        bad = [
            {},                                                         # thiếu shop_id
            {"shop_id": "abc", "range": "today"},
            {"shop_id": self.shop, "range": "năm"},
            {"shop_id": self.shop, "group": "year"},
            {"shop_id": self.shop, "from": "2026-10-01"},               # thiếu đến ngày
            {"shop_id": self.shop, "from": "2026-10-05", "to": "2026-10-01"},
            {"shop_id": self.shop, "from": "2026-13-01", "to": "2026-13-02"},
        ]
        for params in bad:
            with self.subTest(params=params):
                self.assertEqual(client.get("/api/revenue", query_string=params).status_code, 400)


if __name__ == "__main__":
    unittest.main()
