import hashlib
import hmac
import os
import posixpath
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

from flask import Flask, abort, g, jsonify, request, send_from_directory, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

import mailer

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("QO_DB") or os.path.join(BASE, "database.db")   # QO_DB: dùng khi chạy kiểm thử
VN = timezone(timedelta(hours=7))              # quán chỉ phục vụ ở Việt Nam: giờ mở cửa và "hôm nay" tính theo UTC+7
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
# Xác nhận email khi khách đăng ký tài khoản
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PHONE_RE = re.compile(r"\+?\d{9,11}")
CODE_TTL = 10 * 60          # mã có hiệu lực 10 phút
CODE_MAX_TRIES = 5          # nhập sai 5 lần thì phải xin mã mới
RESEND_WAIT = 60            # hai lần gửi mã cách nhau tối thiểu 60 giây
MAX_SENDS_PER_HOUR = 5      # mỗi email tối đa 5 lần gửi mã trong 1 giờ
SENT_MSG = "Nếu email chưa có tài khoản, mã xác nhận 6 số đã được gửi tới email này. Mã có hiệu lực 10 phút."
BAD_CODE = "Mã xác nhận không đúng hoặc đã hết hạn."
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
        # CSDL cũ: bảng orders tạo trước khi có mã đơn và lý do hủy thì bổ sung cột (CREATE IF NOT EXISTS không làm việc này)
        have = {r["name"] for r in c.execute("PRAGMA table_info(orders)")}
        for col in ("access_hash", "cancel_reason"):
            if col not in have:
                c.execute(f"ALTER TABLE orders ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")


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


def profile_fields(d):
    """Họ tên và số điện thoại của khách. Trả về (dict, None) nếu hợp lệ, hoặc (None, thông báo lỗi)."""
    name = text(d, "full_name")
    phone = re.sub(r"[\s.-]", "", text(d, "phone"))
    if not name or len(name) > 100:
        return None, "Vui lòng nhập họ tên (tối đa 100 ký tự)."
    if not PHONE_RE.fullmatch(phone):
        return None, "Số điện thoại không hợp lệ (9 đến 11 chữ số)."
    return {"full_name": name, "phone": phone}, None


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
    return jsonify(error="Lỗi cơ sở dữ liệu."), 400   # không trả chi tiết lỗi ra ngoài


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


@app.put("/api/me")
def update_me():
    """Khách (hoặc chủ quán) sửa họ tên và số điện thoại của chính mình. Không đổi được email hay vai trò."""
    u = login_required()
    fields, err = profile_fields(json_body())
    if err:
        return jsonify(error=err), 400
    with db() as c:
        c.execute("UPDATE users SET full_name = ?, phone = ? WHERE id = ?",
                  (fields["full_name"], fields["phone"], u["id"]))
        row = c.execute("SELECT * FROM users WHERE id = ?", (u["id"],)).fetchone()
    return jsonify(out(row))


# ---------- Tài khoản khách: đăng ký có xác nhận email ----------
def start_code(c, email, base, now):
    """Tạo mã 6 số mới cho email, lưu hash vào pending_signups. Trả về (mã, None) hoặc (None, lỗi).
    base: họ tên, số điện thoại, hash mật khẩu. Kiểm tra thời gian chờ và số lần gửi trong 1 giờ."""
    old = c.execute("SELECT * FROM pending_signups WHERE email = ?", (email,)).fetchone()
    if old and now - old["last_sent_at"] < RESEND_WAIT:
        wait = RESEND_WAIT - (now - old["last_sent_at"])
        return None, f"Vui lòng đợi {wait} giây rồi gửi lại."
    in_hour = bool(old) and now - old["window_start"] < 3600
    window_start = old["window_start"] if in_hour else now
    sent = old["sent_in_window"] if in_hour else 0
    if sent >= MAX_SENDS_PER_HOUR:
        return None, "Đã gửi quá nhiều mã cho email này. Thử lại sau 1 giờ."
    code = f"{secrets.randbelow(10 ** 6):06d}"
    c.execute(
        "INSERT OR REPLACE INTO pending_signups (email, full_name, phone, password_hash, code_hash, "
        "expires_at, tries, last_sent_at, window_start, sent_in_window) VALUES (?,?,?,?,?,?,0,?,?,?)",
        (email, base["full_name"], base["phone"], base["password_hash"], generate_password_hash(code),
         now + CODE_TTL, now, window_start, sent + 1),
    )
    return code, None


