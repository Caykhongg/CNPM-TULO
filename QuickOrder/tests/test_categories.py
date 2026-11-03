"""Kiểm thử danh mục riêng cho từng quán: quyền thêm/xóa, món chỉ dùng danh mục của quán mình,
và nâng cấp CSDL cũ (danh mục dùng chung -> danh mục riêng cho từng quán).

Chạy từ thư mục QuickOrder:
    python -m unittest discover -s tests -v
"""
import os
import sqlite3
import sys
import tempfile
import unittest

from werkzeug.security import generate_password_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PW = "matkhau123"
DEFAULTS = {"Cà phê", "Trà", "Trà sữa", "Đồ ăn", "Nước giải khát"}


def load_app(path):
    """Nạp lại app với một CSDL riêng, để mỗi test bắt đầu từ dữ liệu trống."""
    os.environ["QO_DB"] = path
    os.environ["SECRET_KEY"] = "test-secret"
    sys.modules.pop("app", None)
    import app as qo
    return qo


class CategoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.qo = load_app(os.path.join(self.tmp.name, "test.db"))
        self.qo.app.config["TESTING"] = True
        with self.qo.db() as c:
            add = lambda sql, *a: c.execute(sql, a).lastrowid
            h = generate_password_hash(PW)
            self.owner_a = add("INSERT INTO users(full_name, email, password_hash, role) VALUES ('A', 'a@quan.vn', ?, 'owner')", h)
            self.owner_b = add("INSERT INTO users(full_name, email, password_hash, role) VALUES ('B', 'b@quan.vn', ?, 'owner')", h)
            add("INSERT INTO users(full_name, email, password_hash, role) VALUES ('Admin', 'admin@quan.vn', ?, 'admin')", h)
            self.shop_a = add("INSERT INTO shops(owner_id, name, address, phone, open_time, close_time, status) VALUES (?, 'Quán A', 'Đ1', '0900000000', '00:00', '24:00', 'APPROVED')", self.owner_a)
            self.shop_b = add("INSERT INTO shops(owner_id, name, address, phone, open_time, close_time, status) VALUES (?, 'Quán B', 'Đ2', '0900000001', '00:00', '24:00', 'APPROVED')", self.owner_b)
            self.shop_pending = add("INSERT INTO shops(owner_id, name, address, phone, open_time, close_time, status) VALUES (?, 'Quán chờ', 'Đ3', '0900000002', '00:00', '24:00', 'PENDING')", self.owner_b)
            # Cùng tên "Đồ ăn" ở hai quán: không xung đột vì mỗi quán có danh mục riêng
            self.cat_a = add("INSERT INTO categories(shop_id, name) VALUES (?, 'Đồ ăn')", self.shop_a)
            self.cat_b = add("INSERT INTO categories(shop_id, name) VALUES (?, 'Đồ ăn')", self.shop_b)
            self.cat_a_tra = add("INSERT INTO categories(shop_id, name) VALUES (?, 'Trà')", self.shop_a)
            self.cat_pending = add("INSERT INTO categories(shop_id, name) VALUES (?, 'Trà')", self.shop_pending)
            self.dish_a = add("INSERT INTO dishes(shop_id, category_id, name, price) VALUES (?, ?, 'Phở', 40000)", self.shop_a, self.cat_a)

    def login(self, email):
        client = self.qo.app.test_client()
        self.assertEqual(client.post("/api/login", json={"email": email, "password": PW}).status_code, 200)
        return client

    def category_ids(self, shop_id):
        with self.qo.db() as c:
            return {r[0] for r in c.execute("SELECT id FROM categories WHERE shop_id = ?", (shop_id,))}

    # ----- quyền thêm và xóa -----
    def test_owner_cannot_delete_another_shops_category(self):
        b = self.login("b@quan.vn")
        self.assertEqual(b.delete(f"/api/categories/{self.cat_a_tra}").status_code, 403)
        self.assertIn(self.cat_a_tra, self.category_ids(self.shop_a))

    def test_owner_cannot_add_category_to_another_shop(self):
        b = self.login("b@quan.vn")
        resp = b.post("/api/categories", json={"shop_id": self.shop_a, "name": "Lạ"})
        self.assertEqual(resp.status_code, 403)

    def test_owner_can_add_then_delete_own_unused_category(self):
        a = self.login("a@quan.vn")
        resp = a.post("/api/categories", json={"shop_id": self.shop_a, "name": "Sinh tố"})
        self.assertEqual(resp.status_code, 201)
        cid = resp.get_json()["id"]
        self.assertEqual(a.delete(f"/api/categories/{cid}").status_code, 204)

    def test_category_name_must_be_unique_within_shop_only(self):
        a = self.login("a@quan.vn")
        b = self.login("b@quan.vn")
        # Lưu ý: SQLite NOCASE chỉ không phân biệt chữ ASCII, nên "Đ"/"đ" vẫn được coi là khác nhau
        self.assertEqual(a.post("/api/categories", json={"shop_id": self.shop_a, "name": "Đồ ăn"}).status_code, 409)
        self.assertEqual(b.post("/api/categories", json={"shop_id": self.shop_b, "name": "Trà"}).status_code, 201)

    def test_category_used_by_dish_cannot_be_deleted(self):
        a = self.login("a@quan.vn")
        self.assertEqual(a.delete(f"/api/categories/{self.cat_a}").status_code, 409)
        self.assertIn(self.cat_a, self.category_ids(self.shop_a))

    def test_soft_deleted_dish_still_keeps_category(self):
        with self.qo.db() as c:
            c.execute("INSERT INTO dishes(shop_id, category_id, name, price, is_deleted) VALUES (?, ?, 'Cũ', 1000, 1)",
                      (self.shop_a, self.cat_a_tra))
        a = self.login("a@quan.vn")
        self.assertEqual(a.delete(f"/api/categories/{self.cat_a_tra}").status_code, 409)
        flags = {r["id"]: r["in_use"] for r in a.get(f"/api/categories?shop_id={self.shop_a}").get_json()}
        self.assertTrue(flags[self.cat_a_tra])

    def test_owner_cannot_rename_category(self):
        a = self.login("a@quan.vn")
        self.assertEqual(a.put(f"/api/categories/{self.cat_a_tra}", json={"name": "Trà sữa"}).status_code, 403)

    # ----- danh sách và quyền đọc -----
    def test_list_shows_own_categories_with_in_use_flag(self):
        a = self.login("a@quan.vn")
        rows = a.get(f"/api/categories?shop_id={self.shop_a}").get_json()
        self.assertEqual({r["name"]: r["in_use"] for r in rows}, {"Đồ ăn": True, "Trà": False})

    def test_customer_sees_categories_only_of_approved_shops(self):
        anon = self.qo.app.test_client()
        self.assertEqual(len(anon.get(f"/api/categories?shop_id={self.shop_a}").get_json()), 2)
        self.assertEqual(anon.get(f"/api/categories?shop_id={self.shop_pending}").get_json(), [])

    # ----- món chỉ dùng danh mục của quán mình -----
    def test_dish_cannot_use_another_shops_category(self):
        a = self.login("a@quan.vn")
        resp = a.post("/api/dishes", json={"shop_id": self.shop_a, "category_id": self.cat_b, "name": "Bún", "price": 30000})
        self.assertEqual(resp.status_code, 400)
        resp = a.put(f"/api/dishes/{self.dish_a}", json={"category_id": self.cat_b})
        self.assertEqual(resp.status_code, 400)

    def test_dish_can_use_own_shop_category(self):
        a = self.login("a@quan.vn")
        resp = a.post("/api/dishes", json={"shop_id": self.shop_a, "category_id": self.cat_a_tra, "name": "Trà đào", "price": 30000})
        self.assertEqual(resp.status_code, 201)

    # ----- quán mới và quyền quản trị -----
    def test_new_shop_gets_default_categories(self):
        b = self.login("b@quan.vn")
        resp = b.post("/api/shops", json={"name": "Quán mới", "address": "Đ9", "phone": "0900000009",
                                           "open_time": "07:00", "close_time": "22:00"})
        self.assertEqual(resp.status_code, 201)
        sid = resp.get_json()["id"]
        names = {r["name"] for r in b.get(f"/api/categories?shop_id={sid}").get_json()}
        self.assertEqual(names, DEFAULTS)

    def test_admin_can_delete_shop_with_categories_and_dishes(self):
        admin = self.login("admin@quan.vn")
        self.assertEqual(admin.delete(f"/api/shops/{self.shop_a}").status_code, 204)
        self.assertEqual(self.category_ids(self.shop_a), set())


