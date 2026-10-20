"""
seed_data.py - Nạp dữ liệu giả cho QuickOrder Sprint 1 (theo quickorder_sprint1.sql)

Đặt file cùng thư mục với quickorder_sprint1.sql rồi chạy:
    python seed_data.py --reset            # xóa DB cũ, tạo lại từ schema, nạp dữ liệu
    python seed_data.py                    # thêm dữ liệu vào DB đã có bảng (dừng nếu đã nạp rồi)
    python seed_data.py --db test.db       # ghi ra file DB khác (mặc định: database.db)
    python seed_data.py --schema file.sql  # chọn file schema khác

Tài khoản demo - mật khẩu chung: Demo@1234
    admin@quickorder.vn                         (admin)
    owner1@quickorder.vn ... owner6@quickorder.vn (owner)
    khach1@quickorder.vn ... khach4@quickorder.vn (customer)
"""
import argparse
import os
import random
import secrets
import sqlite3
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

random.seed(7)
BASE = os.path.dirname(os.path.abspath(__file__))
PASSWORD = "Demo@1234"

ap = argparse.ArgumentParser()
ap.add_argument("--reset", action="store_true")
ap.add_argument("--db", default=os.path.join(BASE, "database.db"))
ap.add_argument("--schema", default=None)
args = ap.parse_args()

schema = args.schema or next(
    (p for p in (os.path.join(BASE, n) for n in ("quickorder_sprint1.sql", "quickorder_full_schema.sql", "schema.sql"))
     if os.path.exists(p)), None)
if not schema:
    raise SystemExit("Không tìm thấy file schema (quickorder_sprint1.sql) trong thư mục này.")

if args.reset and os.path.exists(args.db):
    os.remove(args.db)
conn = sqlite3.connect(args.db)
conn.execute("PRAGMA foreign_keys = ON")

# schema Sprint 1 có DROP TABLE nên chỉ chạy khi DB còn trống/--reset, tránh xóa nhầm dữ liệu
has_users = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
if not has_users:
    with open(schema, encoding="utf-8") as f:
        conn.executescript(f.read())
if conn.execute("SELECT 1 FROM users WHERE email='admin@quickorder.vn'").fetchone():
    raise SystemExit("DB đã có dữ liệu mẫu. Chạy lại với --reset để tạo mới.")

NOW = datetime.now().replace(microsecond=0)
ts = lambda d: d.strftime("%Y-%m-%d %H:%M:%S")
ago = lambda lo, hi: ts(NOW - timedelta(days=random.randint(lo, hi), hours=random.randint(0, 20)))
pw_hash = generate_password_hash(PASSWORD)