def send_code_or_error(email, code):
    """Gửi mã qua email. Trả về phản hồi lỗi nếu gửi thất bại, hoặc None nếu thành công."""
    try:
        mailer.send_code(email, code)
    except mailer.MailError as e:
        return jsonify(error=str(e)), 502
    return None


@app.post("/api/customer/signup")
def customer_signup():
    d = json_body()
    email = text(d, "email").lower()
    pw = str(d.get("password") or "")
    fields, err = profile_fields(d)
    if err:
        return jsonify(error=err), 400
    if not EMAIL_RE.fullmatch(email) or len(pw) < 8:          # NFR-10: mật khẩu tối thiểu 8 ký tự
        return jsonify(error="Email không hợp lệ hoặc mật khẩu dưới 8 ký tự."), 400
    now = int(time.time())
    with db() as c:
        c.execute("DELETE FROM pending_signups WHERE expires_at < ?", (now - 3600,))   # dọn đăng ký đã bỏ dở
        if c.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            return jsonify(message=SENT_MSG), 200      # không tiết lộ email đã có tài khoản hay chưa
        base = {**fields, "password_hash": generate_password_hash(pw)}
        code, err = start_code(c, email, base, now)
        if err:
            return jsonify(error=err), 429
    failed = send_code_or_error(email, code)
    if failed:
        return failed
    return jsonify(message=SENT_MSG)


@app.post("/api/customer/resend")
def customer_resend():
    email = text(json_body(), "email").lower()
    now = int(time.time())
    with db() as c:
        p = c.execute("SELECT * FROM pending_signups WHERE email = ?", (email,)).fetchone()
        if not p:
            return jsonify(message=SENT_MSG), 200
        base = {"full_name": p["full_name"], "phone": p["phone"], "password_hash": p["password_hash"]}
        code, err = start_code(c, email, base, now)
        if err:
            return jsonify(error=err), 429
    failed = send_code_or_error(email, code)
    if failed:
        return failed
    return jsonify(message=SENT_MSG)


@app.post("/api/customer/verify")
def customer_verify():
    d = json_body()
    email = text(d, "email").lower()
    code = re.sub(r"\s", "", str(d.get("code") or ""))
    if not re.fullmatch(r"\d{6}", code):
        return jsonify(error=BAD_CODE), 400
    now = int(time.time())
    with db() as c:
        p = c.execute("SELECT * FROM pending_signups WHERE email = ?", (email,)).fetchone()
        if not p:
            return jsonify(error=BAD_CODE), 400
        if now > p["expires_at"]:
            c.execute("DELETE FROM pending_signups WHERE email = ?", (email,))
            return jsonify(error="Mã đã hết hạn. Bấm gửi lại mã để nhận mã mới."), 400
        if p["tries"] >= CODE_MAX_TRIES:
            return jsonify(error="Nhập sai quá nhiều lần. Bấm gửi lại mã để nhận mã mới."), 429
        if not check_password_hash(p["code_hash"], code):
            c.execute("UPDATE pending_signups SET tries = tries + 1 WHERE email = ?", (email,))
            return jsonify(error=BAD_CODE), 400
        if c.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            c.execute("DELETE FROM pending_signups WHERE email = ?", (email,))
            return jsonify(error="Email này đã có tài khoản. Hãy đăng nhập."), 409
        cur = c.execute(
            "INSERT INTO users (full_name, email, phone, password_hash, role) VALUES (?,?,?,?,'customer')",
            (p["full_name"], email, p["phone"], p["password_hash"]),
        )
        c.execute("DELETE FROM pending_signups WHERE email = ?", (email,))
        row = c.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    session.clear()
    session["uid"] = row["id"]
    return jsonify(out(row)), 201


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


