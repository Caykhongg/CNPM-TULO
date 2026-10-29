"""Kiểm thử Sprint 3 nhóm khách: lịch sử đơn (FR-21), đặt lại món (FR-22), gợi ý món (FR-25), khiếu nại (FR-26).

Chạy từ thư mục QuickOrder:
    python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import unittest

from werkzeug.security import generate_password_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PW = "matkhau123"


def load_app(tmp):
    os.environ["QO_DB"] = os.path.join(tmp, "test.db")
    os.environ["QO_UPLOADS"] = os.path.join(tmp, "uploads")
    os.environ["SECRET_KEY"] = "test-secret"
    sys.modules.pop("app", None)
    import app as qo
    return qo


class CustomerUtilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.qo = load_app(self.tmp.name)
        self.qo.app.config["TESTING"] = True
        with self.qo.db() as c:
            cat = c.execute("SELECT id FROM categories WHERE name = 'Đồ ăn'").fetchone()[0]
            add = lambda sql, *a: c.execute(sql, a).lastrowid
            h = generate_password_hash(PW)
            user = lambda name, email, role: add(
                "INSERT INTO users(full_name, email, password_hash, role) VALUES (?, ?, ?, ?)", name, email, h, role)
            self.owner = user("Chủ", "owner@quan.vn", "owner")
            self.cust_a = user("Khách A", "a@mail.vn", "customer")
            self.cust_b = user("Khách B", "b@mail.vn", "customer")
            self.shop = add("INSERT INTO shops(owner_id, name, address, phone, open_time, close_time, status) "
                            "VALUES (?, 'Quán 1', 'Đ1', '0900000000', '00:00', '24:00', 'APPROVED')", self.owner)
            self.pho = add("INSERT INTO dishes(shop_id, category_id, name, price) VALUES (?, ?, 'Phở', 40000)", self.shop, cat)
            self.tra = add("INSERT INTO dishes(shop_id, category_id, name, price) VALUES (?, ?, 'Trà', 10000)", self.shop, cat)
            self.bun = add("INSERT INTO dishes(shop_id, category_id, name, price) VALUES (?, ?, 'Bún', 35000)", self.shop, cat)
            grp = add("INSERT INTO option_groups(dish_id, name, is_required) VALUES (?, 'Size', 1)", self.tra)
            self.size_m = add("INSERT INTO options(group_id, name, extra_price) VALUES (?, 'M', 0)", grp)
            self.size_l = add("INSERT INTO options(group_id, name, extra_price) VALUES (?, 'L', 5000)", grp)
            self.table = add("INSERT INTO shop_tables(shop_id, table_number, qr_token) VALUES (?, '1', 'tok1')", self.shop)
        self.guest = self.qo.app.test_client()

    # ----- tiện ích -----
    def login(self, email):
        client = self.qo.app.test_client()
        self.assertEqual(client.post("/api/login", json={"email": email, "password": PW}).status_code, 200)
        return client

    def order(self, client, items=None):
        items = items or [{"dish_id": self.pho, "quantity": 1}]
        r = client.post("/api/orders", json={"shop_id": self.shop, "table_id": self.table, "customer_name": "K",
                                             "payment_method": "CASH", "items": items})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        return r.get_json()

    def set_status(self, order_id, status):
        with self.qo.db() as c:
            c.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))

    def sql(self, q, *a):
        with self.qo.db() as c:
            return c.execute(q, a).fetchall()

    # ===== FR-21: lịch sử đơn =====
    def test_history_needs_customer_login(self):
        self.assertEqual(self.guest.get("/api/my/orders").status_code, 401)
        self.assertEqual(self.login("owner@quan.vn").get("/api/my/orders").status_code, 403)

    def test_history_lists_only_own_orders(self):
        a, b = self.login("a@mail.vn"), self.login("b@mail.vn")
        mine = self.order(a)
        self.order(b)
        self.order(self.guest)                       # khách ẩn danh: không vào lịch sử của ai
        r = a.get("/api/my/orders").get_json()
        self.assertEqual([o["id"] for o in r["orders"]], [mine["id"]])
        o = r["orders"][0]
        self.assertEqual((o["shop_name"], o["table_number"]), ("Quán 1", "1"))
        self.assertEqual(o["items"][0]["dish_name"], "Phở")
        self.assertNotIn("access_hash", o)
        self.assertNotIn("user_id", o)
        self.assertIsNone(r["next_before"])

    def test_history_detail_is_private(self):
        a, b = self.login("a@mail.vn"), self.login("b@mail.vn")
        o = self.order(a)
        self.assertEqual(a.get(f"/api/my/orders/{o['id']}").status_code, 200)
        self.assertEqual(b.get(f"/api/my/orders/{o['id']}").status_code, 404)
        self.assertEqual(self.guest.get(f"/api/my/orders/{o['id']}").status_code, 401)

    def test_history_paging_and_status_filter(self):
        a = self.login("a@mail.vn")
        ids = [self.order(a)["id"] for _ in range(5)]
        self.set_status(ids[0], "COMPLETED")
        p1 = a.get("/api/my/orders?limit=2").get_json()
        self.assertEqual([o["id"] for o in p1["orders"]], ids[::-1][:2])
        self.assertEqual(p1["next_before"], ids[3])
        p2 = a.get(f"/api/my/orders?limit=2&before={p1['next_before']}").get_json()
        self.assertEqual([o["id"] for o in p2["orders"]], [ids[2], ids[1]])
        done = a.get("/api/my/orders?status=COMPLETED").get_json()["orders"]
        self.assertEqual([o["id"] for o in done], [ids[0]])
        self.assertEqual(a.get("/api/my/orders?status=XYZ").status_code, 400)
        self.assertEqual(a.get("/api/my/orders?limit=0").status_code, 400)
        self.assertEqual(a.get("/api/my/orders?limit=abc").status_code, 400)

    def test_owner_view_hides_customer_account(self):
        self.order(self.login("a@mail.vn"))
        rows = self.login("owner@quan.vn").get("/api/orders").get_json()
        self.assertTrue(rows)
        self.assertTrue(all("user_id" not in o for o in rows))

    # ===== FR-22: đặt lại món =====
    def reorder(self, client, order_id):
        return client.post(f"/api/my/orders/{order_id}/reorder", json={})

    def test_reorder_rebuilds_cart_with_options(self):
        a = self.login("a@mail.vn")
        o = self.order(a, [{"dish_id": self.pho, "quantity": 2}, {"dish_id": self.tra, "quantity": 1, "option_ids": [self.size_l]}])
        r = self.reorder(a, o["id"]).get_json()
        self.assertEqual(r["shop"], {"id": self.shop, "name": "Quán 1"})
        self.assertEqual(r["skipped"], [])
        self.assertTrue(r["accepting"])
        pho, tra = r["items"]
        self.assertEqual((pho["dish_id"], pho["qty"], pho["options"], pho["price"]), (self.pho, 2, [], 40000))
        self.assertEqual([x["id"] for x in tra["options"]], [self.size_l])
        self.assertEqual((tra["unit_price"], tra["price_changed"]), (15000, False))

    def test_reorder_uses_current_price(self):
        a = self.login("a@mail.vn")
        o = self.order(a)
        with self.qo.db() as c:
            c.execute("UPDATE dishes SET price = 50000 WHERE id = ?", (self.pho,))
        item = self.reorder(a, o["id"]).get_json()["items"][0]
        self.assertEqual((item["price"], item["unit_price"], item["old_unit_price"], item["price_changed"]),
                         (50000, 50000, 40000, True))
        self.assertEqual(self.sql("SELECT unit_price FROM order_items WHERE order_id = ?", o["id"])[0][0], 40000)   # đơn cũ giữ nguyên giá (BR-04)

    def test_reorder_skips_unavailable_dishes(self):
        a = self.login("a@mail.vn")
        o = self.order(a, [{"dish_id": self.pho, "quantity": 1}, {"dish_id": self.bun, "quantity": 1}, {"dish_id": self.tra, "quantity": 1, "option_ids": [self.size_m]}])
        with self.qo.db() as c:
            c.execute("UPDATE dishes SET is_available = 0 WHERE id = ?", (self.pho,))
            c.execute("UPDATE dishes SET is_deleted = 1 WHERE id = ?", (self.bun,))
            c.execute("DELETE FROM options WHERE id = ?", (self.size_m,))
        r = self.reorder(a, o["id"]).get_json()
        self.assertEqual(r["items"], [])
        reasons = {s["dish_name"]: s["reason"] for s in r["skipped"]}
        self.assertEqual(reasons["Phở"], "Món đã hết.")
        self.assertEqual(reasons["Bún"], "Món đã ngừng bán.")
        self.assertIn("Tùy chọn", reasons["Trà"])

    def test_reorder_old_order_without_saved_options(self):
        a = self.login("a@mail.vn")
        o = self.order(a, [{"dish_id": self.tra, "quantity": 1, "option_ids": [self.size_l]}, {"dish_id": self.pho, "quantity": 1}])
        with self.qo.db() as c:
            c.execute("UPDATE order_items SET option_ids = '' WHERE order_id = ?", (o["id"],))     # đơn tạo trước khi có cột này
        r = self.reorder(a, o["id"]).get_json()
        self.assertEqual([i["dish_id"] for i in r["items"]], [self.pho])
        self.assertEqual([s["dish_name"] for s in r["skipped"]], ["Trà"])

    def test_reorder_is_private_and_read_only(self):
        a, b = self.login("a@mail.vn"), self.login("b@mail.vn")
        o = self.order(a)
        before = len(self.sql("SELECT id FROM orders"))
        self.assertEqual(self.reorder(b, o["id"]).status_code, 404)
        self.assertEqual(self.reorder(self.guest, o["id"]).status_code, 401)
        self.assertEqual(self.reorder(a, o["id"]).status_code, 200)
        self.assertEqual(len(self.sql("SELECT id FROM orders")), before)       # không tự tạo đơn mới

    def test_reorder_blocked_when_shop_locked(self):
        a = self.login("a@mail.vn")
        o = self.order(a)
        with self.qo.db() as c:
            c.execute("UPDATE shops SET status = 'LOCKED' WHERE id = ?", (self.shop,))
        self.assertEqual(self.reorder(a, o["id"]).status_code, 409)

    # ===== FR-25: gợi ý món =====
    def suggestions(self, client=None):
        return (client or self.guest).get(f"/api/shops/{self.shop}/suggestions")

    def test_popular_counts_only_completed_orders(self):
        o1 = self.order(self.guest, [{"dish_id": self.pho, "quantity": 2}, {"dish_id": self.bun, "quantity": 1}])
        o2 = self.order(self.guest, [{"dish_id": self.bun, "quantity": 3}])
        o3 = self.order(self.guest, [{"dish_id": self.pho, "quantity": 9}])          # đơn hủy không tính
        self.set_status(o1["id"], "COMPLETED"); self.set_status(o2["id"], "COMPLETED"); self.set_status(o3["id"], "CANCELLED")
        r = self.suggestions().get_json()
        self.assertEqual([(d["dish_id"], d["total"]) for d in r["popular"]], [(self.bun, 4), (self.pho, 2)])
        self.assertEqual(r["mine"], [])                                                # khách ẩn danh: không có phần cá nhân

    def test_popular_skips_deleted_dishes_and_empty_shop(self):
        self.assertEqual(self.suggestions().get_json(), {"popular": [], "mine": []})
        o = self.order(self.guest)
        self.set_status(o["id"], "COMPLETED")
        with self.qo.db() as c:
            c.execute("UPDATE dishes SET is_deleted = 1 WHERE id = ?", (self.pho,))
        self.assertEqual(self.suggestions().get_json()["popular"], [])

    def test_mine_needs_two_orders_and_ignores_cancelled(self):
        a, b = self.login("a@mail.vn"), self.login("b@mail.vn")
        self.order(a); self.order(a)                                                    # Phở: 2 đơn
        self.order(a, [{"dish_id": self.bun, "quantity": 5}])                           # Bún: 1 đơn, dù số lượng lớn
        cancelled = self.order(a, [{"dish_id": self.bun, "quantity": 1}])
        self.set_status(cancelled["id"], "CANCELLED")
        self.order(b); self.order(b); self.order(b)
        mine = self.suggestions(a).get_json()["mine"]
        self.assertEqual([d["dish_id"] for d in mine], [self.pho])
        self.assertEqual(mine[0]["order_count"], 2)

    def test_suggestions_only_for_approved_shop(self):
        with self.qo.db() as c:
            c.execute("UPDATE shops SET status = 'PENDING' WHERE id = ?", (self.shop,))
        self.assertEqual(self.suggestions().status_code, 404)

    # ===== FR-26: khiếu nại =====
    TEXT = "Món lên chậm và bị thiếu một phần."

    def complain(self, client, order_id, **kw):
        body = {"content": self.TEXT}
        body.update(kw)
        return client.post(f"/api/orders/{order_id}/complaints", json=body)

    def test_customer_complains_and_tracks_status(self):
        a = self.login("a@mail.vn")
        o = self.order(a)
        self.set_status(o["id"], "COMPLETED")
        r = self.complain(a, o["id"])
        self.assertEqual(r.status_code, 201)
        self.assertEqual((r.get_json()["status"], r.get_json()["owner_reply"]), ("OPEN", ""))
        self.assertEqual(a.get(f"/api/my/orders/{o['id']}").get_json()["complaint_status"], "OPEN")
        with self.qo.db() as c:                                                         # Chủ quán phản hồi ở FR-55
            c.execute("UPDATE complaints SET status = 'REPLIED', owner_reply = 'Xin lỗi bạn' WHERE order_id = ?", (o["id"],))
        lst = a.get(f"/api/orders/{o['id']}/complaints").get_json()
        self.assertEqual((lst[0]["status"], lst[0]["owner_reply"]), ("REPLIED", "Xin lỗi bạn"))
        mine = a.get("/api/my/complaints").get_json()
        self.assertEqual((len(mine), mine[0]["shop_name"]), (1, "Quán 1"))

    def test_complaint_validation(self):
        a = self.login("a@mail.vn")
        o = self.order(a)
        self.set_status(o["id"], "COMPLETED")
        self.assertEqual(self.complain(a, o["id"], content="ngắn").status_code, 400)
        self.assertEqual(self.complain(a, o["id"], content="x" * 501).status_code, 400)
        self.assertEqual(self.complain(a, o["id"], content="   ").status_code, 400)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM complaints")[0][0], 0)

    def test_cannot_complain_while_pending(self):
        a = self.login("a@mail.vn")
        o = self.order(a)
        self.assertEqual(self.complain(a, o["id"]).status_code, 409)

    def test_one_open_complaint_per_order_then_reopen_after_close(self):
        a = self.login("a@mail.vn")
        o = self.order(a)
        self.set_status(o["id"], "COMPLETED")
        self.assertEqual(self.complain(a, o["id"]).status_code, 201)
        self.assertEqual(self.complain(a, o["id"]).status_code, 409)
        with self.qo.db() as c:
            c.execute("UPDATE complaints SET status = 'CLOSED'")
        self.assertEqual(self.complain(a, o["id"]).status_code, 201)

    def test_complaint_cap_per_order(self):
        a = self.login("a@mail.vn")
        o = self.order(a)
        self.set_status(o["id"], "COMPLETED")
        for _ in range(self.qo.MAX_COMPLAINTS_PER_ORDER):
            self.assertEqual(self.complain(a, o["id"]).status_code, 201)
            with self.qo.db() as c:
                c.execute("UPDATE complaints SET status = 'CLOSED'")
        self.assertEqual(self.complain(a, o["id"]).status_code, 409)

    def test_complaint_access_rules(self):
        a, b = self.login("a@mail.vn"), self.login("b@mail.vn")
        o = self.order(a)
        self.set_status(o["id"], "COMPLETED")
        self.assertEqual(self.complain(b, o["id"]).status_code, 404)                    # khách khác
        self.assertEqual(self.complain(self.guest, o["id"]).status_code, 404)           # không có mã riêng
        self.assertEqual(self.complain(self.guest, o["id"], token="sai").status_code, 404)
        self.assertEqual(b.get(f"/api/orders/{o['id']}/complaints").status_code, 404)
        self.assertEqual(self.guest.get("/api/my/complaints").status_code, 401)

    def test_anonymous_customer_complains_with_order_token(self):
        o = self.order(self.guest)
        self.set_status(o["id"], "COMPLETED")
        r = self.complain(self.guest, o["id"], token=o["access_token"])
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(self.sql("SELECT user_id FROM complaints")[0][0])
        lst = self.guest.get(f"/api/orders/{o['id']}/complaints?token={o['access_token']}")
        self.assertEqual(len(lst.get_json()), 1)
        self.assertEqual(self.guest.get(f"/api/orders/{o['id']}/complaints").status_code, 404)

    def test_missing_order_is_404(self):
        self.assertEqual(self.complain(self.login("a@mail.vn"), 9999).status_code, 404)


if __name__ == "__main__":
    unittest.main()
