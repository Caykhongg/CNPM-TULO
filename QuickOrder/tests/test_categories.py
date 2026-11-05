"""Kiểm thử danh mục hai loại: danh mục chung do admin quản lý (shop_id NULL) và danh mục riêng của từng quán.
Gồm quyền thêm/xóa, món dùng được danh mục nào, và nâng cấp CSDL cũ.

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
            # Danh mục chung mặc định (shop_id NULL), do init_db tạo sẵn
            self.shared_tra = c.execute("SELECT id FROM categories WHERE name = 'Trà' AND shop_id IS NULL").fetchone()[0]
            self.shared_do_an = c.execute("SELECT id FROM categories WHERE name = 'Đồ ăn' AND shop_id IS NULL").fetchone()[0]
            # Danh mục riêng của từng quán; "Đồ ăn" của quán A và B không xung đột vì khác quán
            self.cat_a = add("INSERT INTO categories(shop_id, name) VALUES (?, 'Món ký')", self.shop_a)
            self.cat_b = add("INSERT INTO categories(shop_id, name) VALUES (?, 'Món ký')", self.shop_b)
            self.cat_a_tra = add("INSERT INTO categories(shop_id, name) VALUES (?, 'Topping')", self.shop_a)
            self.dish_a = add("INSERT INTO dishes(shop_id, category_id, name, price) VALUES (?, ?, 'Phở', 40000)", self.shop_a, self.cat_a)

    def login(self, email):
        client = self.qo.app.test_client()
        self.assertEqual(client.post("/api/login", json={"email": email, "password": PW}).status_code, 200)
        return client

    def own_category_ids(self, shop_id):
        with self.qo.db() as c:
            return {r[0] for r in c.execute("SELECT id FROM categories WHERE shop_id = ?", (shop_id,))}

    # ----- quyền thêm và xóa danh mục riêng -----
    def test_owner_cannot_delete_another_shops_category(self):
        b = self.login("b@quan.vn")
        self.assertEqual(b.delete(f"/api/categories/{self.cat_a_tra}").status_code, 403)
        self.assertIn(self.cat_a_tra, self.own_category_ids(self.shop_a))

    def test_owner_cannot_add_category_to_another_shop(self):
        b = self.login("b@quan.vn")
        self.assertEqual(b.post("/api/categories", json={"shop_id": self.shop_a, "name": "Lạ"}).status_code, 403)

    def test_owner_can_add_then_delete_own_unused_category(self):
        a = self.login("a@quan.vn")
        resp = a.post("/api/categories", json={"shop_id": self.shop_a, "name": "Sinh tố"})
        self.assertEqual(resp.status_code, 201)
        cid = resp.get_json()["id"]
        self.assertEqual(a.delete(f"/api/categories/{cid}").status_code, 204)

    def test_names_unique_within_shop_and_against_shared(self):
        a = self.login("a@quan.vn")
        b = self.login("b@quan.vn")
        self.assertEqual(a.post("/api/categories", json={"shop_id": self.shop_a, "name": "Món ký"}).status_code, 409)
        self.assertEqual(a.post("/api/categories", json={"shop_id": self.shop_a, "name": "Trà"}).status_code, 409)   # trùng danh mục chung
        self.assertEqual(a.post("/api/categories", json={"shop_id": self.shop_a, "name": "Đậu hũ"}).status_code, 201)
        # Quán khác dùng được cùng tên với quán A
        self.assertEqual(b.post("/api/categories", json={"shop_id": self.shop_b, "name": "Đậu hũ"}).status_code, 201)

    def test_category_used_by_dish_cannot_be_deleted(self):
        a = self.login("a@quan.vn")
        self.assertEqual(a.delete(f"/api/categories/{self.cat_a}").status_code, 409)
        self.assertIn(self.cat_a, self.own_category_ids(self.shop_a))

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

    # ----- danh mục chung do admin quản lý -----
    def test_owner_cannot_create_or_delete_shared_category(self):
        a = self.login("a@quan.vn")
        self.assertEqual(a.post("/api/categories", json={"name": "Lạ"}).status_code, 403)
        self.assertEqual(a.delete(f"/api/categories/{self.shared_tra}").status_code, 403)

    def test_admin_adds_shared_category_visible_to_every_shop(self):
        admin = self.login("admin@quan.vn")
        resp = admin.post("/api/categories", json={"name": "Đồ uống mới"})
        self.assertEqual(resp.status_code, 201)
        cid = resp.get_json()["id"]
        a = self.login("a@quan.vn")
        names = {r["name"] for r in a.get(f"/api/categories?shop_id={self.shop_a}").get_json()}
        self.assertIn("Đồ uống mới", names)
        self.assertEqual(a.post(f"/api/dishes", json={"shop_id": self.shop_a, "category_id": cid, "name": "Sữa", "price": 20000}).status_code, 201)

    def test_dish_can_use_shared_category(self):
        a = self.login("a@quan.vn")
        resp = a.post("/api/dishes", json={"shop_id": self.shop_a, "category_id": self.shared_do_an, "name": "Bánh mì", "price": 25000})
        self.assertEqual(resp.status_code, 201)

    def test_dish_cannot_use_another_shops_category(self):
        a = self.login("a@quan.vn")
        self.assertEqual(a.post("/api/dishes", json={"shop_id": self.shop_a, "category_id": self.cat_b, "name": "Bún", "price": 30000}).status_code, 400)
        self.assertEqual(a.put(f"/api/dishes/{self.dish_a}", json={"category_id": self.cat_b}).status_code, 400)

    def test_dish_can_use_own_shop_category(self):
        a = self.login("a@quan.vn")
        resp = a.post("/api/dishes", json={"shop_id": self.shop_a, "category_id": self.cat_a_tra, "name": "Trà đào", "price": 30000})
        self.assertEqual(resp.status_code, 201)

    def test_shared_category_in_use_cannot_be_deleted_by_admin(self):
        with self.qo.db() as c:
            c.execute("INSERT INTO dishes(shop_id, category_id, name, price) VALUES (?, ?, 'Bánh', 15000)",
                      (self.shop_b, self.shared_do_an))
        admin = self.login("admin@quan.vn")
        self.assertEqual(admin.delete(f"/api/categories/{self.shared_do_an}").status_code, 409)
        self.assertEqual(admin.delete(f"/api/categories/{self.shared_tra}").status_code, 204)   # không món nào dùng thì xóa được

    # ----- danh sách và quyền đọc -----
    def test_list_shows_shared_and_own_categories_with_in_use_flag(self):
        a = self.login("a@quan.vn")
        rows = a.get(f"/api/categories?shop_id={self.shop_a}").get_json()
        own = {r["name"]: r["in_use"] for r in rows if r["shop_id"] == self.shop_a}
        self.assertEqual(own, {"Món ký": True, "Topping": False})
        self.assertTrue(any(r["shop_id"] is None for r in rows))

    def test_customer_sees_shared_always_and_own_only_for_approved_shops(self):
        anon = self.qo.app.test_client()
        rows_a = anon.get(f"/api/categories?shop_id={self.shop_a}").get_json()
        self.assertEqual(len([r for r in rows_a if r["shop_id"] == self.shop_a]), 2)
        rows_pending = anon.get(f"/api/categories?shop_id={self.shop_pending}").get_json()
        self.assertTrue(rows_pending)
        self.assertTrue(all(r["shop_id"] is None for r in rows_pending))

    def test_admin_list_global_only(self):
        admin = self.login("admin@quan.vn")
        rows = admin.get("/api/categories?global=1").get_json()
        self.assertTrue(rows)
        self.assertTrue(all(r["shop_id"] is None for r in rows))

    # ----- quán mới và quyền quản trị -----
    def test_new_shop_sees_shared_categories(self):
        b = self.login("b@quan.vn")
        resp = b.post("/api/shops", json={"name": "Quán mới", "address": "Đ9", "phone": "0900000009",
                                           "open_time": "07:00", "close_time": "22:00"})
        self.assertEqual(resp.status_code, 201)
        sid = resp.get_json()["id"]
        names = {r["name"] for r in b.get(f"/api/categories?shop_id={sid}").get_json()}
        self.assertTrue(DEFAULTS <= names)

    def test_admin_can_delete_shop_with_categories_and_dishes(self):
        admin = self.login("admin@quan.vn")
        self.assertEqual(admin.delete(f"/api/shops/{self.shop_a}").status_code, 204)
        self.assertEqual(self.own_category_ids(self.shop_a), set())


class MigrationTests(unittest.TestCase):
    def test_old_shared_categories_keep_ids_and_dishes(self):
        """CSDL cũ: danh mục dùng chung không có shop_id, tên duy nhất toàn hệ thống.
        Sau nâng cấp: giữ nguyên id để món không đổi, thêm bộ danh mục chung mặc định còn thiếu."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "old.db")
            conn = sqlite3.connect(path)
            with open(os.path.join(ROOT, "schema.sql"), encoding="utf-8") as f:
                conn.executescript(f.read())
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
                dishes = {r["id"]: (r["cat_name"], r["cat_shop"]) for r in c.execute(
                    "SELECT d.id, cat.name AS cat_name, cat.shop_id AS cat_shop FROM dishes d "
                    "JOIN categories cat ON cat.id = d.category_id")}
                shared = {r["name"] for r in c.execute("SELECT name FROM categories WHERE shop_id IS NULL")}
                index_ok = c.execute("SELECT 1 FROM sqlite_master WHERE name = 'ux_categories_global'").fetchone()
                fk_problems = c.execute("PRAGMA foreign_key_check").fetchall()

            self.assertEqual(dishes[1], ("Đồ ăn", None))
            self.assertEqual(dishes[2], ("Topping", None))
            self.assertEqual(dishes[3], ("Cà phê", None))
            self.assertEqual(dishes[4], ("Topping", None))      # món đã xóa mềm vẫn giữ danh mục
            self.assertTrue(DEFAULTS <= shared)
            self.assertIn("Lạ", shared)                          # danh mục chung cũ không bị bỏ
            self.assertIsNotNone(index_ok)
            self.assertEqual(fk_problems, [])

            load_app(path)                                       # khởi động lại: không nâng cấp lần nữa, không lỗi


if __name__ == "__main__":
    unittest.main()
