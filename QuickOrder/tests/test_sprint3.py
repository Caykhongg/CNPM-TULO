"""Kiểm thử Sprint 3 nhóm chủ quán: mã giảm giá (FR-46, FR-23), tính tiền theo bàn (FR-45), đánh giá (FR-24, FR-49).

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


def day(offset=0):
    return (datetime.now(VN).date() + timedelta(days=offset)).isoformat()


def load_app(tmp):
    os.environ["QO_DB"] = os.path.join(tmp, "test.db")
    os.environ["QO_UPLOADS"] = os.path.join(tmp, "uploads")
    os.environ["SECRET_KEY"] = "test-secret"
    sys.modules.pop("app", None)
    import app as qo
    return qo


class Sprint3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.qo = load_app(self.tmp.name)
        self.qo.app.config["TESTING"] = True
        with self.qo.db() as c:
            cat = c.execute("SELECT id FROM categories WHERE name = 'Đồ ăn'").fetchone()[0]
            add = lambda sql, *a: c.execute(sql, a).lastrowid
            h = generate_password_hash(PW)
            self.owner_a = add("INSERT INTO users(full_name, email, password_hash, role) VALUES ('A', 'a@quan.vn', ?, 'owner')", h)
            self.owner_b = add("INSERT INTO users(full_name, email, password_hash, role) VALUES ('B', 'b@quan.vn', ?, 'owner')", h)
            self.shop = add("INSERT INTO shops(owner_id, name, address, phone, open_time, close_time, status) VALUES (?, 'Quán A', 'Đ1', '0900000000', '00:00', '24:00', 'APPROVED')", self.owner_a)
            self.shop_b = add("INSERT INTO shops(owner_id, name, address, phone, open_time, close_time, status) VALUES (?, 'Quán B', 'Đ2', '0900000001', '00:00', '24:00', 'APPROVED')", self.owner_b)
            self.dish = add("INSERT INTO dishes(shop_id, category_id, name, price) VALUES (?, ?, 'Phở', 40000)", self.shop, cat)
            self.dish2 = add("INSERT INTO dishes(shop_id, category_id, name, price) VALUES (?, ?, 'Trà', 10000)", self.shop, cat)
            self.dish_b = add("INSERT INTO dishes(shop_id, category_id, name, price) VALUES (?, ?, 'Bún', 30000)", self.shop_b, cat)
            self.t1 = add("INSERT INTO shop_tables(shop_id, table_number, qr_token) VALUES (?, '1', 'tok1')", self.shop)
            self.t2 = add("INSERT INTO shop_tables(shop_id, table_number, qr_token) VALUES (?, '2', 'tok2')", self.shop)
        self.guest = self.qo.app.test_client()

    def login(self, email):
        client = self.qo.app.test_client()
        self.assertEqual(client.post("/api/login", json={"email": email, "password": PW}).status_code, 200)
        return client

    def coupon(self, client=None, **kw):
        body = {"shop_id": self.shop, "code": "GIAM10", "discount_type": "PERCENT", "discount_value": 10}
        body.update(kw)
        return (client or self.login("a@quan.vn")).post("/api/coupons", json=body)

    def order(self, code="", table=None, qty=1, dish=None, shop=None):
        body = {"shop_id": shop or self.shop, "table_id": table or self.t1, "customer_name": "Khách",
                "payment_method": "CASH", "items": [{"dish_id": dish or self.dish, "quantity": qty}]}
        if code:
            body["coupon_code"] = code
        return self.guest.post("/api/orders", json=body)

    def used(self, cid):
        with self.qo.db() as c:
            return c.execute("SELECT used_count FROM coupons WHERE id = ?", (cid,)).fetchone()[0]

    # ----- FR-46: chủ quán quản lý mã -----
    def test_owner_creates_lists_updates_deletes(self):
        owner = self.login("a@quan.vn")
        r = self.coupon(owner, code="giam10", max_uses=5, min_order=20000)
        self.assertEqual(r.status_code, 201)
        cp = r.get_json()
        self.assertEqual((cp["code"], cp["state"], cp["used_count"]), ("GIAM10", "ACTIVE", 0))
        self.assertEqual(len(owner.get(f"/api/coupons?shop_id={self.shop}").get_json()), 1)
        r = owner.put(f"/api/coupons/{cp['id']}", json={"is_active": False})
        self.assertEqual(r.get_json()["state"], "OFF")
        r = owner.put(f"/api/coupons/{cp['id']}", json={"discount_value": 20, "code": "KHAC"})
        self.assertEqual((r.get_json()["discount_value"], r.get_json()["code"]), (20, "GIAM10"))   # không đổi được mã
        self.assertEqual(owner.delete(f"/api/coupons/{cp['id']}").status_code, 200)
        self.assertEqual(owner.get(f"/api/coupons?shop_id={self.shop}").get_json(), [])

    def test_coupon_validation(self):
        owner = self.login("a@quan.vn")
        bad = [dict(code="ab"), dict(code="co dau!"), dict(discount_type="X"), dict(discount_value=0),
               dict(discount_value=101), dict(discount_type="AMOUNT", discount_value=10_000_001),
               dict(min_order=-1), dict(max_uses="abc"), dict(start_date="2026-13-01"),
               dict(start_date="2026-10-10", end_date="2026-10-01")]
        for kw in bad:
            with self.subTest(kw=kw):
                self.assertEqual(self.coupon(owner, **kw).status_code, 400)
        self.assertEqual(self.coupon(owner).status_code, 201)
        self.assertEqual(self.coupon(owner, code="giam10").status_code, 409)       # trùng mã (không phân biệt hoa thường)
        self.assertEqual(self.coupon(owner, shop_id=self.shop_b).status_code, 403)

    def test_coupon_permissions(self):
        cid = self.coupon().get_json()["id"]
        self.assertEqual(self.guest.get("/api/coupons").status_code, 401)
        b = self.login("b@quan.vn")
        self.assertEqual(b.get(f"/api/coupons?shop_id={self.shop}").status_code, 403)
        self.assertEqual(b.get("/api/coupons").get_json(), [])
        self.assertEqual(b.put(f"/api/coupons/{cid}", json={"is_active": False}).status_code, 403)
        self.assertEqual(b.delete(f"/api/coupons/{cid}").status_code, 403)

    def test_max_uses_cannot_go_below_used(self):
        owner = self.login("a@quan.vn")
        cid = self.coupon(owner, max_uses=3).get_json()["id"]
        self.order("GIAM10"); self.order("GIAM10")
        self.assertEqual(owner.put(f"/api/coupons/{cid}", json={"max_uses": 1}).status_code, 400)
        self.assertEqual(owner.put(f"/api/coupons/{cid}", json={"max_uses": 2}).get_json()["state"], "USED_UP")

    # ----- FR-23: khách dùng mã -----
    def test_percent_and_amount_discount_total(self):
        self.coupon(code="GIAM10")
        self.coupon(code="TRU15K", discount_type="AMOUNT", discount_value=15000)
        o = self.order("giam10", qty=2).get_json()                 # 80.000 - 10%
        self.assertEqual((o["total_amount"], o["discount_amount"], o["coupon_code"]), (72000, 8000, "GIAM10"))
        o = self.order("TRU15K", dish=self.dish2).get_json()       # 10.000 - 15.000 → không âm
        self.assertEqual((o["total_amount"], o["discount_amount"]), (0, 10000))

    def test_quote_matches_order(self):
        self.coupon()
        body = {"shop_id": self.shop, "coupon_code": "giam10", "items": [{"dish_id": self.dish, "quantity": 3}]}
        q = self.guest.post("/api/orders/quote", json=body).get_json()
        self.assertEqual((q["subtotal"], q["discount"], q["total"]), (120000, 12000, 108000))
        self.assertEqual(self.order("GIAM10", qty=3).get_json()["total_amount"], q["total"])
        body["coupon_code"] = "KHONGCO"
        self.assertEqual(self.guest.post("/api/orders/quote", json=body).status_code, 400)
        del body["coupon_code"]
        self.assertEqual(self.guest.post("/api/orders/quote", json=body).get_json()["discount"], 0)

    def test_invalid_coupons_are_rejected_with_reason(self):
        owner = self.login("a@quan.vn")
        self.coupon(owner, code="HETHAN", end_date=day(-1))
        self.coupon(owner, code="CHUA", start_date=day(1))
        self.coupon(owner, code="TAT")
        owner.put(f"/api/coupons/{owner.get('/api/coupons').get_json()[0]['id']}", json={"is_active": False})
        self.coupon(owner, code="LON", min_order=100000)
        self.coupon(owner, code="HOMNAY", end_date=day(0))
        for code, word in (("HETHAN", "hết hạn"), ("CHUA", "có hiệu lực từ"), ("TAT", "tạm tắt"),
                           ("LON", "từ 100.000đ"), ("KHONGCO", "không tồn tại")):
            with self.subTest(code=code):
                r = self.order(code)
                self.assertEqual(r.status_code, 400)
                self.assertIn(word, r.get_json()["error"])
        self.assertEqual(self.order("HOMNAY").status_code, 201)     # ngày cuối cùng vẫn dùng được

    def test_coupon_of_other_shop_is_not_usable(self):
        self.coupon(self.login("b@quan.vn"), shop_id=self.shop_b, code="CUAB")
        self.assertEqual(self.order("CUAB").status_code, 400)

    def test_uses_limit_and_release_on_cancel(self):
        owner = self.login("a@quan.vn")
        cid = self.coupon(owner, max_uses=1).get_json()["id"]
        first = self.order("GIAM10").get_json()
        self.assertEqual(self.used(cid), 1)
        self.assertIn("hết lượt", self.order("GIAM10").get_json()["error"])
        r = self.guest.put(f"/api/orders/{first['id']}/cancel", json={"token": first["access_token"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.used(cid), 0)                         # hủy đơn thì trả lượt
        self.assertEqual(self.order("GIAM10").status_code, 201)

    def test_owner_cancel_also_releases(self):
        owner = self.login("a@quan.vn")
        cid = self.coupon(owner).get_json()["id"]
        oid = self.order("GIAM10").get_json()["id"]
        r = owner.put(f"/api/orders/{oid}/status", json={"status": "CANCELLED", "reason": "Hết món"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.used(cid), 0)

    def test_failed_order_does_not_consume_coupon(self):
        cid = self.coupon().get_json()["id"]
        r = self.guest.post("/api/orders", json={"shop_id": self.shop, "table_id": self.t1, "customer_name": "K",
                                                 "payment_method": "CASH", "coupon_code": "GIAM10",
                                                 "items": [{"dish_id": self.dish_b, "quantity": 1}]})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.used(cid), 0)

    def test_revenue_uses_discounted_total(self):
        owner = self.login("a@quan.vn")
        self.coupon(owner)
        oid = self.order("GIAM10", qty=1).get_json()["id"]          # 36.000
        for st in ("PREPARING", "COMPLETED"):
            owner.put(f"/api/orders/{oid}/status", json={"status": st})
        owner.put(f"/api/orders/{oid}/payment", json={"payment_status": "PAID"})
        d = day(0)
        rev = owner.get(f"/api/revenue?shop_id={self.shop}&from={d}&to={d}").get_json()
        self.assertEqual(rev["summary"]["revenue"], 36000)

    # ----- FR-45: tính tiền theo bàn -----
    def test_bills_group_by_table_and_settle(self):
        owner = self.login("a@quan.vn")
        a = self.order(table=self.t1, qty=1).get_json()             # 40.000
        self.order(table=self.t1, dish=self.dish2).get_json()       # 10.000
        self.order(table=self.t2).get_json()                        # 40.000
        gone = self.order(table=self.t2).get_json()
        owner.put(f"/api/orders/{gone['id']}/status", json={"status": "CANCELLED", "reason": "Nhầm"})
        bills = owner.get(f"/api/shops/{self.shop}/bills").get_json()
        self.assertEqual([(b["table_number"], b["total"], len(b["orders"])) for b in bills], [("1", 50000, 2), ("2", 40000, 1)])
        r = owner.post(f"/api/tables/{self.t1}/settle", json={"order_ids": [a["id"]]})
        self.assertEqual(r.get_json(), {"settled": 1, "total": 40000})
        r = owner.post(f"/api/tables/{self.t1}/settle", json={})
        self.assertEqual(r.get_json(), {"settled": 1, "total": 10000})
        self.assertEqual(owner.post(f"/api/tables/{self.t1}/settle", json={}).status_code, 409)
        self.assertEqual([b["table_number"] for b in owner.get(f"/api/shops/{self.shop}/bills").get_json()], ["2"])

    def test_settle_only_touches_that_table(self):
        owner = self.login("a@quan.vn")
        self.order(table=self.t1); other = self.order(table=self.t2).get_json()
        owner.post(f"/api/tables/{self.t1}/settle", json={})
        self.assertEqual(owner.get(f"/api/orders/{other['id']}").get_json()["payment_status"], "UNPAID")
        # order_ids của bàn khác không bị đụng tới
        self.order(table=self.t1)
        self.assertEqual(owner.post(f"/api/tables/{self.t1}/settle", json={"order_ids": [other["id"]]}).status_code, 409)
        self.assertEqual(owner.post(f"/api/tables/{self.t1}/settle", json={"order_ids": "x"}).status_code, 400)

    def test_bills_permissions(self):
        self.assertEqual(self.guest.get(f"/api/shops/{self.shop}/bills").status_code, 401)
        self.assertEqual(self.guest.post(f"/api/tables/{self.t1}/settle", json={}).status_code, 401)
        b = self.login("b@quan.vn")
        self.assertEqual(b.get(f"/api/shops/{self.shop}/bills").status_code, 403)
        self.assertEqual(b.post(f"/api/tables/{self.t1}/settle", json={}).status_code, 403)

    # ----- FR-24 / FR-49: đánh giá -----
    def completed(self, **kw):
        o = self.order(**kw).get_json()
        owner = self.login("a@quan.vn")
        for st in ("PREPARING", "COMPLETED"):
            self.assertEqual(owner.put(f"/api/orders/{o['id']}/status", json={"status": st}).status_code, 200)
        return o

    def review(self, o, **kw):
        body = {"token": o["access_token"], "rating": 5, "comment": "Ngon"}
        body.update(kw)
        return self.guest.post(f"/api/orders/{o['id']}/review", json=body)

    def test_review_flow_and_flag(self):
        o = self.completed()
        self.assertFalse(self.guest.get(f"/api/orders/{o['id']}?token={o['access_token']}").get_json()["reviewed"])
        r = self.review(o, rating=4, dishes=[{"dish_id": self.dish, "rating": 5}])
        self.assertEqual(r.status_code, 201)
        self.assertTrue(self.guest.get(f"/api/orders/{o['id']}?token={o['access_token']}").get_json()["reviewed"])
        self.assertEqual(self.review(o).status_code, 409)           # BR-09: một lần

    def test_review_rules(self):
        pending = self.order().get_json()
        self.assertEqual(self.review(pending).status_code, 409)     # chưa hoàn thành
        o = self.completed()
        self.assertEqual(self.review(o, token="sai").status_code, 404)
        self.assertEqual(self.guest.post(f"/api/orders/{o['id']}/review", json={"rating": 5}).status_code, 404)
        for kw in (dict(rating=0), dict(rating=6), dict(rating="x"), dict(comment="a" * 501),
                   dict(dishes=[{"dish_id": self.dish_b, "rating": 5}]), dict(dishes=[{"dish_id": self.dish, "rating": 9}]),
                   dict(dishes="x")):
            with self.subTest(kw=kw):
                self.assertEqual(self.review(o, **kw).status_code, 400)
        self.assertEqual(self.review(o).status_code, 201)           # lỗi trước đó không làm mất lượt đánh giá

    def test_owner_sees_only_own_reviews(self):
        self.review(self.completed(), rating=5, dishes=[{"dish_id": self.dish, "rating": 4}])
        self.review(self.completed(table=self.t2), rating=2, comment="Chậm")
        ob = self.order(shop=self.shop_b, dish=self.dish_b, table=None)
        owner = self.login("a@quan.vn")
        r = owner.get(f"/api/reviews?shop_id={self.shop}").get_json()
        self.assertEqual((r["count"], r["average"]), (2, 3.5))
        self.assertEqual(r["distribution"], {"1": 0, "2": 1, "3": 0, "4": 0, "5": 1})
        self.assertEqual([x["rating"] for x in r["reviews"]], [2, 5])             # mới nhất trước
        self.assertEqual(r["reviews"][1]["dishes"], [{"name": "Phở", "rating": 4}])
        self.assertEqual(r["reviews"][0]["table_number"], "2")
        self.assertEqual([x["rating"] for x in owner.get("/api/reviews?rating=5").get_json()["reviews"]], [5])
        b = self.login("b@quan.vn")
        self.assertEqual(b.get("/api/reviews").get_json()["count"], 0)
        self.assertEqual(b.get(f"/api/reviews?shop_id={self.shop}").status_code, 403)
        self.assertEqual(self.guest.get("/api/reviews").status_code, 401)
        self.assertEqual(owner.get("/api/reviews?rating=9").status_code, 400)


if __name__ == "__main__":
    unittest.main()
