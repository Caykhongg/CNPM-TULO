import os
import posixpath
import secrets
import sqlite3
import time
from contextlib import contextmanager

from flask import Flask, abort, g, jsonify, request, send_from_directory, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "database.db")
PUBLIC = ("customer/", "merchant/", "admin/", "css/", "js/")   # chỉ phục vụ các thư mục này

app = Flask(__name__, static_folder=None)
# Phiên đăng nhập lưu ở server (cookie đã ký). Đặt SECRET_KEY cố định để không mất phiên khi khởi động lại.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.environ.get("HTTPS") == "1")   # bật khi chạy trên HTTPS

# tên trong API (khớp app.js) -> (bảng SQL, cho phép ghi qua API chung?)
TABLES = {
    "users": ("users", False),            # users chỉ qua /api/register, /api/login, /api/me
    "shops": ("shops", True),
    "tables": ("shop_tables", True),
    "categories": ("categories", True),
    "dishes": ("dishes", True),
    "optionGroups": ("option_groups", True),
    "options": ("options", True),
}
BOOLS = {"is_active", "is_available", "is_deleted", "is_required", "is_multiple"}

# Từ bản ghi tới owner_id của quán chứa nó (để kiểm tra quyền)
OWNER_SQL = {
    "shops": "SELECT owner_id FROM shops WHERE id = ?",
    "tables": "SELECT s.owner_id FROM shop_tables r JOIN shops s ON s.id = r.shop_id WHERE r.id = ?",
    "dishes": "SELECT s.owner_id FROM dishes r JOIN shops s ON s.id = r.shop_id WHERE r.id = ?",
    "optionGroups": "SELECT s.owner_id FROM option_groups r JOIN dishes d ON d.id = r.dish_id "
                    "JOIN shops s ON s.id = d.shop_id WHERE r.id = ?",
    "options": "SELECT s.owner_id FROM options r JOIN option_groups g ON g.id = r.group_id "
               "JOIN dishes d ON d.id = g.dish_id JOIN shops s ON s.id = d.shop_id WHERE r.id = ?",
}
# Bảng cha và cột khóa ngoại: khi tạo hoặc chuyển bản ghi, cha phải thuộc quán của người gọi
PARENT = {"tables": ("shops", "shop_id"), "dishes": ("shops", "shop_id"),
          "optionGroups": ("dishes", "dish_id"), "options": ("optionGroups", "group_id")}
# Món, nhóm, tùy chọn: khách chỉ thấy khi quán đã duyệt (BR-06)
ITEMS = ("dishes", "optionGroups", "options")
# Khóa tạm đăng nhập theo email: 5 lần sai thì chặn 15 phút (lưu trong bộ nhớ, khởi động lại thì mất)
LOGIN_FAILS = {}
MAX_FAILS, LOCK_SECONDS = 5, 15 * 60
MSG = {400: "Dữ liệu không hợp lệ.", 401: "Bạn cần đăng nhập.",
       403: "Bạn không có quyền thực hiện thao tác này.", 404: "Không tìm thấy dữ liệu.",
       405: "Thao tác này không được phép.", 415: "Dữ liệu gửi lên phải là JSON."}


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


# ---------- Đầu vào, phiên, quyền ----------
def text(d, k):
    return str(d.get(k) or "").strip()


def json_body():
    if not request.is_json:                    # chặn form từ trang khác gửi dữ liệu kiểu JSON
        abort(415)
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        abort(400)
    return d


def current_user():
    """Người đang đăng nhập theo phiên phía server, hoặc None."""
    if not hasattr(g, "user"):
        g.user = None
        uid = session.get("uid")
        if uid:
            with db() as c:
                row = c.execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (uid,)).fetchone()
            g.user = dict(row) if row else None
    return g.user


def login_required(*roles):
    u = current_user()
    if u is None:
        abort(401)
    if roles and u["role"] not in roles:
        abort(403)
    return u


def owner_via(c, name, rid):
    r = c.execute(OWNER_SQL[name], (rid,)).fetchone()
    return r[0] if r else None


def assert_owns(c, name, rid, u):
    if u["role"] == "admin":
        return
    owner = owner_via(c, name, rid)
    if owner is None:
        abort(404)
    if owner != u["id"]:
        abort(403)


def shop_scope(u):
    """Quán người này được thấy: admin tất cả; chủ quán: quán của mình + quán đã duyệt; khách: quán đã duyệt."""
    if u and u["role"] == "admin":
        return "1 = 1", []
    if u and u["role"] == "owner":
        return "(owner_id = ? OR status = 'APPROVED')", [u["id"]]
    return "status = 'APPROVED'", []


