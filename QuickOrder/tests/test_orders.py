"""Kiểm thử đơn hàng: tùy chọn món, giá đơn, quyền truy cập, chuyển trạng thái, lý do hủy, thanh toán.

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


def hhmm(total_minutes):
    total_minutes %= 1440
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


class OrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.qo = load_app(os.path.join(self.tmp.name, "test.db"))
        self.qo.app.config["TESTING"] = True
        self.guest = self.qo.app.test_client()
        self.seed()

    # ----- dữ liệu mẫu -----
    def seed(self):
        with self.qo.db() as c:
            cat = c.execute("SELECT id FROM categories WHERE name = 'Đồ ăn'").fetchone()[0]

            def add(sql, *args):
                return c.execute(sql, args).lastrowid

            self.owner_a = add("INSERT INTO users(full_name, email, password_hash, role) VALUES ('Chủ A', 'a@quan.vn', ?, 'owner')", generate_password_hash(PW))
            self.owner_b = add("INSERT INTO users(full_name, email, password_hash, role) VALUES ('Chủ B', 'b@quan.vn', ?, 'owner')", generate_password_hash(PW))
            add("INSERT INTO users(full_name, email, password_hash, role) VALUES ('Khách', 'k@example.com', ?, 'customer')", generate_password_hash(PW))
            # Giờ mở cửa cả ngày (24:00) để các test không phụ thuộc giờ chạy
            self.shop = add("INSERT INTO shops(owner_id, name, address, phone, open_time, close_time, status) VALUES (?, 'Quán A', 'Đường 1', '0900000000', '00:00', '24:00', 'APPROVED')", self.owner_a)
            self.other_shop = add("INSERT INTO shops(owner_id, name, address, phone, open_time, close_time, status) VALUES (?, 'Quán B', 'Đường 2', '0900000001', '00:00', '24:00', 'APPROVED')", self.owner_b)
            self.table = add("INSERT INTO shop_tables(shop_id, table_number, qr_token) VALUES (?, '1', 'tok-a-1')", self.shop)
            self.other_table = add("INSERT INTO shop_tables(shop_id, table_number, qr_token) VALUES (?, '1', 'tok-b-1')", self.other_shop)
            self.dish = add("INSERT INTO dishes(shop_id, category_id, name, price) VALUES (?, ?, 'Trà sữa', 50000)", self.shop, cat)
            self.sold_out = add("INSERT INTO dishes(shop_id, category_id, name, price, is_available) VALUES (?, ?, 'Hết món', 30000, 0)", self.shop, cat)
            self.other_dish = add("INSERT INTO dishes(shop_id, category_id, name, price) VALUES (?, ?, 'Phở', 40000)", self.other_shop, cat)

            # Nhóm bắt buộc, chọn một: Size
            size = add("INSERT INTO option_groups(dish_id, name, is_required, is_multiple) VALUES (?, 'Size', 1, 0)", self.dish)
            self.opt_small = add("INSERT INTO options(group_id, name, extra_price) VALUES (?, 'Nhỏ', 0)", size)
            self.opt_big = add("INSERT INTO options(group_id, name, extra_price) VALUES (?, 'Lớn', 10000)", size)
            # Nhóm tùy chọn, chọn nhiều: Topping
            topping = add("INSERT INTO option_groups(dish_id, name, is_required, is_multiple) VALUES (?, 'Topping', 0, 1)", self.dish)
            self.opt_pearl = add("INSERT INTO options(group_id, name, extra_price) VALUES (?, 'Trân châu', 5000)", topping)
            self.opt_jelly = add("INSERT INTO options(group_id, name, extra_price) VALUES (?, 'Thạch', 7000)", topping)
            # Tùy chọn của món khác (dùng để thử gửi nhầm)
            other_group = add("INSERT INTO option_groups(dish_id, name, is_required, is_multiple) VALUES (?, 'Khác', 0, 0)", self.other_dish)
            self.opt_foreign = add("INSERT INTO options(group_id, name, extra_price) VALUES (?, 'Ngoài', 1000)", other_group)

    # ----- tiện ích -----
    def login(self, email):
        client = self.qo.app.test_client()
        resp = client.post("/api/login", json={"email": email, "password": PW})
        self.assertEqual(resp.status_code, 200, resp.get_json())
        return client

    def order(self, items, client=None, **extra):
        body = {"shop_id": self.shop, "table_id": self.table, "items": items}
        body.update(extra)
        return (client or self.guest).post("/api/orders", json=body)

    def make_order(self):
        resp = self.order([{"dish_id": self.dish, "quantity": 2, "option_ids": [self.opt_small, self.opt_pearl]}])
        self.assertEqual(resp.status_code, 201, resp.get_json())
        return resp.get_json()

    def set_hours(self, open_at, close_at):
        with self.qo.db() as c:
            c.execute("UPDATE shops SET open_time = ?, close_time = ? WHERE id = ?", (open_at, close_at, self.shop))

    # ----- tùy chọn và giá -----
    def test_price_includes_chosen_options(self):
        resp = self.order([{"dish_id": self.dish, "quantity": 2, "option_ids": [self.opt_big, self.opt_pearl]}])
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        # 50000 + 10000 (Lớn) + 5000 (Trân châu) = 65000 cho mỗi phần, 2 phần
        self.assertEqual(data["total_amount"], 130000)
        item = data["items"][0]
        self.assertEqual(item["unit_price"], 65000)
        self.assertIn("Lớn", item["note"])
        self.assertIn("Trân châu", item["note"])

    def test_option_names_and_customer_note_are_both_kept(self):
        resp = self.order([{"dish_id": self.dish, "quantity": 1, "option_ids": [self.opt_small], "note": "ít đá"}])
        self.assertEqual(resp.get_json()["items"][0]["note"], "Nhỏ; ít đá")

    def test_multiple_choice_group_accepts_several_options(self):
        resp = self.order([{"dish_id": self.dish, "quantity": 1,
                            "option_ids": [self.opt_small, self.opt_pearl, self.opt_jelly]}])
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["total_amount"], 50000 + 5000 + 7000)

    def test_required_group_must_be_chosen(self):
        resp = self.order([{"dish_id": self.dish, "quantity": 1, "option_ids": [self.opt_pearl]}])
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Size", resp.get_json()["error"])

    def test_single_choice_group_rejects_two_options(self):
        resp = self.order([{"dish_id": self.dish, "quantity": 1, "option_ids": [self.opt_big, self.opt_small]}])
        self.assertEqual(resp.status_code, 400)

    def test_option_from_another_dish_is_rejected(self):
        resp = self.order([{"dish_id": self.dish, "quantity": 1, "option_ids": [self.opt_small, self.opt_foreign]}])
        self.assertEqual(resp.status_code, 400)

    def test_sold_out_dish_cannot_be_ordered(self):
        resp = self.order([{"dish_id": self.sold_out, "quantity": 1, "option_ids": []}])
        self.assertEqual(resp.status_code, 400)

    def test_table_must_belong_to_shop(self):
        resp = self.order([{"dish_id": self.dish, "quantity": 1, "option_ids": [self.opt_small]}], table_id=999)
        self.assertEqual(resp.status_code, 400)

    def test_order_without_table_is_rejected(self):
        resp = self.order([{"dish_id": self.dish, "quantity": 1, "option_ids": [self.opt_small]}], table_id=None)
        self.assertEqual(resp.status_code, 400)

    def test_quantity_is_capped(self):
        too_many = self.order([{"dish_id": self.dish, "quantity": 51, "option_ids": [self.opt_small]}])
        self.assertEqual(too_many.status_code, 400)
        ok = self.order([{"dish_id": self.dish, "quantity": 50, "option_ids": [self.opt_small]}])
        self.assertEqual(ok.status_code, 201)

    def test_order_rejected_outside_opening_hours(self):
        now = datetime.now(VN)
        n = now.hour * 60 + now.minute
        self.set_hours(hhmm(n + 120), hhmm(n + 180))     # khung giờ không chứa thời điểm hiện tại
        resp = self.order([{"dish_id": self.dish, "quantity": 1, "option_ids": [self.opt_small]}])
        self.assertEqual(resp.status_code, 409)

    def test_order_accepted_inside_opening_hours(self):
        now = datetime.now(VN)
        n = now.hour * 60 + now.minute
        self.set_hours(hhmm(n - 60), hhmm(n + 60))       # khung giờ chứa thời điểm hiện tại
        resp = self.order([{"dish_id": self.dish, "quantity": 1, "option_ids": [self.opt_small]}])
        self.assertEqual(resp.status_code, 201)

    # ----- mã đơn: ai xem được đơn -----
    def test_create_returns_token_once_and_list_never_shows_it(self):
        order = self.make_order()
        self.assertTrue(order["access_token"])
        self.assertNotIn("access_hash", order)
        listed = self.login("a@quan.vn").get("/api/orders").get_json()
        self.assertNotIn("access_token", listed[0])
        self.assertNotIn("access_hash", listed[0])

    def test_guest_reads_order_only_with_token(self):
        order = self.make_order()
        url = f"/api/orders/{order['id']}"
        self.assertEqual(self.guest.get(url).status_code, 404)
        self.assertEqual(self.guest.get(url + "?token=sai").status_code, 404)
        resp = self.guest.get(url + "?token=" + order["access_token"])
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("access_hash", resp.get_json())

    def test_other_customer_cannot_read_order_by_guessing_id(self):
        order = self.make_order()
        stranger = self.qo.app.test_client()
        self.assertEqual(stranger.get(f"/api/orders/{order['id']}").status_code, 404)

    def test_owner_reads_own_order_without_token(self):
        order = self.make_order()
        self.assertEqual(self.login("a@quan.vn").get(f"/api/orders/{order['id']}").status_code, 200)
        self.assertEqual(self.login("b@quan.vn").get(f"/api/orders/{order['id']}").status_code, 404)

    # ----- quyền xem danh sách và xử lý đơn -----
    def test_list_returns_newest_first_in_pages(self):
        ids = [self.make_order()["id"] for _ in range(3)]
        owner = self.login("a@quan.vn")
        page1 = owner.get("/api/orders?limit=2").get_json()
        self.assertEqual([o["id"] for o in page1], [ids[2], ids[1]])
        self.assertEqual(len(page1[0]["items"]), 1)            # món vẫn gắn đúng đơn sau khi gom truy vấn
        page2 = owner.get(f"/api/orders?limit=2&before={ids[1]}").get_json()
        self.assertEqual([o["id"] for o in page2], [ids[0]])
        self.assertEqual(owner.get("/api/orders?limit=abc").status_code, 400)

    def test_owner_sees_only_own_shop_orders(self):
        self.make_order()
        other = self.guest.post("/api/orders", json={
            "shop_id": self.other_shop,
            "table_id": self.other_table,
            "items": [{"dish_id": self.other_dish, "quantity": 1, "option_ids": [self.opt_foreign]}],
        })
        self.assertEqual(other.status_code, 201)
        mine = self.login("a@quan.vn").get("/api/orders").get_json()
        self.assertEqual([o["shop_id"] for o in mine], [self.shop])
        theirs = self.login("b@quan.vn").get("/api/orders").get_json()
        self.assertEqual([o["shop_id"] for o in theirs], [self.other_shop])

    def test_customer_and_guest_cannot_list_orders(self):
        self.assertEqual(self.guest.get("/api/orders").status_code, 401)
        self.assertEqual(self.login("k@example.com").get("/api/orders").status_code, 403)

    def test_owner_confirms_then_completes_order(self):
        order = self.make_order()
        owner = self.login("a@quan.vn")
        url = f"/api/orders/{order['id']}/status"
        r = owner.put(url, json={"status": "PREPARING"})
        self.assertEqual(r.get_json()["status"], "PREPARING")
        r = owner.put(url, json={"status": "COMPLETED"})
        self.assertEqual(r.get_json()["status"], "COMPLETED")
        # Đơn đã kết thúc không sửa được nữa
        self.assertEqual(owner.put(url, json={"status": "PREPARING"}).status_code, 409)

    def test_owner_cannot_jump_pending_straight_to_completed(self):
        order = self.make_order()
        r = self.login("a@quan.vn").put(f"/api/orders/{order['id']}/status", json={"status": "COMPLETED"})
        self.assertEqual(r.status_code, 409)

    def test_owner_cannot_move_order_back_to_pending(self):
        order = self.make_order()
        owner = self.login("a@quan.vn")
        url = f"/api/orders/{order['id']}/status"
        owner.put(url, json={"status": "PREPARING"})
        self.assertEqual(owner.put(url, json={"status": "PENDING"}).status_code, 409)

    def test_owner_cancel_requires_reason_and_saves_it(self):
        order = self.make_order()
        owner = self.login("a@quan.vn")
        url = f"/api/orders/{order['id']}/status"
        self.assertEqual(owner.put(url, json={"status": "CANCELLED"}).status_code, 400)
        r = owner.put(url, json={"status": "CANCELLED", "reason": "Hết nguyên liệu"})
        self.assertEqual(r.get_json()["status"], "CANCELLED")
        self.assertEqual(r.get_json()["cancel_reason"], "Hết nguyên liệu")

    def test_other_owner_cannot_change_status(self):
        order = self.make_order()
        r = self.login("b@quan.vn").put(f"/api/orders/{order['id']}/status", json={"status": "PREPARING"})
        self.assertEqual(r.status_code, 403)

    # ----- khách hủy -----
    def test_customer_cancels_pending_order_with_token(self):
        order = self.make_order()
        url = f"/api/orders/{order['id']}/cancel"
        r = self.guest.put(url, json={"token": order["access_token"]})
        self.assertEqual(r.get_json()["status"], "CANCELLED")
        self.assertTrue(r.get_json()["cancel_reason"])
        self.assertEqual(self.guest.put(url, json={"token": order["access_token"]}).status_code, 409)

    def test_customer_cannot_cancel_without_token(self):
        order = self.make_order()
        url = f"/api/orders/{order['id']}/cancel"
        self.assertEqual(self.guest.put(url, json={}).status_code, 404)
        self.assertEqual(self.guest.put(url, json={"token": "sai"}).status_code, 404)

    def test_customer_cannot_cancel_order_already_being_made(self):
        order = self.make_order()
        self.login("a@quan.vn").put(f"/api/orders/{order['id']}/status", json={"status": "PREPARING"})
        r = self.guest.put(f"/api/orders/{order['id']}/cancel", json={"token": order["access_token"]})
        self.assertEqual(r.status_code, 409)

    # ----- thanh toán -----
    def test_owner_marks_order_paid_and_back(self):
        order = self.make_order()
        owner = self.login("a@quan.vn")
        url = f"/api/orders/{order['id']}/payment"
        r = owner.put(url, json={"payment_status": "PAID"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["payment_status"], "PAID")
        r = owner.put(url, json={"payment_status": "UNPAID"})
        self.assertEqual(r.get_json()["payment_status"], "UNPAID")

    def test_payment_update_rules(self):
        order = self.make_order()
        url = f"/api/orders/{order['id']}/payment"
        body = {"payment_status": "PAID"}
        self.assertEqual(self.guest.put(url, json=body).status_code, 401)
        self.assertEqual(self.login("k@example.com").put(url, json=body).status_code, 403)
        self.assertEqual(self.login("b@quan.vn").put(url, json=body).status_code, 403)
        owner = self.login("a@quan.vn")
        self.assertEqual(owner.put(url, json={"payment_status": "KHONG"}).status_code, 400)
        # Đơn đã hủy thì không ghi nhận thanh toán
        owner.put(f"/api/orders/{order['id']}/status", json={"status": "CANCELLED", "reason": "Test"})
        self.assertEqual(owner.put(url, json=body).status_code, 409)


class OldOrderTableTests(unittest.TestCase):
    """CSDL có bảng orders tạo trước khi thêm mã đơn và lý do hủy vẫn được bổ sung cột khi khởi động."""

    def test_old_orders_table_gets_new_columns(self):
        import sqlite3
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "old.db")
        con = sqlite3.connect(path)
        con.execute("""CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id INTEGER NOT NULL, table_id INTEGER,
            customer_name TEXT NOT NULL DEFAULT 'Khách tại bàn', status TEXT NOT NULL DEFAULT 'PENDING',
            payment_method TEXT NOT NULL DEFAULT 'CASH', payment_status TEXT NOT NULL DEFAULT 'UNPAID',
            total_amount INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        con.commit()
        con.close()
        qo = load_app(path)
        with qo.db() as c:
            cols = [r["name"] for r in c.execute("PRAGMA table_info(orders)")]
        self.assertIn("access_hash", cols)
        self.assertIn("cancel_reason", cols)


if __name__ == "__main__":
    unittest.main()
