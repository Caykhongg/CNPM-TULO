"""Thêm quán, bàn và món để thử đặt đơn trong CSDL QuickOrder local hiện tại.

Chạy tại folder repo hoặc QuickOrder:
    python seed_order_local.py

Có thể chạy file tải về từ Downloads khi terminal đang ở folder repo.
Dùng quán của tài khoản chủ quán đã có:
    python seed_order_local.py --owner-email "email-chu-quan-cua-ban"

Không gửi email, không gọi xAPI, không tạo giao dịch/đơn hàng giả.
"""

import argparse
from contextlib import closing
from datetime import datetime
import os
from pathlib import Path
import secrets
import sqlite3
import sys
from urllib.parse import urlencode


OWNER_EMAIL = "owner.order@quickorder.local"
CUSTOMER_EMAIL = "customer.order@quickorder.local"
PASSWORD = "Order@123456"
SHOP_NAME = "Quán thử đặt món QuickOrder"
MENU = (
    ("Đồ ăn", "Cơm gà", 25000),
    ("Đồ ăn", "Mì xào bò", 30000),
    ("Đồ ăn", "Bánh mì trứng", 15000),
    ("Nước uống", "Trà đào", 12000),
    ("Nước uống", "Trà đá thử thanh toán", 2000),
)


class SeedError(Exception):
    pass


def find_app_dir(project_dir=None):
    candidates = [project_dir] if project_dir else [Path.cwd(), Path(__file__).resolve().parent]
    for candidate in candidates:
        candidate = Path(candidate).expanduser().resolve()
        for path in (candidate / "QuickOrder", candidate):
            if (path / "app.py").is_file() and (path / "schema.sql").is_file():
                return path
    raise SeedError("Hãy mở terminal ở CNPM-TULO-FRESH hoặc QuickOrder rồi chạy lại.")


def backup_database(path):
    if not path.exists():
        return None
    folder = Path.home() / "QuickOrder-local-backups"
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / ("before-seed-" + datetime.now().strftime("%Y%m%d-%H%M%S")
                            + "-" + secrets.token_hex(3) + ".db")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(destination)) as target:
            source.backup(target)
    return destination