def item_scope(name, u):
    """Món, nhóm và tùy chọn được thấy: chỉ của quán được thấy (xem shop_scope) và món chưa xóa mềm; admin thấy tất cả."""
    if u and u["role"] == "admin":
        return "1 = 1", []
    clause, args = shop_scope(u)
    shops = f"SELECT id FROM shops WHERE {clause}"
    if name == "dishes":
        return f"is_deleted = 0 AND shop_id IN ({shops})", args
    if name == "optionGroups":
        return f"dish_id IN (SELECT id FROM dishes WHERE is_deleted = 0 AND shop_id IN ({shops}))", args
    return (f"group_id IN (SELECT g.id FROM option_groups g JOIN dishes d ON d.id = g.dish_id "
            f"WHERE d.is_deleted = 0 AND d.shop_id IN ({shops}))"), args


def guard_write(c, name, rid, data, u):
    """Chặn ghi trái quyền. Trả về dữ liệu đã bỏ các cột chủ quán không được tự đặt."""
    if u["role"] == "admin":
        return data
    if name == "categories":                   # danh mục dùng chung: chủ quán được thêm/xóa, không được sửa
        if rid is not None:
            abort(403)
        return data
    if name == "shops":
        if rid is None:                        # quán mới luôn thuộc người tạo và chờ admin duyệt
            data.update(owner_id=u["id"], status="PENDING", status_note="")
        else:
            assert_owns(c, name, rid, u)
            for k in ("owner_id", "status", "status_note"):
                data.pop(k, None)              # chỉ admin được đổi trạng thái hoặc chủ quán
            cur = c.execute("SELECT status FROM shops WHERE id = ?", (rid,)).fetchone()
            if cur and cur["status"] == "REJECTED":
                data.update(status="PENDING", status_note="")   # quán bị từ chối: sửa rồi lưu là gửi lại (UC-36)
        return data
    if rid is not None:
        assert_owns(c, name, rid, u)
    parent, fk = PARENT[name]
    if rid is None and fk not in data:
        abort(400)
    if fk in data and owner_via(c, parent, data[fk]) != u["id"]:
        abort(403)                             # không được gắn vào quán/món/nhóm của người khác
    return data


def check_values(name, data):
    """Giá trị nhập hợp lệ: giá món phải lớn hơn 0 (UC-24, FR-34). Trả về phản hồi lỗi hoặc None."""
    if name == "dishes" and "price" in data:
        try:
            ok = int(data["price"]) > 0
        except (TypeError, ValueError):
            ok = False
        if not ok:
            return jsonify(error="Giá món phải lớn hơn 0."), 400
    return None


# ---------- Lỗi -> JSON ----------
@app.errorhandler(sqlite3.IntegrityError)
def on_integrity(e):
    return jsonify(error="Dữ liệu bị trùng hoặc đang được sử dụng."), 409


@app.errorhandler(sqlite3.Error)
def on_sqlite(e):
    return jsonify(error=f"Lỗi CSDL: {e}"), 400


@app.errorhandler(HTTPException)
def on_http(e):
    if request.path.startswith("/api/"):
        return jsonify(error=MSG.get(e.code, e.description)), e.code
    return e.get_response()


# ---------- Đăng ký / đăng nhập / phiên ----------
@app.post("/api/register")
def register():
    d = json_body()
    email = text(d, "email").lower()
    pw = str(d.get("password") or "")
    if "@" not in email or len(pw) < 8:              # NFR-10: mật khẩu tối thiểu 8 ký tự
        return jsonify(error="Email không hợp lệ hoặc mật khẩu dưới 8 ký tự."), 400
    with db() as c:
        cur = c.execute(
            "INSERT INTO users(full_name, email, phone, password_hash, role) VALUES (?,?,?,?,'owner')",
            (text(d, "full_name"), email, text(d, "phone"), generate_password_hash(pw)),
        )
        row = c.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    session.clear()
    session["uid"] = row["id"]
    return jsonify(out(row)), 201


@app.post("/api/login")
def login():
    d = json_body()
    email = text(d, "email").lower()
    pw = str(d.get("password") or "")
    now = time.time()
    fails, since = LOGIN_FAILS.get(email, (0, now))
    if now - since >= LOCK_SECONDS:                 # hết thời gian khóa thì đếm lại từ đầu
        fails, since = 0, now
    if fails >= MAX_FAILS:
        return jsonify(error="Bạn đã nhập sai quá nhiều lần. Thử lại sau 15 phút."), 429
    with db() as c:
        row = c.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], pw):
        LOGIN_FAILS[email] = (fails + 1, since)
        return jsonify(error="Email hoặc mật khẩu không đúng."), 401
    if not row["is_active"]:
        return jsonify(error="Tài khoản đã bị khóa."), 403
    LOGIN_FAILS.pop(email, None)
    session.clear()
    session["uid"] = row["id"]
    return jsonify(out(row))


@app.post("/api/logout")
def logout():
    session.clear()
    return "", 204


@app.get("/api/me")
def whoami():
    return jsonify(out(login_required()))


