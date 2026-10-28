"""Kiểm thử các lỗi tìm thấy khi rà soát Sprint 2.

Chạy từ thư mục QuickOrder:
    python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def load_app(tmp):
    os.environ["QO_DB"] = os.path.join(tmp, "test.db")
    os.environ["QO_UPLOADS"] = os.path.join(tmp, "uploads")
    os.environ["SECRET_KEY"] = "test-secret"
    sys.modules.pop("app", None)
    import app as qo
    return qo


class EmptyRequiredGroupTests(unittest.TestCase):
    """Chủ quán tạo nhóm bắt buộc trước, thêm tùy chọn sau: lúc chưa có tùy chọn, món vẫn phải đặt được."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.qo = load_app(self.tmp.name)
        self.qo.app.config["TESTING"] = True
        with self.qo.db() as c:
            cat = c.execute("SELECT id FROM categories WHERE name = 'Đồ ăn'").fetchone()[0]
            add = lambda sql, *a: c.execute(sql, a).lastrowid
            owner = add("INSERT INTO users(full_name, email, password_hash, role) VALUES ('A', 'a@quan.vn', 'x', 'owner')")
            self.shop = add("INSERT INTO shops(owner_id, name, address, phone, open_time, close_time, status) VALUES (?, 'Quán A', 'Đ1', '0900000000', '00:00', '24:00', 'APPROVED')", owner)
            self.table = add("INSERT INTO shop_tables(shop_id, table_number, qr_token) VALUES (?, '1', 'tok-1')", self.shop)
            self.dish = add("INSERT INTO dishes(shop_id, category_id, name, price) VALUES (?, ?, 'Trà', 30000)", self.shop, cat)
            self.group = add("INSERT INTO option_groups(dish_id, name, is_required, is_multiple) VALUES (?, 'Mức đá', 1, 0)", self.dish)

    def order(self, option_ids):
        return self.qo.app.test_client().post("/api/orders", json={
            "shop_id": self.shop, "table_id": self.table,
            "items": [{"dish_id": self.dish, "quantity": 1, "option_ids": option_ids}]})

    def test_required_group_without_options_does_not_block_ordering(self):
        resp = self.order([])
        self.assertEqual(resp.status_code, 201, resp.get_json())
        self.assertEqual(resp.get_json()["total_amount"], 30000)

    def test_group_becomes_required_once_it_has_options(self):
        with self.qo.db() as c:
            self.opt = c.execute("INSERT INTO options(group_id, name, extra_price) VALUES (?, 'Ít đá', 2000)", (self.group,)).lastrowid
        self.assertEqual(self.order([]).status_code, 400)                # đã có tùy chọn thì phải chọn
        resp = self.order([self.opt])
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["total_amount"], 32000)


if __name__ == "__main__":
    unittest.main()