class MigrationTests(unittest.TestCase):
    def test_shared_categories_become_per_shop(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "old.db")
            conn = sqlite3.connect(path)
            with open(os.path.join(ROOT, "schema.sql"), encoding="utf-8") as f:
                conn.executescript(f.read())
            # Đưa bảng danh mục về kiểu cũ: một danh mục dùng chung cho mọi quán
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DROP TABLE categories")
            conn.execute("CREATE TABLE categories (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                         "name TEXT NOT NULL UNIQUE COLLATE NOCASE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            conn.executemany("INSERT INTO categories (id, name) VALUES (?, ?)",
                             [(1, "Cà phê"), (2, "Đồ ăn"), (3, "Topping"), (4, "Lạ")])
            conn.execute("INSERT INTO users (id, full_name, email, password_hash, role) VALUES "
                         "(1, 'A', 'a@quan.vn', 'x', 'owner'), (2, 'B', 'b@quan.vn', 'x', 'owner')")
            conn.execute("INSERT INTO shops (id, owner_id, name, address, phone, open_time, close_time, status) VALUES "
                         "(1, 1, 'Quán A', 'Đ1', '0900000000', '00:00', '24:00', 'APPROVED'), "
                         "(2, 2, 'Quán B', 'Đ2', '0900000001', '00:00', '24:00', 'APPROVED')")
            conn.execute("INSERT INTO dishes (id, shop_id, category_id, name, price, is_deleted) VALUES "
                         "(1, 1, 2, 'Phở', 40000, 0), (2, 1, 3, 'Trân châu', 5000, 0), "
                         "(3, 2, 1, 'Cà phê đen', 20000, 0), (4, 2, 3, 'Món đã xóa', 9000, 1)")
            conn.commit()
            conn.close()

            qo = load_app(path)
            with qo.db() as c:
                dishes = {r["id"]: (r["cat_name"], r["cat_shop"], r["shop_id"]) for r in c.execute(
                    "SELECT d.id, d.shop_id, cat.name AS cat_name, cat.shop_id AS cat_shop FROM dishes d "
                    "JOIN categories cat ON cat.id = d.category_id")}
                per_shop = {}
                for r in c.execute("SELECT shop_id, name FROM categories"):
                    per_shop.setdefault(r["shop_id"], set()).add(r["name"])
                fk_problems = c.execute("PRAGMA foreign_key_check").fetchall()

            self.assertEqual(dishes[1], ("Đồ ăn", 1, 1))
            self.assertEqual(dishes[2], ("Topping", 1, 1))
            self.assertEqual(dishes[3], ("Cà phê", 2, 2))
            self.assertEqual(dishes[4], ("Topping", 2, 2))     # món đã xóa mềm vẫn được chuyển
            self.assertEqual(per_shop[1], DEFAULTS | {"Topping"})
            self.assertEqual(per_shop[2], DEFAULTS | {"Topping"})
            self.assertFalse(any("Lạ" in names for names in per_shop.values()))   # danh mục không ai dùng bị bỏ
            self.assertEqual(fk_problems, [])

            load_app(path)                                    # khởi động lại: không nâng cấp lần nữa, không lỗi


if __name__ == "__main__":
    unittest.main()