# ---------- CRUD chung ----------
@app.get("/api/<name>")
def list_rows(name):
    t, _ = table(name)
    if name == "users":
        abort(405)                             # không liệt kê người dùng
    where, args = [], []
    if name == "shops":
        clause, a = shop_scope(current_user())
        where.append(clause)
        args += a
    elif name in ITEMS:
        clause, a = item_scope(name, current_user())
        where.append(clause)
        args += a
    elif name == "tables" and "qr_token" not in request.args:
        u = login_required("owner", "admin")   # danh sách bàn chỉ cho chủ quán / admin; khách tra theo qr_token
        if u["role"] == "owner":
            where.append("shop_id IN (SELECT id FROM shops WHERE owner_id = ?)")
            args.append(u["id"])
    with db() as c:
        cols = columns(c, t)
        for k, v in request.args.items():      # ?shop_id=3  -> lọc theo cột
            if k not in cols or k == "password_hash":
                abort(400)
            where.append(f"{k} = ?")
            args.append(v)
        sql = f"SELECT * FROM {t}" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id"
        return jsonify([out(r) for r in c.execute(sql, args)])


@app.get("/api/<name>/<int:id>")
def get_row(name, id):
    t, _ = table(name)
    if name == "users":
        abort(405)                             # không đọc chi tiết người dùng (email, sđt, vai trò)
    u = login_required("owner", "admin") if name == "tables" else None
    with db() as c:
        if name == "shops":
            clause, a = shop_scope(current_user())
            row = c.execute(f"SELECT * FROM shops WHERE id = ? AND {clause}", [id, *a]).fetchone()
        elif name in ITEMS:
            clause, a = item_scope(name, current_user())
            row = c.execute(f"SELECT * FROM {t} WHERE id = ? AND {clause}", [id, *a]).fetchone()
        else:
            if u is not None:
                assert_owns(c, name, id, u)
            row = c.execute(f"SELECT * FROM {t} WHERE id = ?", (id,)).fetchone()
    if not row:
        abort(404)
    return jsonify(out(row))


@app.post("/api/<name>")
def create_row(name):
    t, writable = table(name)
    if not writable:
        abort(405)
    u = login_required("owner", "admin")
    data = json_body()
    with db() as c:
        data = guard_write(c, name, None, data, u)
        err = check_values(name, data)
        if err:
            return err
        if name == "tables":
            data["qr_token"] = secrets.token_urlsafe(16)   # mã do máy chủ sinh, không nhận từ trình duyệt (NFR-16)
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
    u = login_required("owner", "admin")
    data = json_body()
    with db() as c:
        data = guard_write(c, name, id, data, u)
        err = check_values(name, data)
        if err:
            return err
        if name == "tables":
            if data.pop("regenerate", False):              # tạo lại mã: mã cũ vô hiệu ngay (BR-07)
                data["qr_token"] = secrets.token_urlsafe(16)
            else:
                data.pop("qr_token", None)
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
    u = login_required("owner", "admin")
    with db() as c:
        if name == "shops":
            if u["role"] != "admin":
                abort(403)                     # xóa quán chỉ admin
        elif name != "categories":             # danh mục: chủ quán được xóa, RESTRICT chặn nếu đang dùng
            assert_owns(c, name, id, u)
        c.execute(f"DELETE FROM {t} WHERE id=?", (id,))
    return "", 204


@app.get("/api/qr/<token>")
def qr_lookup(token):
    """Khách quét mã QR: trả bàn và quán (kèm trạng thái) để trang menu kiểm tra trước khi cho gọi món (UC-05)."""
    with db() as c:
        row = c.execute(
            "SELECT r.id AS table_id, r.table_number, s.id, s.name, s.address, s.phone, "
            "s.open_time, s.close_time, s.status "
            "FROM shop_tables r JOIN shops s ON s.id = r.shop_id WHERE r.qr_token = ?", (token,)).fetchone()
    if not row:
        abort(404)
    return jsonify(table={"id": row["table_id"], "table_number": row["table_number"]},
                   shop={k: row[k] for k in ("id", "name", "address", "phone", "open_time", "close_time", "status")})


# ---------- Trang tĩnh ----------
@app.get("/")
@app.get("/index.html")          # logo và các link "về trang chủ" trỏ tới index.html
def index():
    return send_from_directory(BASE, "index.html")


@app.get("/<path:p>")
def static_files(p):
    p = posixpath.normpath(p)                  # chặn css/../app.py
    if not p.startswith(PUBLIC) or ".." in p.split("/"):
        abort(404)
    return send_from_directory(BASE, p)


init_db()

if __name__ == "__main__":
    if not os.environ.get("SECRET_KEY"):
        print("Lưu ý: chưa đặt SECRET_KEY; phiên đăng nhập sẽ mất khi khởi động lại server.")
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")   # không bật debug khi chạy thật (NFR-33)
