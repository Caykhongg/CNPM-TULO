import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "database.db")

if "--reset" in sys.argv and os.path.exists(DB):
    os.remove(DB)                      # xóa toàn bộ dữ liệu cũ

conn = sqlite3.connect(DB)
with open(os.path.join(BASE, "schema.sql"), "r", encoding="utf-8") as f:
    conn.executescript(f.read())
conn.commit()
conn.close()
print("Tạo database thành công!")
