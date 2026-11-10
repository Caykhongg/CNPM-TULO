"""Quyền xem/hủy đơn từ trang theo dõi, bao gồm phiên khách trên thiết bị khác."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PASSWORD = "TrackingTest@123"


class CustomerTrackingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = generate_password_hash(PASSWORD)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {"QO_DB": str(Path(tmp.name) / "test.db"), "SECRET_KEY": "tracking-tests"})
        env.start()
        self.addCleanup(env.stop)
        sys.modules.pop("app", None)
        import app
        self.qo = app
        app.app.config["TESTING"] = True
        self.clients, self.ids = {}, {}
        with app.db() as c:
            for name, role in (("owner", "owner"), ("admin", "admin"), ("a", "customer"), ("b", "customer")):
                self.ids[name] = c.execute(
                    "INSERT INTO users(full_name,email,password_hash,role) VALUES (?,?,?,?)",
                    (name, name + "@tracking.test", self.password_hash, role),
                ).lastrowid
            self.shop = c.execute(
                "INSERT INTO shops(owner_id,name,address,phone,open_time,close_time,status) "
                "VALUES (?,'Quán thử','Test','0912345678','00:00','24:00','APPROVED')", (self.ids["owner"],),
            ).lastrowid
            self.table = c.execute(
                "INSERT INTO shop_tables(shop_id,table_number,qr_token) VALUES (?,'1','tracking-qr')", (self.shop,),
            ).lastrowid
            cat = c.execute("INSERT INTO categories(shop_id,name) VALUES (?,'Món thử')", (self.shop,)).lastrowid
            self.dish = c.execute(
                "INSERT INTO dishes(shop_id,category_id,name,price) VALUES (?,?,'Phở',40000)", (self.shop, cat),
            ).lastrowid
        for name, uid in self.ids.items():
            client = app.app.test_client()
            with client.session_transaction() as s:
                s["uid"] = uid
            self.clients[name] = client
        self.guest = app.app.test_client()

    def order(self, client=None):
        r = (client or self.guest).post("/api/orders", json={
            "shop_id": self.shop, "table_id": self.table,
            "items": [{"dish_id": self.dish, "quantity": 2}],
        })
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def test_customer_tracks_and_cancels_owned_order_from_another_session(self):
        order = self.order(self.clients["a"])
        other_device = self.qo.app.test_client()
        login = other_device.post("/api/login", json={"email": "a@tracking.test", "password": PASSWORD})
        self.assertEqual(login.status_code, 200)
        url = f"/api/orders/{order['id']}"
        details = other_device.get(url).get_json()
        self.assertEqual((details["shop_name"], details["table_number"], details["total_amount"]), ("Quán thử", "1", 80000))
        self.assertNotIn("access_hash", details)
        self.assertNotIn("user_id", details)
        cancelled = other_device.put(url + "/cancel", json={})
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.get_json()["status"], "CANCELLED")

    def test_other_customer_cannot_view_or_cancel_owned_order_without_token(self):
        order = self.order(self.clients["a"])
        url = f"/api/orders/{order['id']}"
        self.assertEqual(self.clients["b"].get(url).status_code, 404)
        self.assertEqual(self.clients["b"].put(url + "/cancel", json={}).status_code, 404)
        self.assertEqual(self.clients["a"].get(url).get_json()["status"], "PENDING")

    def test_owner_and_admin_use_owner_workflow_instead_of_customer_cancel(self):
        order = self.order()
        for name in ("owner", "admin"):
            self.assertEqual(self.clients[name].put(f"/api/orders/{order['id']}/cancel", json={}).status_code, 404)

    def test_guest_tracking_and_cancellation_still_require_correct_token(self):
        order = self.order()
        url = f"/api/orders/{order['id']}"
        self.assertEqual(self.guest.get(url).status_code, 404)
        self.assertEqual(self.guest.put(url + "/cancel", json={"token": "wrong"}).status_code, 404)
        self.assertEqual(self.guest.get(url + "?token=" + order["access_token"]).status_code, 200)
        self.assertEqual(self.guest.put(url + "/cancel", json={"token": order["access_token"]}).status_code, 200)

    def test_customer_cancel_loses_race_to_owner_confirmation(self):
        order = self.order(self.clients["a"])
        self.clients["owner"].put(f"/api/orders/{order['id']}/status", json={"status": "PREPARING"})
        r = self.clients["a"].put(f"/api/orders/{order['id']}/cancel", json={})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.clients["a"].get(f"/api/orders/{order['id']}").get_json()["status"], "PREPARING")

    def test_locked_account_cannot_cancel_without_order_token(self):
        order = self.order(self.clients["a"])
        with self.qo.db() as c:
            c.execute("UPDATE users SET is_active = 0 WHERE id = ?", (self.ids["a"],))
        self.assertEqual(self.clients["a"].put(f"/api/orders/{order['id']}/cancel", json={}).status_code, 404)

    def test_tracking_page_and_assets_are_served(self):
        for path in ("/customer/track.html", "/js/order-tracking.js", "/css/order-tracking.css"):
            with self.subTest(path=path):
                response = self.guest.get(path)
                self.assertEqual(response.status_code, 200)
                response.close()

    def test_delivery_status_is_rejected_by_backend(self):
        order = self.order()
        r = self.clients["owner"].put(f"/api/orders/{order['id']}/status", json={"status": "DELIVERING"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