def seed(c, password_hash, owner_email=OWNER_EMAIL, existing_owner=False):
    """Chỉ thêm dữ liệu còn thiếu. Không đổi mật khẩu, ngân hàng hay giá món cũ."""
    def account(email, name, role, allow_create=True):
        row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if row:
            if row["role"] != role or not row["is_active"]:
                raise SeedError(f"Tài khoản {email} bị khóa hoặc không có vai trò {role}.")
            return row, False
        if not allow_create:
            raise SeedError(f"Không tìm thấy tài khoản chủ quán {email} trong CSDL này.")
        cur = c.execute(
            "INSERT INTO users(full_name,email,phone,password_hash,role) VALUES (?,?,?,?,?)",
            (name, email, "0900000000", password_hash, role),
        )
        return c.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone(), True

    c.execute("BEGIN IMMEDIATE")
    owner, owner_created = account(owner_email, "Chủ quán thử order", "owner", not existing_owner)
    customer, customer_created = account(CUSTOMER_EMAIL, "Khách thử order", "customer")
    # Giao diện chủ quán hiện dùng quán đầu tiên của tài khoản: dùng cùng quán đó.
    shop = c.execute("SELECT * FROM shops WHERE owner_id=? ORDER BY id LIMIT 1", (owner["id"],)).fetchone()
    shop_created = shop is None
    if shop is None:
        cur = c.execute(
            """INSERT INTO shops(owner_id,name,address,phone,open_time,close_time,status)
               VALUES (?,?,?,?, '00:00','24:00','APPROVED')""",
            (owner["id"], SHOP_NAME, "Quán dùng thử trên máy local", "0900000000"),
        )
        shop = c.execute("SELECT * FROM shops WHERE id=?", (cur.lastrowid,)).fetchone()
    elif shop["status"] != "APPROVED":
        raise SeedError("Quán hiện có chưa ở trạng thái APPROVED. Hãy duyệt quán trước khi thử đặt món.")

    tables = []
    for number in ("1", "2"):
        row = c.execute(
            "SELECT * FROM shop_tables WHERE shop_id=? AND table_number=?", (shop["id"], number),
        ).fetchone()
        if row is None:
            cur = c.execute(
                "INSERT INTO shop_tables(shop_id,table_number,qr_token) VALUES (?,?,?)",
                (shop["id"], number, secrets.token_urlsafe(24)),
            )
            row = c.execute("SELECT * FROM shop_tables WHERE id=?", (cur.lastrowid,)).fetchone()
        tables.append(dict(row))

    dishes = []
    added = 0
    for category, name, price in MENU:
        c.execute("INSERT OR IGNORE INTO categories(shop_id,name) VALUES (?,?)", (shop["id"], category))
        category_id = c.execute(
            "SELECT id FROM categories WHERE shop_id=? AND name=?", (shop["id"], category),
        ).fetchone()[0]
        row = c.execute(
            "SELECT * FROM dishes WHERE shop_id=? AND name=? COLLATE NOCASE ORDER BY id LIMIT 1",
            (shop["id"], name),
        ).fetchone()
        if row is None:
            cur = c.execute(
                "INSERT INTO dishes(shop_id,category_id,name,price) VALUES (?,?,?,?)",
                (shop["id"], category_id, name, price),
            )
            row = c.execute("SELECT * FROM dishes WHERE id=?", (cur.lastrowid,)).fetchone()
            added += 1
        dishes.append(dict(row))
    return dict(owner=dict(owner), customer=dict(customer), shop=dict(shop), tables=tables,
                dishes=dishes, owner_created=owner_created, customer_created=customer_created,
                shop_created=shop_created, added=added)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-dir", type=Path, help="Folder repo hoặc QuickOrder nếu terminal đang ở chỗ khác")
    parser.add_argument("--owner-email", help="Dùng chủ quán/quán đã có, giữ nguyên cấu hình ngân hàng và token")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        if os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID"):
            raise SeedError("Script này chỉ dành cho dữ liệu local; không chạy trong dịch vụ Render.")
        app_dir = find_app_dir(args.project_dir)
        os.chdir(app_dir)
        # Giống app.py: QO_DB của terminal được ưu tiên, mặc định là QuickOrder/database.db.
        db_path = Path(os.environ.get("QO_DB") or app_dir / "database.db").expanduser().resolve()
        print("Folder ứng dụng:", app_dir)
        print("CSDL sẽ dùng:", db_path)
        backup = backup_database(db_path)
        if backup:
            print("Bản sao lưu trước khi thêm dữ liệu:", backup)
        sys.path.insert(0, str(app_dir))
        from werkzeug.security import check_password_hash, generate_password_hash
        import app as qo
        if Path(qo.DB).expanduser().resolve() != db_path:
            raise SeedError("Đường dẫn CSDL không khớp app.py. Chưa thêm dữ liệu thử.")
        with qo.db() as c:
            data = seed(c, generate_password_hash(PASSWORD),
                        owner_email=args.owner_email.strip().lower() if args.owner_email else OWNER_EMAIL,
                        existing_owner=bool(args.owner_email))
        print("\nĐÃ SẴN SÀNG THỬ ĐẶT MÓN")
        print("Quán:", data["shop"]["name"], "| ID:", data["shop"]["id"])
        print("Quán mới tạo:" if data["shop_created"] else "Dùng lại quán hiện có:", data["shop"]["status"])
        print("Số món vừa thêm:", data["added"], "| Chạy lại không tạo thêm món trùng tên.")
        for title, key in (("Chủ quán", "owner"), ("Khách hàng", "customer")):
            user = data[key]
            password = PASSWORD if check_password_hash(user["password_hash"], PASSWORD) else "dùng mật khẩu hiện tại của tài khoản"
            print(f"{title}: {user['email']} | Mật khẩu: {password}")
        print("\nMenu:")
        for dish in data["dishes"]:
            state = "" if dish["is_available"] and not dish["is_deleted"] else " [đang ẩn/hết món; giữ nguyên thiết lập cũ]"
            print(" -", dish["name"], ":", f"{dish['price']:,}".replace(",", ".") + "đ" + state)
        print("\nChạy server tại folder QuickOrder: python app.py")
        base = "http://127.0.0.1:5000"
        print("Đăng nhập chủ quán:", base + "/merchant/login.html")
        print("Ngân hàng và token xAPI:", base + "/merchant/shop.html#bank-section")
        print("Đơn quán nhận:", base + "/merchant/orders.html")
        print("Đăng nhập khách:", base + "/customer/account.html")
        for table in data["tables"]:
            query = urlencode({"id": data["shop"]["id"], "table": table["qr_token"]})
            print("Menu bàn " + table["table_number"] + ":", base + "/customer/restaurant.html?" + query)
        print("Giỏ hàng (mở cùng tab menu):", base + "/customer/cart.html")
        print("\nQuán mới chưa có ngân hàng: thử tiền mặt ngay, hoặc lưu ngân hàng/token thật để thử QR.")
        print("Dùng hai cửa sổ trình duyệt riêng cho chủ quán và khách để giữ phiên đăng nhập riêng.")
        print("Không gọi xAPI/gửi email, không thay token hoặc tự đánh dấu thanh toán.")
        return 0
    except SeedError as error:
        print("DỪNG:", error)
        return 1
    except ModuleNotFoundError as error:
        print("Thiếu thư viện:", error.name)
        print("Kích hoạt .venv rồi chạy: python -m pip install -r requirements.txt")
        return 1
    except (OSError, sqlite3.Error) as error:
        print("Không thêm được dữ liệu (" + type(error).__name__ + "). Hãy dừng server và kiểm tra quyền/đường dẫn CSDL.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