# ---------- Đơn hàng ----------
ORDER_STATUSES = ("PENDING", "CONFIRMED", "PREPARING", "COMPLETED", "CANCELLED")
# Chủ quán chỉ được chuyển tiến theo luồng: chờ xác nhận -> đang làm -> hoàn thành; hủy được cho tới khi hoàn thành.
# CONFIRMED chỉ còn ở dữ liệu cũ nhưng vẫn được xử lý tiếp.
NEXT_STATUS = {
    "PENDING": ("CONFIRMED", "PREPARING", "CANCELLED"),
    "CONFIRMED": ("PREPARING", "COMPLETED", "CANCELLED"),
    "PREPARING": ("COMPLETED", "CANCELLED"),
}
MAX_QTY = 50                # tối đa mỗi dòng món
MAX_LINES = 50              # tối đa số dòng món trong một đơn
MAX_NOTE = 500
MAX_ITEM_NOTE = 200
MAX_REASON = 200
CUSTOMER_CANCEL_REASON = "Khách hủy đơn"


def token_hash(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def token_ok(order, token):
    """Mã riêng của đơn (khách giữ trên thiết bị) khớp với băm đã lưu. So sánh theo thời gian không đổi."""
    return bool(token) and bool(order["access_hash"]) and hmac.compare_digest(order["access_hash"], token_hash(token))


def minutes_of(t):
    """'HH:MM' -> số phút từ 0 giờ. '24:00' nghĩa là hết ngày. Sai định dạng -> None."""
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(t or ""))
    return int(m[1]) * 60 + int(m[2]) if m else None


def is_open_now(shop, now=None):
    """Quán đang trong giờ mở cửa (theo giờ Việt Nam, có thể qua nửa đêm). Chưa đặt giờ thì không chặn."""
    o, c = minutes_of(shop["open_time"]), minutes_of(shop["close_time"])
    if o is None or c is None:
        return True
    now = now or datetime.now(VN)
    n = now.hour * 60 + now.minute
    return o <= n < c if o <= c else (n >= o or n < c)


def items_of(c, ids):
    """Món của nhiều đơn bằng một truy vấn: {id đơn: [món...]}."""
    by = {i: [] for i in ids}
    if ids:
        marks = ",".join("?" * len(ids))
        rows = c.execute(
            f"SELECT oi.*, d.name AS dish_name FROM order_items oi JOIN dishes d ON d.id = oi.dish_id "
            f"WHERE oi.order_id IN ({marks}) ORDER BY oi.id", list(ids))
        for r in rows:
            by[r["order_id"]].append(out(r))
    return by


def order_view(row, items):
    """Đơn gửi ra ngoài: không bao giờ kèm băm mã riêng."""
    o = out(row)
    o.pop("access_hash", None)
    o["items"] = items
    return o


def order_json(c, order_id):
    row = c.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        abort(404)
    return order_view(row, items_of(c, [order_id])[order_id])


def owns_order(c, order, u):
    """Admin, hoặc chủ của quán có đơn này."""
    if u is None:
        return False
    if u["role"] == "admin":
        return True
    return c.execute("SELECT 1 FROM shops WHERE id = ? AND owner_id = ?", (order["shop_id"], u["id"])).fetchone() is not None


def as_int(v):
    """Số nguyên từ JSON. Từ chối True/False, số thực và chuỗi không phải số."""
    if isinstance(v, bool):
        raise ValueError
    if isinstance(v, int):
        return v
    if isinstance(v, str) and re.fullmatch(r"\d{1,9}", v.strip()):
        return int(v)
    raise ValueError


