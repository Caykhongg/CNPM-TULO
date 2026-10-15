import os
import posixpath
import sqlite3
from contextlib import contextmanager

from flask import Flask, abort, jsonify, request, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "database.db")
PUBLIC = ("customer/", "merchant/", "admin/", "css/", "js/")   # chỉ phục vụ các thư mục này

app = Flask(__name__, static_folder=None)

# tên trong API (khớp app.js) -> (bảng SQL, cho phép ghi qua API chung?)
TABLES = {
    "users": ("users", False),            # users chỉ qua /api/register, /api/login
    "shops": ("shops", True),
    "tables": ("shop_tables", True),
    "categories": ("categories", True),
    "dishes": ("dishes", True),
    "optionGroups": ("option_groups", True),
    "options": ("options", True),
}
BOOLS = {"is_active", "is_available", "is_deleted", "is_required", "is_multiple"}


@contextmanager
def db():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")      # SQLite mặc định TẮT khóa ngoại
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with db() as c, open(os.path.join(BASE, "schema.sql"), encoding="utf-8") as f:
        c.executescript(f.read())


def columns(c, table):
    return [r["name"] for r in c.execute(f"PRAGMA table_info({table})")]


def out(row):
    d = dict(row)
    d.pop("password_hash", None)
    for k in BOOLS & d.keys():
        d[k] = bool(d[k])
    return d


def clean(v):
    return int(v) if isinstance(v, bool) else v


def table(name):
    if name not in TABLES:
        abort(404)
    return TABLES[name]


# ---------- Lỗi -> JSON ----------
@app.errorhandler(sqlite3.IntegrityError)
def on_integrity(e):
    return jsonify(error="Dữ liệu bị trùng hoặc đang được sử dụng."), 409


@app.errorhandler(sqlite3.Error)
def on_sqlite(e):
    return jsonify(error=f"Lỗi CSDL: {e}"), 400


# ---------- Đăng ký / đăng nhập ----------
@app.post("/api/register")
def register():
    d = request.get_json(force=True) or {}
    email = (d.get("email") or "").strip().lower()
    pw = d.get("password") or ""
    if not email or len(pw) < 6:
        return jsonify(error="Email không hợp lệ hoặc mật khẩu dưới 6 ký tự."), 400
    with db() as c:
        cur = c.execute(
            "INSERT INTO users(full_name, email, phone, password_hash, role) VALUES (?,?,?,?,'owner')",
            ((d.get("full_name") or "").strip(), email, (d.get("phone") or "").strip(),
             generate_password_hash(pw)),
        )
        row = c.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(out(row)), 201


@app.post("/api/login")
def login():
    d = request.get_json(force=True) or {}
    with db() as c:
        row = c.execute("SELECT * FROM users WHERE email=?",
                        ((d.get("email") or "").strip().lower(),)).fetchone()
    if not row or not check_password_hash(row["password_hash"], d.get("password") or ""):
        return jsonify(error="Email hoặc mật khẩu không đúng."), 401
    if not row["is_active"]:
        return jsonify(error="Tài khoản đã bị khóa."), 403
    return jsonify(out(row))


# ---------- CRUD chung ----------
@app.get("/api/<name>")
def list_rows(name):
    t, _ = table(name)
    if name == "users":
        abort(405)                                 # không liệt kê người dùng
    with db() as c:
        cols = columns(c, t)
        where, args = [], []
        for k, v in request.args.items():          # ?shop_id=3  -> lọc theo cột
            if k not in cols or k == "password_hash":
                abort(400)
            where.append(f"{k} = ?")
            args.append(v)
        sql = f"SELECT * FROM {t}" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id"
        return jsonify([out(r) for r in c.execute(sql, args)])


@app.get("/api/<name>/<int:id>")
def get_row(name, id):
    t, _ = table(name)
    with db() as c:
        row = c.execute(f"SELECT * FROM {t} WHERE id=?", (id,)).fetchone()
    if not row:
        abort(404)
    return jsonify(out(row))


@app.post("/api/<name>")
def create_row(name):
    t, writable = table(name)
    if not writable:
        abort(405)
    data = request.get_json(force=True) or {}
    with db() as c:
        cols = [k for k in columns(c, t) if k in data and k not in ("id", "created_at")]
        if not cols:
            abort(400)
        cur = c.execute(
            f"INSERT INTO {t} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [clean(data[k]) for k in cols],
        )
        row = c.execute(f"SELECT * FROM {t} WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(out(row)), 201


@app.put("/api/<name>/<int:id>")
def update_row(name, id):
    t, writable = table(name)
    if not writable:
        abort(405)
    data = request.get_json(force=True) or {}
    with db() as c:
        cols = [k for k in columns(c, t) if k in data and k not in ("id", "created_at")]
        if cols:
            c.execute(f"UPDATE {t} SET {','.join(k + '=?' for k in cols)} WHERE id=?",
                      [clean(data[k]) for k in cols] + [id])
        row = c.execute(f"SELECT * FROM {t} WHERE id=?", (id,)).fetchone()
    if not row:
        abort(404)
    return jsonify(out(row))


@app.delete("/api/<name>/<int:id>")
def delete_row(name, id):
    t, writable = table(name)
    if not writable:
        abort(405)
    with db() as c:
        c.execute(f"DELETE FROM {t} WHERE id=?", (id,))
    return "", 204


# ---------- Trang tĩnh ----------
@app.get("/")
def index():
    return send_from_directory(BASE, "index.html")


@app.get("/<path:p>")
def static_files(p):
    p = posixpath.normpath(p)                      # chặn css/../app.py
    if not p.startswith(PUBLIC) or ".." in p.split("/"):
        abort(404)
    return send_from_directory(BASE, p)


init_db()

if __name__ == "__main__":
    app.run(debug=True)
