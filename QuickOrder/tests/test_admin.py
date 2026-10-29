import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PW = "AdminTest@123"


class AdminTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw_hash = generate_password_hash(PW)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {
            "QO_DB": os.path.join(tmp.name, "test.db"),
            "SECRET_KEY": "admin-tests-only",
        })
        env.start()
        self.addCleanup(env.stop)
        sys.modules.pop("app", None)
        import app
        self.qo = app
        app.app.config["TESTING"] = True
        with app.db() as c:
            self.ids = {}
            for role in ("admin", "owner", "customer"):
                self.ids[role] = c.execute(
                    "INSERT INTO users(full_name,email,password_hash,role) VALUES (?,?,?,?)",
                    (role, role + "@test.local", self.pw_hash, role),
                ).lastrowid
            self.shop = c.execute(
                "INSERT INTO shops(owner_id,name,address,phone,open_time,close_time,status) "
                "VALUES (?,'Test','A','0912345678','00:00','24:00','APPROVED')",
                (self.ids["owner"],),
            ).lastrowid
            self.table = c.execute(
                "INSERT INTO shop_tables(shop_id,table_number,qr_token) VALUES (?,'1','test-qr')",
                (self.shop,),
            ).lastrowid
            self.cat = c.execute("SELECT id FROM categories LIMIT 1").fetchone()[0]
            self.dish = c.execute(
                "INSERT INTO dishes(shop_id,category_id,name,price) VALUES (?,?,'Tea',20000)",
                (self.shop, self.cat),
            ).lastrowid
            self.order = c.execute(
                "INSERT INTO orders(shop_id,status,total_amount,access_hash) VALUES (?,'COMPLETED',20000,?)",
                (self.shop, app.token_hash("test-token")),
            ).lastrowid
        self.guest = app.app.test_client()
        self.clients = {}
        for role in self.ids:
            client = app.app.test_client()
            with client.session_transaction() as s:
                s["uid"] = self.ids[role]
            self.clients[role] = client
        self.admin = self.clients["admin"]

    def complaint(self):
        r = self.guest.post(f"/api/orders/{self.order}/complaints", json={
            "token": "test-token", "content": "Nhờ quản trị viên kiểm tra đơn giúp tôi."
        })
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()["id"]

    def test_permissions(self):
        paths = [("GET", "/api/admin/users", None),
                 ("GET", "/api/admin/statistics", None),
                 ("GET", "/api/admin/complaints", None),
                 ("PUT", f"/api/admin/users/{self.ids['customer']}/status", {"is_active": False}),
                 ("PUT", "/api/admin/complaints/1/reply", {"admin_reply": "Đã nhận"}),
                 ("PUT", "/api/admin/complaints/1/close", {})]
        for client, code in [(self.guest, 401), (self.clients["owner"], 403), (self.clients["customer"], 403)]:
            for method, path, body in paths:
                with self.subTest(path=path, code=code):
                    self.assertEqual(client.open(path, method=method, json=body).status_code, code)

    def test_fr51_lock_unlock_same_qr(self):
        body = {"shop_id": self.shop, "table_id": self.table,
                "items": [{"dish_id": self.dish, "quantity": 1}]}
        self.assertEqual(self.guest.post("/api/orders", json=body).status_code, 201)
        self.admin.put(f"/api/shops/{self.shop}", json={"status": "LOCKED"})
        self.assertEqual(self.guest.get(f"/api/shops/{self.shop}").status_code, 404)
        self.assertEqual(self.guest.post("/api/orders", json=body).status_code, 404)
        self.admin.put(f"/api/shops/{self.shop}", json={"status": "APPROVED"})
        self.assertEqual(self.guest.get("/api/qr/test-qr").get_json()["shop"]["status"], "APPROVED")
        self.assertEqual(self.guest.post("/api/orders", json=body).status_code, 201)

    def test_fr51_owner_cannot_unlock(self):
        url = f"/api/shops/{self.shop}"
        self.admin.put(url, json={"status": "LOCKED"})
        self.clients["owner"].put(url, json={"status": "APPROVED"})
        self.assertEqual(self.admin.get(url).get_json()["status"], "LOCKED")

    def test_fr52_search_no_password(self):
        r = self.admin.get("/api/admin/users?q=customer&role=customer")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 1)
        self.assertEqual(r.get_json()["items"][0]["id"], self.ids["customer"])
        self.assertNotIn("password_hash", r.get_json()["items"][0])

    def test_fr52_lock_session_and_login(self):
        url = f"/api/admin/users/{self.ids['customer']}/status"
        creds = {"email": "customer@test.local", "password": PW}
        self.assertEqual(self.admin.put(url, json={"is_active": False}).status_code, 200)
        self.assertEqual(self.clients["customer"].get("/api/me").status_code, 401)
        self.assertEqual(self.guest.post("/api/login", json=creds).status_code, 403)
        self.admin.put(url, json={"is_active": True})
        self.assertEqual(self.guest.post("/api/login", json=creds).status_code, 200)

    def test_fr52_self_lock_and_role_change_denied(self):
        url = f"/api/admin/users/{self.ids['admin']}/status"
        self.assertEqual(self.admin.put(url, json={"is_active": False}).status_code, 409)
        url = f"/api/admin/users/{self.ids['customer']}/status"
        self.assertEqual(self.admin.put(url, json={"is_active": True, "role": "admin"}).status_code, 400)

    def test_fr53_crud_and_duplicate(self):
        r = self.admin.post("/api/categories", json={"name": "  Món test  "})
        self.assertEqual(r.status_code, 201)
        cid = r.get_json()["id"]
        self.assertEqual(r.get_json()["name"], "Món test")
        self.assertEqual(self.admin.post("/api/categories", json={"name": "Món test"}).status_code, 409)
        self.assertEqual(self.admin.put(f"/api/categories/{cid}", json={"name": "Món sửa"}).status_code, 200)
        self.assertEqual(self.admin.delete(f"/api/categories/{cid}").status_code, 204)
        self.assertEqual(self.admin.get(f"/api/categories/{cid}").status_code, 404)

    def test_fr53_invalid_and_in_use(self):
        for name in (" ", "x" * 101, 123):
            self.assertEqual(self.admin.post("/api/categories", json={"name": name}).status_code, 400)
        self.assertEqual(self.admin.delete(f"/api/categories/{self.cat}").status_code, 409)

    def test_fr54_multiple_shops_completed_only(self):
        with self.qo.db() as c:
            other = c.execute(
                "INSERT INTO shops(owner_id,name,address,phone) VALUES (?,'Other','B','0912345678')",
                (self.ids["owner"],),
            ).lastrowid
            c.executemany("INSERT INTO orders(shop_id,status,total_amount) VALUES (?,?,?)", [
                (other, "COMPLETED", 30000), (other, "CANCELLED", 90000), (other, "PENDING", 80000)
            ])
        self.assertEqual(self.admin.get("/api/admin/statistics").get_json(),
                         {"shops": 2, "users": 3, "orders": 4, "revenue": 50000})

    def test_fr55_reply_close_customer_reads(self):
        cid = self.complaint()
        base = f"/api/admin/complaints/{cid}"
        self.assertEqual(self.admin.get("/api/admin/complaints?status=OPEN").get_json()["total"], 1)
        r = self.admin.put(base + "/reply", json={"admin_reply": "Đã liên hệ quán."})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "REPLIED")
        rows = self.guest.get(f"/api/orders/{self.order}/complaints?token=test-token").get_json()
        self.assertEqual(rows[0]["admin_reply"], "Đã liên hệ quán.")
        self.assertEqual(self.admin.put(base + "/close", json={}).get_json()["status"], "CLOSED")
        self.assertEqual(self.admin.get("/api/admin/complaints?status=CLOSED").get_json()["total"], 1)
        self.assertEqual(self.admin.put(base + "/reply", json={"admin_reply": "Sửa"}).status_code, 409)

    def test_fr55_requires_reply_and_correct_token(self):
        cid = self.complaint()
        base = f"/api/admin/complaints/{cid}"
        self.assertEqual(self.admin.put(base + "/close", json={}).status_code, 409)
        self.assertEqual(self.admin.put(base + "/reply", json={"admin_reply": " "}).status_code, 400)
        self.assertEqual(self.guest.get(f"/api/orders/{self.order}/complaints?token=wrong").status_code, 404)


if __name__ == "__main__":
    unittest.main()
