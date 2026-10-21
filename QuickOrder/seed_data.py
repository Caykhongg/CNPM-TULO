"""
seed_data.py - Nạp dữ liệu giả cho QuickOrder, khớp với schema.sql hiện tại của repo
(bảng: users, shops, shop_tables, categories, dishes, option_groups, options).

Đặt file cùng thư mục với app.py / schema.sql rồi chạy:
    python seed_data.py --reset    # xóa database.db cũ, tạo lại từ schema.sql, nạp dữ liệu
    python seed_data.py            # chỉ thêm dữ liệu vào database.db hiện có (dừng nếu đã nạp rồi)

Không sửa schema.sql, app.py hay init_db.py - chỉ thêm dữ liệu vào đúng các bảng đó.

Tài khoản demo - mật khẩu chung: Demo@1234 (>= 8 ký tự theo NFR-10)
    admin@quickorder.vn                           (admin)
    owner1@quickorder.vn ... owner6@quickorder.vn (owner)
    khach1@quickorder.vn ... khach4@quickorder.vn (customer)
"""
import os
import random
import secrets
import sqlite3
import sys
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

random.seed(7)
BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "database.db")          # cùng đường dẫn với app.py / init_db.py
SCHEMA = os.path.join(BASE, "schema.sql")
PASSWORD = "Demo@1234"

if "--reset" in sys.argv and os.path.exists(DB):
    os.remove(DB)

conn = sqlite3.connect(DB)
conn.execute("PRAGMA foreign_keys = ON")
with open(SCHEMA, encoding="utf-8") as f:
    conn.executescript(f.read())                # schema.sql an toàn khi chạy lại (IF NOT EXISTS)

if conn.execute("SELECT 1 FROM users WHERE email='owner1@quickorder.vn'").fetchone():
    raise SystemExit("DB đã có dữ liệu mẫu. Chạy lại với: python seed_data.py --reset")

NOW = datetime.now().replace(microsecond=0)
ago = lambda lo, hi: (NOW - timedelta(days=random.randint(lo, hi), hours=random.randint(0, 20))).strftime("%Y-%m-%d %H:%M:%S")
pw_hash = generate_password_hash(PASSWORD)

# ------------------------------------------------------------------ users
def add_user(name, email, phone, role, active=1):
    conn.execute("INSERT OR IGNORE INTO users(full_name,email,phone,password_hash,role,is_active,created_at) VALUES (?,?,?,?,?,?,?)",
                 (name, email, phone, pw_hash, role, active, ago(30, 90)))
    return conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]

add_user("Quản trị viên", "admin@quickorder.vn", "0900000001", "admin")
OWNERS = ["Lê Thị Hồng", "Trịnh Văn Tài", "Nguyễn Thị Tư", "Phạm Thị Lan", "Vương Quốc Bảo", "Đỗ Thị Mai"]
owner_ids = [add_user(n, f"owner{i+1}@quickorder.vn", f"091100000{i+1}", "owner") for i, n in enumerate(OWNERS)]
for i, n in enumerate(["Nguyễn Văn An", "Trần Thị Bình", "Lê Hoàng Cường", "Phạm Minh Dũng"]):
    add_user(n, f"khach{i+1}@quickorder.vn", f"098800000{i+1}", "customer")
add_user("Khách Bị Khóa", "khoa@quickorder.vn", "0988000099", "customer", 0)

# ------------------------------------------------------------------ categories (5 mục đã có sẵn trong schema.sql)
cat = {n: i for i, n in conn.execute("SELECT id,name FROM categories")}

