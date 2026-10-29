"""FR-55: chủ quán xem, phản hồi và đóng khiếu nại thuộc quán mình."""
from flask import abort, jsonify, request


def register_complaint_routes(app, *, db, login_required, json_body, out):
    def owned_complaint(c, cid, uid):
        row = c.execute(
            "SELECT m.* FROM complaints m JOIN shops s ON s.id = m.shop_id "
            "JOIN orders o ON o.id = m.order_id AND o.shop_id = m.shop_id "
            "WHERE m.id = ? AND s.owner_id = ?", (cid, uid),
        ).fetchone()
        if not row:
            abort(404)
        return row

    @app.get("/api/merchant/complaints")
    def merchant_complaints():
        u = login_required("owner")
        try:
            limit = int(request.args.get("limit", 20))
            offset = int(request.args.get("offset", 0))
            shop_id = int(request.args["shop_id"]) if request.args.get("shop_id") else None
        except ValueError:
            abort(400)
        status = request.args.get("status", "")
        if not 1 <= limit <= 100 or offset < 0 or status not in ("", "OPEN", "REPLIED", "CLOSED"):
            abort(400)
        where, args = " WHERE s.owner_id = ?", [u["id"]]
        if shop_id is not None:
            where += " AND m.shop_id = ?"
            args.append(shop_id)
        if status:
            where += " AND m.status = ?"
            args.append(status)
        joins = (" FROM complaints m JOIN shops s ON s.id = m.shop_id "
                 "JOIN orders o ON o.id = m.order_id AND o.shop_id = m.shop_id")
        with db() as c:
            if shop_id is not None and not c.execute(
                "SELECT 1 FROM shops WHERE id = ? AND owner_id = ?", (shop_id, u["id"]),
            ).fetchone():
                abort(403)
            total = c.execute("SELECT COUNT(*)" + joins + where, args).fetchone()[0]
            rows = c.execute(
                "SELECT m.*, s.name AS shop_name, o.customer_name" + joins + where
                + " ORDER BY m.id DESC LIMIT ? OFFSET ?", [*args, limit, offset],
            ).fetchall()
        return jsonify(items=[out(r) for r in rows], total=total, limit=limit, offset=offset)

    @app.put("/api/merchant/complaints/<int:cid>/reply")
    def merchant_complaint_reply(cid):
        u = login_required("owner")
        reply = json_body().get("owner_reply")
        if not isinstance(reply, str) or not 1 <= len(reply.strip()) <= 2000:
            return jsonify(error="Phản hồi phải có từ 1 đến 2000 ký tự."), 400
        with db() as c:
            c.execute("BEGIN IMMEDIATE")
            row = owned_complaint(c, cid, u["id"])
            if row["status"] == "CLOSED":
                return jsonify(error="Khiếu nại đã đóng, không thể sửa phản hồi."), 409
            c.execute(
                "UPDATE complaints SET owner_reply = ?, status = 'REPLIED', "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?", (reply.strip(), cid),
            )
            return jsonify(out(owned_complaint(c, cid, u["id"])))

    @app.put("/api/merchant/complaints/<int:cid>/close")
    def merchant_complaint_close(cid):
        u = login_required("owner")
        json_body()
        with db() as c:
            c.execute("BEGIN IMMEDIATE")
            row = owned_complaint(c, cid, u["id"])
            if row["status"] == "OPEN" or not row["owner_reply"].strip():
                return jsonify(error="Cần lưu phản hồi trước khi đóng khiếu nại."), 409
            c.execute(
                "UPDATE complaints SET status = 'CLOSED', updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ? AND status = 'REPLIED'", (cid,),
            )
            return jsonify(out(owned_complaint(c, cid, u["id"])))