def price_item(c, shop_id, item):
    """Kiểm tra một dòng món và tính giá. Trả về ((dish_id, số lượng, đơn giá, ghi chú), None) hoặc (None, lỗi).
    Đơn giá gồm giá món cộng giá thêm của các tùy chọn đã chọn; tên tùy chọn được ghi vào ghi chú của dòng."""
    if not isinstance(item, dict):
        return None, "Món trong đơn không hợp lệ."
    try:
        dish_id, qty = as_int(item.get("dish_id")), as_int(item.get("quantity"))
    except ValueError:
        return None, "Món trong đơn không hợp lệ."
    if not 1 <= qty <= MAX_QTY:
        return None, f"Số lượng mỗi món phải từ 1 đến {MAX_QTY}."
    raw = item.get("option_ids") or []
    if not isinstance(raw, list):
        return None, "Tùy chọn không hợp lệ."
    try:
        picked = list(dict.fromkeys(as_int(x) for x in raw))      # bỏ trùng, giữ thứ tự
    except ValueError:
        return None, "Tùy chọn không hợp lệ."
    note = str(item.get("note") or "").strip()
    if len(note) > MAX_ITEM_NOTE:
        return None, f"Ghi chú món tối đa {MAX_ITEM_NOTE} ký tự."

    dish = c.execute(
        "SELECT id, name, price FROM dishes WHERE id = ? AND shop_id = ? AND is_deleted = 0 AND is_available = 1",
        (dish_id, shop_id)).fetchone()
    if not dish:
        return None, f"Món {dish_id} không tồn tại hoặc đã hết món."
    groups = c.execute("SELECT id, name, is_required, is_multiple FROM option_groups WHERE dish_id = ? ORDER BY id",
                       (dish_id,)).fetchall()
    options = {r["id"]: r for r in c.execute(
        "SELECT o.id, o.name, o.extra_price, o.group_id FROM options o JOIN option_groups g ON g.id = o.group_id "
        "WHERE g.dish_id = ? ORDER BY o.id", (dish_id,))}
    if any(i not in options for i in picked):
        return None, f"Tùy chọn không thuộc món {dish['name']}."
    chosen = sorted((options[i] for i in picked), key=lambda o: (o["group_id"], o["id"]))
    for g in groups:
        n = sum(1 for o in chosen if o["group_id"] == g["id"])
        if g["is_required"] and n == 0:
            return None, f'Món {dish["name"]}: vui lòng chọn nhóm "{g["name"]}".'
        if not g["is_multiple"] and n > 1:
            return None, f'Món {dish["name"]}: nhóm "{g["name"]}" chỉ được chọn một.'
    unit = int(dish["price"]) + sum(int(o["extra_price"]) for o in chosen)
    full_note = "; ".join(p for p in (", ".join(o["name"] for o in chosen), note) if p)
    return (dish_id, qty, unit, full_note), None


@app.post("/api/orders")
def create_order():
    d = json_body()
    try:
        shop_id = as_int(d.get("shop_id"))
    except ValueError:
        return jsonify(error="shop_id không hợp lệ."), 400
    if d.get("table_id") is None:
        return jsonify(error="Hãy quét mã QR trên bàn để đặt món."), 400
    try:
        table_id = as_int(d.get("table_id"))
    except ValueError:
        return jsonify(error="table_id không hợp lệ."), 400
    items = d.get("items")
    if not isinstance(items, list) or not items:
        return jsonify(error="Đơn hàng phải có ít nhất một món."), 400
    if len(items) > MAX_LINES:
        return jsonify(error=f"Một đơn tối đa {MAX_LINES} món."), 400
    payment_method = str(d.get("payment_method") or "CASH").upper()
    if payment_method not in ("CASH", "TRANSFER"):
        return jsonify(error="payment_method phải là CASH hoặc TRANSFER."), 400
    customer = text(d, "customer_name") or "Khách tại bàn"
    note = text(d, "note")
    if len(customer) > 100 or len(note) > MAX_NOTE:
        return jsonify(error="Họ tên hoặc ghi chú quá dài."), 400

    with db() as c:
        shop = c.execute("SELECT id, open_time, close_time FROM shops WHERE id = ? AND status = 'APPROVED'",
                         (shop_id,)).fetchone()
        if not shop:
            return jsonify(error="Quán không tồn tại hoặc chưa được duyệt."), 404
        if not is_open_now(shop):
            return jsonify(error="Quán hiện không nhận đơn (ngoài giờ mở cửa)."), 409
        if not c.execute("SELECT 1 FROM shop_tables WHERE id = ? AND shop_id = ?", (table_id, shop_id)).fetchone():
            return jsonify(error="Bàn không thuộc quán này."), 400

        lines, total = [], 0
        for item in items:
            line, err = price_item(c, shop_id, item)
            if err:
                return jsonify(error=err), 400
            lines.append(line)
            total += line[1] * line[2]

        token = secrets.token_urlsafe(24)              # chỉ trả về một lần; server chỉ giữ băm
        order_id = c.execute(
            "INSERT INTO orders (shop_id, table_id, customer_name, payment_method, total_amount, note, access_hash) "
            "VALUES (?,?,?,?,?,?,?)",
            (shop_id, table_id, customer, payment_method, total, note, token_hash(token))).lastrowid
        c.executemany(
            "INSERT INTO order_items (order_id, dish_id, quantity, unit_price, note) VALUES (?,?,?,?,?)",
            [(order_id, dish_id, qty, unit, line_note) for dish_id, qty, unit, line_note in lines])
        result = order_json(c, order_id)
    result["access_token"] = token
    return jsonify(result), 201