# ------------------------------------------------------------------ users
def add_user(name, email, phone, role, status="active"):
    t = ago(30, 90)
    return conn.execute(
        "INSERT INTO users(full_name,email,phone,password_hash,role,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (name, email, phone, pw_hash, role, status, t, t)).lastrowid

add_user("Quản trị viên", "admin@quickorder.vn", "0900000001", "admin")
OWNERS = ["Lê Thị Hồng", "Trịnh Văn Tài", "Nguyễn Thị Tư", "Phạm Thị Lan", "Vương Quốc Bảo", "Đỗ Thị Mai"]
owner_ids = [add_user(n, f"owner{i+1}@quickorder.vn", f"091100000{i+1}", "owner") for i, n in enumerate(OWNERS)]
for i, n in enumerate(["Nguyễn Văn An", "Trần Thị Bình", "Lê Hoàng Cường", "Phạm Minh Dũng"]):
    add_user(n, f"khach{i+1}@quickorder.vn", f"098800000{i+1}", "customer")
add_user("Khách Bị Khóa", "khoa@quickorder.vn", "0988000099", "customer", "locked")
add_user("Chủ Quán Bị Khóa", "owner_khoa@quickorder.vn", "0911000099", "owner", "locked")

# ------------------------------------------------------------------ categories (5 mục có sẵn trong schema)
conn.execute("INSERT OR IGNORE INTO categories(name,description,is_active) VALUES ('Món cũ (đã ẩn)','Danh mục ngừng dùng',0)")
cat = {n: i for i, n in conn.execute("SELECT id,name FROM categories")}

# ------------------------------------------------------------------ restaurants
# (key, chủ quán index, tên, địa chỉ, sđt, mở, đóng, trạng thái, lý do, số bàn)
SHOPS = [
    ("mayhong", 0, "Trà Sữa Mây Hồng", "12 Trần Đăng Ninh, Cầu Giấy, Hà Nội", "0243111001", "08:00", "22:00", "approved", None, 8),
    ("gocpho", 1, "Cà Phê Góc Phố", "45 Nguyễn Chí Thanh, Đống Đa, Hà Nội", "0243111002", "06:30", "23:00", "approved", None, 8),
    ("batu", 2, "Cơm Nhà Bà Tư", "89 Láng Hạ, Đống Đa, Hà Nội", "0243111003", "10:00", "21:00", "approved", None, 6),
    ("buncha", 3, "Bún Chả 36", "36 Phố Huế, Hai Bà Trưng, Hà Nội", "0243111004", "09:00", "20:00", "approved", None, 6),
    ("mayhong2", 0, "Trà Sữa Mây Hồng - Cơ sở 2", "88 Xuân Thủy, Cầu Giấy, Hà Nội", "0243111005", "08:00", "22:00", "approved", None, 4),  # 1 chủ, 2 quán
    ("pholan", 4, "Phở Gia Truyền Cô Lan", "27 Hàng Giày, Hoàn Kiếm, Hà Nội", "0243111006", "06:00", "14:00", "pending", None, 3),
    ("tracanh", 5, "Tiệm Trà Chanh Xanh", "5 Tây Sơn, Đống Đa, Hà Nội", "0243111007", "09:00", "21:00", "rejected", "Thiếu giấy phép kinh doanh", 3),
    ("nuocep", 5, "Quán Nước Ép Tươi", "101 Xuân Thủy, Cầu Giấy, Hà Nội", "0243111008", "07:00", "20:00", "locked", None, 3),
    ("chopending", 4, "Bánh Mì Sài Gòn", "15 Kim Mã, Ba Đình, Hà Nội", "0243111009", "06:00", "13:00", "pending", None, 2),
]
shop = {}
for key, oi, name, addr, phone, o, c, st, reason, ntables in SHOPS:
    t = ago(10, 60)
    rid = conn.execute(
        """INSERT INTO restaurants(owner_id,name,address,phone,open_time,close_time,status,rejection_reason,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (owner_ids[oi], name, addr, phone, o, c, st, reason, t, t)).lastrowid
    shop[key] = rid
    for n in range(1, ntables + 1):
        # bàn cuối của quán lớn để inactive, test menu QR từ chối bàn không hoạt động
        status = "inactive" if (ntables >= 6 and n == ntables) else "active"
        conn.execute("INSERT INTO restaurant_tables(restaurant_id,table_number,qr_token,status) VALUES (?,?,?,?)",
                     (rid, n, secrets.token_urlsafe(16), status))

# ------------------------------------------------------------------ dishes
# (danh mục, tên, giá, còn hàng, đã xóa)
MENU = {
    "mayhong": [("Trà sữa", "Trà sữa trân châu đường đen", 35000, 1, 0), ("Trà sữa", "Trà sữa matcha", 38000, 1, 0),
                ("Trà sữa", "Trà sữa khoai môn", 36000, 1, 0), ("Trà", "Trà đào cam sả", 33000, 1, 0),
                ("Trà", "Hồng trà macchiato", 32000, 0, 0), ("Nước giải khát", "Sinh tố bơ", 40000, 1, 0),
                ("Đồ ăn", "Khoai tây chiên", 25000, 1, 0), ("Trà sữa", "Trà sữa socola (ngừng bán)", 34000, 1, 1)],
    "gocpho": [("Cà phê", "Cà phê đen đá", 20000, 1, 0), ("Cà phê", "Cà phê sữa đá", 25000, 1, 0),
               ("Cà phê", "Bạc xỉu", 28000, 1, 0), ("Cà phê", "Cà phê muối", 32000, 1, 0),
               ("Cà phê", "Cappuccino", 45000, 0, 0), ("Nước giải khát", "Cacao đá xay", 40000, 1, 0),
               ("Đồ ăn", "Croissant bơ", 30000, 1, 0)],
    "batu": [("Đồ ăn", "Cơm sườn nướng", 45000, 1, 0), ("Đồ ăn", "Cơm gà xối mỡ", 42000, 1, 0),
             ("Đồ ăn", "Cơm thịt kho trứng", 40000, 1, 0), ("Đồ ăn", "Cơm chiên dương châu", 38000, 0, 0),
             ("Nước giải khát", "Nước chanh", 12000, 1, 0), ("Nước giải khát", "Trà đá", 3000, 1, 0)],
    "buncha": [("Đồ ăn", "Bún chả", 50000, 1, 0), ("Đồ ăn", "Bún chả nem cua bể", 65000, 1, 0),
               ("Đồ ăn", "Nem rán (phần)", 30000, 1, 0), ("Nước giải khát", "Trà tắc", 10000, 1, 0)],
    "mayhong2": [("Trà sữa", "Trà sữa trân châu đường đen", 35000, 1, 0), ("Trà", "Trà đào cam sả", 33000, 1, 0),
                 ("Cà phê", "Cà phê sữa đá", 25000, 1, 0)],
    "pholan": [("Đồ ăn", "Phở bò tái", 55000, 1, 0), ("Đồ ăn", "Phở bò đặc biệt", 70000, 1, 0), ("Đồ ăn", "Phở gà", 50000, 1, 0)],
    "tracanh": [("Trà", "Trà chanh", 15000, 1, 0), ("Nước giải khát", "Nước ép cam", 30000, 1, 0)],
    "nuocep": [("Nước giải khát", "Nước ép cam", 35000, 1, 0), ("Nước giải khát", "Nước ép dưa hấu", 30000, 1, 0)],
    "chopending": [("Đồ ăn", "Bánh mì thịt", 25000, 1, 0), ("Đồ ăn", "Bánh mì trứng", 20000, 1, 0)],
}
for key, items in MENU.items():
    for c, name, price, avail, deleted in items:
        t = ago(1, 30)
        conn.execute(
            """INSERT INTO dishes(restaurant_id,category_id,name,description,price,is_available,is_deleted,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (shop[key], cat[c], name, f"{name} - món bán chạy của quán", price, avail, deleted, t, t))

conn.commit()
print("Đã nạp dữ liệu vào", args.db)
for t in ["users", "restaurants", "restaurant_tables", "categories", "dishes"]:
    print(f"  {t:20}{conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>4}")
print(f"\nMật khẩu chung: {PASSWORD}  |  admin@quickorder.vn, owner1@quickorder.vn, khach1@quickorder.vn")
conn.close()