# ------------------------------------------------------------------ shops + bàn/QR
# (key, index chủ quán, tên, địa chỉ, sđt, mở, đóng, trạng thái, ghi chú, số bàn)
SHOPS = [
    ("mayhong", 0, "Trà Sữa Mây Hồng", "12 Trần Đăng Ninh, Cầu Giấy, Hà Nội", "0243111001", "08:00", "22:00", "APPROVED", "", 8),
    ("gocpho", 1, "Cà Phê Góc Phố", "45 Nguyễn Chí Thanh, Đống Đa, Hà Nội", "0243111002", "06:30", "23:00", "APPROVED", "", 8),
    ("batu", 2, "Cơm Nhà Bà Tư", "89 Láng Hạ, Đống Đa, Hà Nội", "0243111003", "10:00", "21:00", "APPROVED", "", 6),
    ("buncha", 3, "Bún Chả 36", "36 Phố Huế, Hai Bà Trưng, Hà Nội", "0243111004", "09:00", "20:00", "APPROVED", "", 6),
    ("pholan", 4, "Phở Gia Truyền Cô Lan", "27 Hàng Giày, Hoàn Kiếm, Hà Nội", "0243111005", "06:00", "14:00", "PENDING", "", 3),
    ("pending2", 5, "Bánh Mì Sài Gòn", "15 Kim Mã, Ba Đình, Hà Nội", "0243111006", "06:00", "13:00", "PENDING", "", 2),
    ("tracanh", 0, "Tiệm Trà Chanh Xanh", "5 Tây Sơn, Đống Đa, Hà Nội", "0243111007", "09:00", "21:00", "REJECTED", "Thiếu giấy phép kinh doanh", 3),
    ("nuocep", 1, "Quán Nước Ép Tươi", "101 Xuân Thủy, Cầu Giấy, Hà Nội", "0243111008", "07:00", "20:00", "LOCKED", "Bị khiếu nại nhiều lần", 3),
]
shop = {}
for key, oi, name, addr, phone, o, c, st, note, ntables in SHOPS:
    sid = conn.execute(
        """INSERT INTO shops(owner_id,name,address,phone,open_time,close_time,status,status_note,created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (owner_ids[oi], name, addr, phone, o, c, st, note, ago(10, 60))).lastrowid
    shop[key] = sid
    for n in range(1, ntables + 1):
        conn.execute("INSERT INTO shop_tables(shop_id,table_number,qr_token) VALUES (?,?,?)",
                     (sid, f"Bàn {n}", secrets.token_urlsafe(16)))      # token sinh giống app.py

# ------------------------------------------------------------------ dishes + option_groups + options
SIZE = ("Size", 1, 0, [("M", 0), ("L", 5000)])                                   # bắt buộc, chọn 1
TOPPING = ("Topping", 0, 1, [("Trân châu", 5000), ("Thạch dừa", 5000), ("Pudding", 7000), ("Kem cheese", 10000)])
SUGAR = ("Mức đường", 0, 0, [("100%", 0), ("70%", 0), ("50%", 0), ("30%", 0)])
ICE = ("Mức đá", 0, 0, [("Bình thường", 0), ("Ít đá", 0), ("Không đá", 0)])
EXTRA = ("Ăn kèm", 0, 1, [("Trứng ốp la", 8000), ("Thêm cơm", 5000), ("Canh", 10000)])
NOODLE = ("Thêm", 0, 1, [("Thêm bún", 5000), ("Thêm nem", 15000), ("Thêm thịt", 20000)])

# (danh mục, tên món, giá, còn hàng, [nhóm tùy chọn], đã xóa)
MENU = {
    "mayhong": [("Trà sữa", "Trà sữa trân châu đường đen", 35000, 1, [SIZE, TOPPING, SUGAR, ICE], 0),
                ("Trà sữa", "Trà sữa matcha", 38000, 1, [SIZE, TOPPING, SUGAR, ICE], 0),
                ("Trà sữa", "Trà sữa khoai môn", 36000, 1, [SIZE, TOPPING, SUGAR], 0),
                ("Trà", "Trà đào cam sả", 33000, 1, [SIZE, SUGAR, ICE], 0),
                ("Trà", "Hồng trà macchiato", 32000, 0, [SIZE, SUGAR], 0),
                ("Nước giải khát", "Sinh tố bơ", 40000, 1, [SIZE], 0),
                ("Đồ ăn", "Khoai tây chiên", 25000, 1, [], 0),
                ("Trà sữa", "Trà sữa socola (ngừng bán)", 34000, 1, [], 1)],
    "gocpho": [("Cà phê", "Cà phê đen đá", 20000, 1, [SIZE, SUGAR], 0),
               ("Cà phê", "Cà phê sữa đá", 25000, 1, [SIZE, SUGAR], 0),
               ("Cà phê", "Bạc xỉu", 28000, 1, [SIZE, ICE], 0),
               ("Cà phê", "Cà phê muối", 32000, 1, [SIZE], 0),
               ("Cà phê", "Cappuccino", 45000, 0, [SIZE], 0),
               ("Nước giải khát", "Cacao đá xay", 40000, 1, [SIZE, TOPPING], 0),
               ("Đồ ăn", "Croissant bơ", 30000, 1, [], 0)],
    "batu": [("Đồ ăn", "Cơm sườn nướng", 45000, 1, [EXTRA], 0), ("Đồ ăn", "Cơm gà xối mỡ", 42000, 1, [EXTRA], 0),
             ("Đồ ăn", "Cơm thịt kho trứng", 40000, 1, [EXTRA], 0), ("Đồ ăn", "Cơm chiên dương châu", 38000, 0, [], 0),
             ("Nước giải khát", "Nước chanh", 12000, 1, [ICE], 0), ("Nước giải khát", "Trà đá", 3000, 1, [], 0)],
    "buncha": [("Đồ ăn", "Bún chả", 50000, 1, [NOODLE], 0), ("Đồ ăn", "Bún chả nem cua bể", 65000, 1, [NOODLE], 0),
               ("Đồ ăn", "Nem rán (phần)", 30000, 1, [], 0), ("Nước giải khát", "Trà tắc", 10000, 1, [ICE], 0)],
    "pholan": [("Đồ ăn", "Phở bò tái", 55000, 1, [], 0), ("Đồ ăn", "Phở bò đặc biệt", 70000, 1, [], 0),
               ("Đồ ăn", "Phở gà", 50000, 1, [], 0)],
    "pending2": [("Đồ ăn", "Bánh mì thịt", 25000, 1, [], 0), ("Đồ ăn", "Bánh mì trứng", 20000, 1, [], 0)],
    "tracanh": [("Trà", "Trà chanh", 15000, 1, [ICE], 0), ("Nước giải khát", "Nước ép cam", 30000, 1, [], 0)],
    "nuocep": [("Nước giải khát", "Nước ép cam", 35000, 1, [SIZE], 0), ("Nước giải khát", "Nước ép dưa hấu", 30000, 1, [], 0)],
}
for key, items in MENU.items():
    for c, name, price, avail, groups, deleted in items:
        did = conn.execute("INSERT INTO dishes(shop_id,category_id,name,price,is_available,is_deleted,created_at) VALUES (?,?,?,?,?,?,?)",
                           (shop[key], cat[c], name, price, avail, deleted, ago(1, 30))).lastrowid
        for gname, req, multi, opts in groups:
            gid = conn.execute("INSERT INTO option_groups(dish_id,name,is_required,is_multiple) VALUES (?,?,?,?)",
                               (did, gname, req, multi)).lastrowid
            for oname, extra in opts:
                conn.execute("INSERT INTO options(group_id,name,extra_price) VALUES (?,?,?)", (gid, oname, extra))

conn.commit()
print("Đã nạp dữ liệu vào", DB)
for t in ["users", "shops", "shop_tables", "categories", "dishes", "option_groups", "options"]:
    print(f"  {t:14}{conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>5}")
print(f"\nMật khẩu chung: {PASSWORD}  |  admin@quickorder.vn, owner1@quickorder.vn, khach1@quickorder.vn")
conn.close()