@app.get("/api/orders/<int:id>")
def get_order(id):
    """Chủ quán (hoặc admin) xem đơn của quán mình; khách xem bằng mã riêng của đơn (?token=). Còn lại: 404."""
    token = request.args.get("token", "")
    with db() as c:
        row = c.execute("SELECT * FROM orders WHERE id = ?", (id,)).fetchone()
        if not row or not (owns_order(c, row, current_user()) or token_ok(row, token)):
            abort(404)                         # không phân biệt "không có" và "không được xem"
        return jsonify(order_view(row, items_of(c, [id])[id]))


@app.get("/api/orders")
def list_orders():
    u = login_required("owner", "admin")
    status = request.args.get("status")
    if status and status not in ORDER_STATUSES:
        return jsonify(error="Trạng thái đơn không hợp lệ."), 400
    try:
        limit = int(request.args.get("limit", 50))
        before = int(request.args["before"]) if request.args.get("before") else None
        shop_id = int(request.args["shop_id"]) if request.args.get("shop_id") else None
    except ValueError:
        return jsonify(error="Tham số không hợp lệ."), 400
    if not 1 <= limit <= 200:
        return jsonify(error="limit phải từ 1 đến 200."), 400
    where, args = [], []
    if u["role"] == "owner":
        where.append("o.shop_id IN (SELECT id FROM shops WHERE owner_id = ?)")
        args.append(u["id"])
    if shop_id is not None:
        where.append("o.shop_id = ?")
        args.append(shop_id)
    if status:
        where.append("o.status = ?")
        args.append(status)
    if before is not None:                     # trang kế tiếp: đơn cũ hơn id này
        where.append("o.id < ?")
        args.append(before)
    sql = ("SELECT o.* FROM orders o" + (" WHERE " + " AND ".join(where) if where else "")
           + " ORDER BY o.id DESC LIMIT ?")
    with db() as c:
        rows = c.execute(sql, args + [limit]).fetchall()
        items = items_of(c, [r["id"] for r in rows])
        return jsonify([order_view(r, items[r["id"]]) for r in rows])


@app.put("/api/orders/<int:id>/status")
def update_order_status(id):
    u = login_required("owner", "admin")
    d = json_body()
    status = str(d.get("status") or "").upper()
    if status not in ORDER_STATUSES:
        return jsonify(error="Trạng thái đơn không hợp lệ."), 400
    reason = text(d, "reason")
    with db() as c:
        order = c.execute("SELECT * FROM orders WHERE id = ?", (id,)).fetchone()
        if not order:
            abort(404)
        if not owns_order(c, order, u):
            abort(403)
        if status == "CANCELLED" and not reason:
            return jsonify(error="Vui lòng nhập lý do hủy đơn."), 400
        if len(reason) > MAX_REASON:
            return jsonify(error=f"Lý do tối đa {MAX_REASON} ký tự."), 400
        if order["status"] in ("COMPLETED", "CANCELLED"):
            return jsonify(error="Không thể sửa đơn đã kết thúc."), 409
        if status not in NEXT_STATUS.get(order["status"], ()):
            return jsonify(error="Không thể chuyển đơn sang trạng thái này."), 409
        done = c.execute("UPDATE orders SET status = ?, cancel_reason = ? WHERE id = ? AND status = ?",
                         (status, reason if status == "CANCELLED" else order["cancel_reason"], id, order["status"]))
        if done.rowcount == 0:                 # đơn vừa bị đổi bởi người khác
            return jsonify(error="Đơn vừa được cập nhật, hãy tải lại."), 409
        return jsonify(order_json(c, id))


