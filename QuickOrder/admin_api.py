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

        # FR-55: xem danh sách khiếu nại.
    @app.get("/api/admin/complaints")
    def admin_complaints():
        login_required("admin")
        limit, offset = page_args()
        status = request.args.get("status", "")

        if status and status not in ("OPEN", "REPLIED", "CLOSED"):
            abort(400)

        where = " WHERE m.status = ?" if status else ""
        args = [status] if status else []

        with db() as c:
            total = c.execute(
                "SELECT COUNT(*) FROM complaints m" + where,
                args,
            ).fetchone()[0]

            rows = c.execute(
                "SELECT m.*, s.name AS shop_name, o.customer_name "
                "FROM complaints m "
                "JOIN shops s ON s.id = m.shop_id "
                "JOIN orders o ON o.id = m.order_id"
                + where
                + " ORDER BY m.id DESC LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()

        return jsonify(
            items=[out(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    # FR-55: phản hồi, chuyển trạng thái sang REPLIED.
    @app.put("/api/admin/complaints/<int:cid>/reply")
    def admin_complaint_reply(cid):
        login_required("admin")
        reply = json_body().get("admin_reply")

        if not isinstance(reply, str) or not 1 <= len(reply.strip()) <= 2000:
            return jsonify(
                error="Phản hồi phải có từ 1 đến 2000 ký tự."
            ), 400

        with db() as c:
            c.execute("BEGIN IMMEDIATE")

            row = c.execute(
                "SELECT * FROM complaints WHERE id = ?",
                (cid,),
            ).fetchone()

            if not row:
                abort(404)

            if row["status"] == "CLOSED":
                return jsonify(
                    error="Khiếu nại đã đóng, không thể sửa phản hồi."
                ), 409

            c.execute(
                "UPDATE complaints "
                "SET admin_reply = ?, status = 'REPLIED', "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (reply.strip(), cid),
            )

            row = c.execute(
                "SELECT * FROM complaints WHERE id = ?",
                (cid,),
            ).fetchone()

        return jsonify(out(row))

    # FR-55: đóng khiếu nại sau khi đã phản hồi.
    @app.put("/api/admin/complaints/<int:cid>/close")
    def admin_complaint_close(cid):
        login_required("admin")

        with db() as c:
            c.execute("BEGIN IMMEDIATE")

            row = c.execute(
                "SELECT * FROM complaints WHERE id = ?",
                (cid,),
            ).fetchone()

            if not row:
                abort(404)

            if row["status"] == "OPEN" or not row["admin_reply"].strip():
                return jsonify(
                    error="Cần lưu phản hồi trước khi đóng khiếu nại."
                ), 409

            c.execute(
                "UPDATE complaints SET status = 'CLOSED', "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ? AND status = 'REPLIED'",
                (cid,),
            )

            row = c.execute(
                "SELECT * FROM complaints WHERE id = ?",
                (cid,),
            ).fetchone()

        return jsonify(out(row))