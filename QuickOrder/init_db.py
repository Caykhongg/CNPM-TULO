import os
import sqlite3
import sys

from werkzeug.security import generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "database.db")

if "--reset" in sys.argv and os.path.exists(DB):
    os.remove(DB)                      # xóa toàn bộ dữ liệu cũ

conn = sqlite3.connect(DB)
with open(os.path.join(BASE, "schema.sql"), "r", encoding="utf-8") as f:
    conn.executescript(f.read())

# Tài khoản admin (người duyệt quán). Chỉ tạo khi có biến môi trường; chạy lại vẫn an toàn:
#   ADMIN_EMAIL=admin@quickorder.vn ADMIN_PASSWORD=mat-khau-manh python init_db.py
email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
pw = os.environ.get("ADMIN_PASSWORD", "")
if email and pw:
    if len(pw) < 8:                    # NFR-10
        conn.close()
        sys.exit("ADMIN_PASSWORD phải có ít nhất 8 ký tự.")
    if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        print("Email này đã có tài khoản, bỏ qua.")
    else:
        conn.execute("INSERT INTO users (full_name, email, password_hash, role) VALUES ('Quản trị', ?, ?, 'admin')",
                     (email, generate_password_hash(pw)))
        print("Đã tạo tài khoản admin:", email)
else:
    print("Chưa tạo admin (cần đặt ADMIN_EMAIL và ADMIN_PASSWORD).")

conn.commit()
conn.close()
print("Tạo database thành công!")