@app.put("/api/orders/<int:id>/cancel")
def cancel_order(id):
    """Khách hủy đơn của mình bằng mã riêng của đơn, chỉ khi quán chưa xác nhận."""
    d = json_body()
    with db() as c:
        order = c.execute("SELECT * FROM orders WHERE id = ?", (id,)).fetchone()
        if not order or not token_ok(order, str(d.get("token") or "")):
            abort(404)
        done = c.execute("UPDATE orders SET status = 'CANCELLED', cancel_reason = ? WHERE id = ? AND status = 'PENDING'",
                         (CUSTOMER_CANCEL_REASON, id))
        if done.rowcount == 0:
            return jsonify(error="Chỉ có thể hủy đơn đang chờ xác nhận."), 409
        return jsonify(order_json(c, id))


@app.put("/api/orders/<int:id>/payment")
def update_order_payment(id):
    """Chủ quán ghi nhận đã thu tiền (hoặc hoàn tác). Đơn đã hủy thì không ghi nhận thanh toán."""
    u = login_required("owner", "admin")
    d = json_body()
    with db() as c:
        order = c.execute("SELECT * FROM orders WHERE id = ?", (id,)).fetchone()
        if not order:
            abort(404)
        if not owns_order(c, order, u):
            abort(403)
        paid = str(d.get("payment_status") or "").upper()
        if paid not in ("PAID", "UNPAID"):
            return jsonify(error="payment_status phải là PAID hoặc UNPAID."), 400
        if order["status"] == "CANCELLED":
            return jsonify(error="Đơn đã hủy, không ghi nhận thanh toán."), 409
        c.execute("UPDATE orders SET payment_status = ? WHERE id = ?", (paid, id))
        return jsonify(order_json(c, id))


# ---------- Doanh thu (FR-47, FR-48) ----------
MAX_REVENUE_DAYS = 366
UTC_FMT = "%Y-%m-%d %H:%M:%S"


