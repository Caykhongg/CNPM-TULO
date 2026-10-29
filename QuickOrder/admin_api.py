"""API dành cho quản trị viên."""

from flask import abort, jsonify, request


def register_admin_routes(
    app, *, db, login_required, json_body, out
):
    def page_args():
        try:
            limit = int(request.args.get("limit", 20))
            offset = int(request.args.get("offset", 0))
        except (TypeError, ValueError):
            abort(400)

        if not 1 <= limit <= 100 or offset < 0:
            abort(400)

        return limit, offset

    def search_text():
        q = request.args.get("q", "").strip()

        if len(q) > 100:
            abort(400)

        # Tìm ký tự %, _ theo nghĩa thông thường,
        # không coi chúng là ký tự đại diện của SQL.
        q = (
            q.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        return "%" + q + "%"

    # FR-52: xem, tìm kiếm và lọc người dùng.
    @app.get("/api/admin/users")
    def admin_users():
        login_required("admin")

        limit, offset = page_args()
        pattern = search_text()

        where = [
            "(full_name LIKE ? ESCAPE '\\' "
            "OR email LIKE ? ESCAPE '\\' "
            "OR phone LIKE ? ESCAPE '\\')"
        ]
        args = [pattern] * 3

        role = request.args.get("role")
        active = request.args.get("is_active")

        if role:
            if role not in ("customer", "owner", "admin"):
                abort(400)

            where.append("role = ?")
            args.append(role)

        if active is not None and active != "":
            if active not in ("0", "1"):
                abort(400)

            where.append("is_active = ?")
            args.append(int(active))

        clause = " AND ".join(where)

        with db() as c:
            total = c.execute(
                f"SELECT COUNT(*) FROM users WHERE {clause}",
                args,
            ).fetchone()[0]

            rows = c.execute(
                f"SELECT * FROM users WHERE {clause} "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()

        # out() loại bỏ password_hash trước khi trả dữ liệu.
        return jsonify(
            items=[out(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    # FR-52: khóa hoặc mở khóa tài khoản.
    @app.put("/api/admin/users/<int:uid>/status")
    def admin_user_status(uid):
        admin = login_required("admin")
        data = json_body()

        if (
            set(data) != {"is_active"}
            or type(data["is_active"]) not in (bool, int)
            or data["is_active"] not in (0, 1)
        ):
            return jsonify(
                error="Chỉ gửi is_active là true hoặc false."
            ), 400

        if uid == admin["id"] and not data["is_active"]:
            return jsonify(
                error="Không thể tự khóa tài khoản đang đăng nhập."
            ), 409

        with db() as c:
            exists = c.execute(
                "SELECT 1 FROM users WHERE id = ?",
                (uid,),
            ).fetchone()

            if not exists:
                abort(404)

            c.execute(
                "UPDATE users SET is_active = ? WHERE id = ?",
                (int(data["is_active"]), uid),
            )

            row = c.execute(
                "SELECT * FROM users WHERE id = ?",
                (uid,),
            ).fetchone()

        return jsonify(out(row))

        # FR-54: thống kê toàn hệ thống, toàn bộ thời gian.
    @app.get("/api/admin/statistics")
    def admin_statistics():
        login_required("admin")

        with db() as c:
            shops = c.execute(
                "SELECT COUNT(*) FROM shops"
            ).fetchone()[0]

            users = c.execute(
                "SELECT COUNT(*) FROM users"
            ).fetchone()[0]

            orders = c.execute(
                "SELECT COUNT(*) FROM orders"
            ).fetchone()[0]

            revenue = c.execute(
                "SELECT COALESCE(SUM(total_amount), 0) "
                "FROM orders WHERE status = 'COMPLETED'"
            ).fetchone()[0]

        return jsonify(
            shops=shops,
            users=users,
            orders=orders,
            revenue=revenue,
        )
