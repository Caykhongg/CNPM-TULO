"""Lịch sử tài khoản, nhận đơn bằng mã riêng và khiếu nại theo chủ quán."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PW = "TestOrder@123"


class OrderHistoryComplaintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = generate_password_hash(PW)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {"QO_DB": str(Path(tmp.name) / "test.db"), "SECRET_KEY": "tests-only"})
        env.start()
        self.addCleanup(env.stop)
        sys.modules.pop("app", None)
        import app
        self.qo = app
        app.app.config["TESTING"] = True
        self.ids, self.shops, self.tables, self.dishes = {}, {}, {}, {}
        with app.db() as c:
            for name, role in (("owner_a", "owner"), ("owner_b", "owner"),
                               ("customer_a", "customer"), ("customer_b", "customer"), ("admin", "admin")):
                self.ids[name] = c.execute(
                    "INSERT INTO users(full_name,email,password_hash,role) VALUES (?,?,?,?)",
                    (name, name + "@test.local", self.password_hash, role),
                ).lastrowid
            cat = c.execute("SELECT id FROM categories LIMIT 1").fetchone()[0]
            for name in ("a", "b"):
                shop = c.execute(
                    "INSERT INTO shops(owner_id,name,address,phone,open_time,close_time,status) "
                    "VALUES (?,?,'Test','0912345678','00:00','24:00','APPROVED')",
                    (self.ids["owner_" + name], "Quán " + name),
                ).lastrowid
                self.shops[name] = shop
                self.tables[name] = c.execute(
                    "INSERT INTO shop_tables(shop_id,table_number,qr_token) VALUES (?,'1',?)",
                    (shop, "qr-" + name),
                ).lastrowid
                self.dishes[name] = c.execute(
                    "INSERT INTO dishes(shop_id,category_id,name,price) VALUES (?,?,'Phở',40000)", (shop, cat),
                ).lastrowid
        self.guest = app.app.test_client()
        self.clients = {}
        for name, uid in self.ids.items():
            client = app.app.test_client()
            with client.session_transaction() as s:
                s["uid"] = uid
            self.clients[name] = client
        self.customer = self.clients["customer_a"]
        self.owner = self.clients["owner_a"]

    def order(self, client=None, shop="a"):
        r = (client or self.guest).post("/api/orders", json={
            "shop_id": self.shops[shop], "table_id": self.tables[shop], "customer_name": "Khách",
            "items": [{"dish_id": self.dishes[shop], "quantity": 2}],
        })
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def complaint(self, client=None, shop="a"):
        client = client or self.customer
        order = self.order(client, shop)
        owner = self.clients["owner_" + shop]
        for status in ("PREPARING", "COMPLETED"):
            self.assertEqual(owner.put(f"/api/orders/{order['id']}/status", json={"status": status}).status_code, 200)
        r = client.post(f"/api/orders/{order['id']}/complaints", json={
            "token": order["access_token"], "content": "Quán giao thiếu một món, nhờ quán kiểm tra giúp.",
        })
        self.assertEqual(r.status_code, 201, r.get_json())
        return order, r.get_json()["id"]

    def claim(self, client, order, token=None):
        return client.post(f"/api/my/orders/{order['id']}/claim", json={
            "token": order["access_token"] if token is None else token,
        })

    def test_logged_in_checkout_appears_after_completion_and_new_login(self):
        order = self.order(self.customer)
        self.assertTrue(order["in_my_history"])
        for status in ("PREPARING", "COMPLETED"):
            self.owner.put(f"/api/orders/{order['id']}/status", json={"status": status})
        other_device = self.qo.app.test_client()
        self.assertEqual(other_device.post("/api/login", json={
            "email": "customer_a@test.local", "password": PW,
        }).status_code, 200)
        rows = other_device.get("/api/my/orders").get_json()["orders"]
        self.assertEqual([r["id"] for r in rows], [order["id"]])
        self.assertEqual((rows[0]["status"], rows[0]["items"][0]["quantity"]), ("COMPLETED", 2))
        self.assertEqual(other_device.get(f"/api/orders/{order['id']}").status_code, 200)
        self.assertEqual(self.clients["customer_b"].get(f"/api/orders/{order['id']}").status_code, 404)

    def test_guest_order_can_be_saved_without_changing_purchase(self):
        order, cid = self.complaint(self.guest)
        self.assertFalse(order["in_my_history"])
        self.assertEqual(self.customer.get("/api/my/orders").get_json()["orders"], [])
        preview = self.guest.get(f"/api/orders/{order['id']}?token={order['access_token']}").get_json()
        self.assertTrue(preview["can_save_to_history"])
        self.assertEqual(preview["shop_name"], "Quán a")
        r = self.claim(self.customer, order)
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.get_json()["total_amount"], r.get_json()["status"]), (80000, "COMPLETED"))
        self.assertNotIn("access_hash", r.get_json())
        self.assertNotIn("user_id", r.get_json())
        self.assertEqual(self.customer.get("/api/my/complaints").get_json()[0]["id"], cid)
        with self.qo.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM order_items").fetchone()[0], 1)
        self.assertEqual(self.claim(self.customer, order).status_code, 200)  # bấm lại không tạo bản sao
        self.assertFalse(self.customer.get(f"/api/orders/{order['id']}").get_json()["can_save_to_history"])

    def test_claim_requires_customer_and_valid_token(self):
        order = self.order()
        for client, code in ((self.guest, 401), (self.owner, 403), (self.clients["admin"], 403)):
            self.assertEqual(self.claim(client, order).status_code, code)
        for token in ("", "wrong-token"):
            self.assertEqual(self.claim(self.customer, order, token).status_code, 404)
        self.assertEqual(self.claim(self.customer, {**order, "id": 999999}).status_code, 404)
        self.assertEqual(self.customer.get("/api/my/orders").get_json()["orders"], [])

    def test_cannot_transfer_another_customers_order_even_with_token(self):
        order = self.order(self.customer)
        self.assertEqual(self.claim(self.clients["customer_b"], order).status_code, 404)
        self.assertEqual(self.claim(self.customer, order).status_code, 200)
        self.assertEqual(self.clients["customer_b"].get("/api/my/orders").get_json()["orders"], [])

    def test_only_one_account_can_claim_guest_order(self):
        order = self.order()
        self.assertEqual(self.claim(self.customer, order).status_code, 200)
        self.assertEqual(self.claim(self.clients["customer_b"], order).status_code, 404)

    def test_owner_lists_only_complaints_from_own_shops(self):
        _, mine = self.complaint()
        self.complaint(self.clients["customer_b"], "b")
        rows = self.owner.get("/api/merchant/complaints").get_json()
        self.assertEqual((rows["total"], [r["id"] for r in rows["items"]]), (1, [mine]))
        self.assertNotIn("admin_reply", rows["items"][0])
        self.assertEqual(self.owner.get(f"/api/merchant/complaints?shop_id={self.shops['b']}").status_code, 403)

    def test_other_owner_cannot_reply_or_close_by_guessing_id(self):
        _, cid = self.complaint()
        other = self.clients["owner_b"]
        base = f"/api/merchant/complaints/{cid}"
        self.assertEqual(other.get("/api/merchant/complaints").get_json()["total"], 0)
        self.assertEqual(other.put(base + "/reply", json={"owner_reply": "Sửa trái phép"}).status_code, 404)
        self.assertEqual(other.put(base + "/close", json={}).status_code, 404)
        self.assertEqual(self.owner.get("/api/merchant/complaints").get_json()["items"][0]["status"], "OPEN")

    def test_guest_customer_admin_cannot_use_owner_endpoints(self):
        _, cid = self.complaint()
        for client, code in ((self.guest, 401), (self.customer, 403), (self.clients["admin"], 403)):
            self.assertEqual(client.get("/api/merchant/complaints").status_code, code)
            self.assertEqual(client.put(f"/api/merchant/complaints/{cid}/reply", json={"owner_reply": "X"}).status_code, code)
            self.assertEqual(client.put(f"/api/merchant/complaints/{cid}/close", json={}).status_code, code)

    def test_admin_endpoints_and_page_are_removed(self):
        admin = self.clients["admin"]
        self.assertEqual(admin.get("/api/admin/complaints").status_code, 404)
        self.assertIn(admin.put("/api/admin/complaints/1/reply", json={"admin_reply": "X"}).status_code, (404, 405))
        self.assertIn(admin.put("/api/admin/complaints/1/close", json={}).status_code, (404, 405))
        self.assertEqual(admin.get("/admin/complaints.html").status_code, 404)

    def test_owner_reply_close_and_customer_reads(self):
        order, cid = self.complaint()
        base = f"/api/merchant/complaints/{cid}"
        reply = "Xin lỗi bạn, quán sẽ bổ sung món còn thiếu."
        r = self.owner.put(base + "/reply", json={"owner_reply": reply})
        self.assertEqual((r.status_code, r.get_json()["status"]), (200, "REPLIED"))
        rows = self.customer.get(f"/api/orders/{order['id']}/complaints").get_json()
        self.assertEqual(rows[0]["owner_reply"], reply)
        self.assertEqual(self.owner.put(base + "/close", json={}).get_json()["status"], "CLOSED")
        self.assertEqual(self.owner.put(base + "/close", json={}).get_json()["status"], "CLOSED")
        self.assertEqual(self.owner.put(base + "/reply", json={"owner_reply": "Đổi"}).status_code, 409)
        self.assertEqual(self.customer.get(f"/api/my/orders/{order['id']}").get_json()["complaint_status"], "CLOSED")

    def test_close_requires_reply_and_reply_validation(self):
        _, cid = self.complaint()
        base = f"/api/merchant/complaints/{cid}"
        self.assertEqual(self.owner.put(base + "/close", json={}).status_code, 409)
        for reply in (None, 123, "  ", "x" * 2001):
            self.assertEqual(self.owner.put(base + "/reply", json={"owner_reply": reply}).status_code, 400)
        self.assertEqual(self.owner.put("/api/merchant/complaints/99999/reply", json={"owner_reply": "X"}).status_code, 404)

    def test_owner_filter_paging_and_bad_parameters(self):
        _, first = self.complaint()
        _, second = self.complaint()
        page = self.owner.get("/api/merchant/complaints?limit=1&offset=0&status=OPEN").get_json()
        self.assertEqual((page["total"], page["items"][0]["id"]), (2, second))
        self.assertEqual(self.owner.get("/api/merchant/complaints?limit=1&offset=1").get_json()["items"][0]["id"], first)
        self.assertEqual(self.owner.get("/api/merchant/complaints?status=CLOSED").get_json()["total"], 0)
        for query in ("limit=0", "limit=101", "limit=x", "offset=-1", "offset=x", "shop_id=x", "status=bad"):
            self.assertEqual(self.owner.get("/api/merchant/complaints?" + query).status_code, 400)

    def test_anonymous_customer_reads_owner_response_with_token(self):
        order, cid = self.complaint(self.guest)
        self.owner.put(f"/api/merchant/complaints/{cid}/reply", json={"owner_reply": "Quán đang kiểm tra."})
        path = f"/api/orders/{order['id']}/complaints"
        self.assertEqual(self.guest.get(path).status_code, 404)
        self.assertEqual(self.guest.get(path + "?token=" + order["access_token"]).get_json()[0]["owner_reply"], "Quán đang kiểm tra.")

    def test_old_database_reply_migrates_once_without_losing_data(self):
        order, cid = self.complaint()
        with self.qo.db() as c:
            c.execute("ALTER TABLE complaints RENAME COLUMN owner_reply TO admin_reply")
            c.execute("UPDATE complaints SET admin_reply = 'Phản hồi cũ', status = 'REPLIED' WHERE id = ?", (cid,))
        self.qo.init_db()
        rows = self.customer.get(f"/api/orders/{order['id']}/complaints").get_json()
        self.assertEqual(rows[0]["owner_reply"], "Phản hồi cũ")
        self.assertNotIn("admin_reply", rows[0])
        self.owner.put(f"/api/merchant/complaints/{cid}/reply", json={"owner_reply": "Phản hồi mới"})
        self.qo.init_db()
        self.assertEqual(self.customer.get(f"/api/orders/{order['id']}/complaints").get_json()[0]["owner_reply"], "Phản hồi mới")
        self.assertEqual(self.customer.get("/api/my/orders").get_json()["orders"][0]["id"], order["id"])


if __name__ == "__main__":
    unittest.main()