def parse_day(s):
    """'YYYY-MM-DD' -> date, hoặc None nếu sai."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s or ""):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def revenue_period(a):
    """Khoảng ngày (theo giờ Việt Nam) từ tham số: range=today|7d|30d|month, hoặc from và to. Trả về (từ, đến, lỗi)."""
    frm, to = a.get("from"), a.get("to")
    if frm or to:
        d1, d2 = parse_day(frm), parse_day(to)
        if not d1 or not d2:
            return None, None, "Cần nhập đủ ngày bắt đầu và kết thúc hợp lệ (YYYY-MM-DD)."
        if d1 > d2:
            return None, None, "Ngày bắt đầu phải trước ngày kết thúc."
    else:
        today = datetime.now(VN).date()
        days = {"today": 0, "7d": 6, "30d": 29}
        rng = a.get("range") or "today"
        if rng == "month":
            d1, d2 = today.replace(day=1), today
        elif rng in days:
            d1, d2 = today - timedelta(days=days[rng]), today
        else:
            return None, None, "range phải là today, 7d, 30d hoặc month."
    if (d2 - d1).days + 1 > MAX_REVENUE_DAYS:
        return None, None, f"Khoảng thời gian tối đa {MAX_REVENUE_DAYS} ngày."
    return d1, d2, None


def utc_bounds(d1, d2):
    """Ngày VN [d1, d2] -> khoảng giờ UTC [lo, hi) theo định dạng của cột created_at (UTC)."""
    start = datetime.combine(d1, datetime.min.time()) - timedelta(hours=7)
    end = datetime.combine(d2 + timedelta(days=1), datetime.min.time()) - timedelta(hours=7)
    return start.strftime(UTC_FMT), end.strftime(UTC_FMT)


def period_keys(d1, d2, group):
    """Mọi kỳ trong khoảng, kể cả kỳ không có đơn, để biểu đồ liền mạch."""
    if group == "month":
        keys, y, m = [], d1.year, d1.month
        while (y, m) <= (d2.year, d2.month):
            keys.append(f"{y:04d}-{m:02d}")
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return keys
    return [(d1 + timedelta(days=i)).isoformat() for i in range((d2 - d1).days + 1)]


@app.get("/api/revenue")
def revenue():
    """Thống kê của một quán: chỉ đơn hoàn thành mới tính doanh thu. Ngày tính theo giờ Việt Nam."""
    u = login_required("owner", "admin")
    a = request.args
    try:
        shop_id = int(a.get("shop_id", ""))
    except ValueError:
        return jsonify(error="shop_id không hợp lệ."), 400
    group = a.get("group", "day")
    if group not in ("day", "month"):
        return jsonify(error="group phải là day hoặc month."), 400
    d1, d2, err = revenue_period(a)
    if err:
        return jsonify(error=err), 400
    lo, hi = utc_bounds(d1, d2)
    key = "strftime('%Y-%m-%d', created_at, '+7 hours')" if group == "day" else "strftime('%Y-%m', created_at, '+7 hours')"
    with db() as c:
        shop = c.execute("SELECT owner_id FROM shops WHERE id = ?", (shop_id,)).fetchone()
        if not shop:
            abort(404)
        if u["role"] != "admin" and shop["owner_id"] != u["id"]:
            abort(403)
        rows = c.execute(
            f"SELECT {key} AS k, COUNT(*) AS orders, "
            "COALESCE(SUM(status = 'COMPLETED'), 0) AS completed, COALESCE(SUM(status = 'CANCELLED'), 0) AS cancelled, "
            "COALESCE(SUM(CASE WHEN status = 'COMPLETED' THEN total_amount END), 0) AS revenue "
            "FROM orders WHERE shop_id = ? AND created_at >= ? AND created_at < ? GROUP BY k",
            (shop_id, lo, hi)).fetchall()
        by_key = {r["k"]: r for r in rows}
        series = []
        for k in period_keys(d1, d2, group):
            r = by_key.get(k)
            series.append({"key": k, "orders": r["orders"] if r else 0, "completed": r["completed"] if r else 0,
                           "cancelled": r["cancelled"] if r else 0, "revenue": r["revenue"] if r else 0})
        completed = sum(p["completed"] for p in series)
        revenue_sum = sum(p["revenue"] for p in series)
        summary = {"orders": sum(p["orders"] for p in series), "completed": completed,
                   "cancelled": sum(p["cancelled"] for p in series), "revenue": revenue_sum,
                   "average": revenue_sum // completed if completed else 0}
        # Số hiện tại, không phụ thuộc khoảng ngày: đơn chờ từ hôm trước vẫn cần xử lý
        pend = c.execute(
            "SELECT COALESCE(SUM(status = 'PENDING'), 0) AS pending, "
            "COALESCE(SUM(status IN ('CONFIRMED', 'PREPARING')), 0) AS working FROM orders WHERE shop_id = ?",
            (shop_id,)).fetchone()
        dishes = c.execute(
            "SELECT d.name AS name, SUM(oi.quantity) AS quantity, SUM(oi.quantity * oi.unit_price) AS revenue "
            "FROM order_items oi JOIN orders o ON o.id = oi.order_id JOIN dishes d ON d.id = oi.dish_id "
            "WHERE o.shop_id = ? AND o.status = 'COMPLETED' AND o.created_at >= ? AND o.created_at < ? "
            "GROUP BY oi.dish_id ORDER BY quantity DESC, revenue DESC, d.name LIMIT 20",
            (shop_id, lo, hi)).fetchall()
    return jsonify(shop_id=shop_id, group=group, **{"from": d1.isoformat(), "to": d2.isoformat()},
                   summary=summary, now={"pending": pend["pending"], "working": pend["working"]},
                   series=series, dishes=[dict(r) for r in dishes])


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
