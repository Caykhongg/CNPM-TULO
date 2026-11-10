"""Tạo các bản mẫu SVG nhập vào Figma. Chạy bằng Python tiêu chuẩn, không gọi mạng."""
from pathlib import Path
from xml.sax.saxutils import escape

INK, BG, GREEN, GOLD, LINE = "#14213d", "#f5f6f2", "#0e7c66", "#f5a524", "#e3e6df"
ROOT = Path(__file__).resolve().parent


def rect(x, y, w, h, fill="white", radius=14, stroke=LINE):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>'


def text(x, y, value, size=14, color=INK, weight=400, anchor="start"):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}">{escape(value)}</text>'


def button(x, y, w, label, fill=GREEN, color="white", key="button"):
    return f'<g id="{key}">' + rect(x, y, w, 36, fill, 10) + text(x + w / 2, y + 23, label, 12, color, 600, "middle") + '</g>'


def badge(x, y, label, status):
    fill, color = ("#fdf0d3", "#946200") if status == "PENDING" else ("#fde8dc", "#c2410c") if status == "CANCELLED" else ("#dff3ee", "#095c4c")
    return rect(x, y, 136, 27, fill, 13, fill) + text(x + 68, y + 18, label, 12, color, 600, "middle")


def header():
    return rect(0, 0, 390, 106, INK, 0, INK) + text(18, 39, "Quick", 24, "white", 800) + text(91, 39, "Order", 24, GOLD, 800) + \
        rect(0, 103, 390, 3, GOLD, 0, GOLD) + button(18, 59, 171, "Người dùng", GOLD, INK, "customer-nav") + button(201, 59, 171, "Chủ quán", "#243360", "white", "merchant-nav")


def save(name, content, height=940):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="390" height="{height}" viewBox="0 0 390 {height}"><title>{escape(name)}</title><g font-family="Be Vietnam Pro, Arial, sans-serif">' + rect(0, 0, 390, height, BG, 0, BG) + content + '</g></svg>\n'
    (ROOT / name).write_text(svg, encoding="utf-8")


def list_frame():
    s = header() + text(18, 151, "Đơn hàng của bạn", 25, weight=800) + text(18, 176, "Trạng thái tự cập nhật mỗi 7 giây.", 12, "#667085")
    for x, y, w, label, on in ((18, 197, 66, "Tất cả", True), (92, 197, 144, "Chờ xác nhận", False), (244, 197, 128, "Đang làm", False), (18, 241, 132, "Hoàn thành", False), (158, 241, 104, "Đã hủy", False)):
        s += button(x, y, w, label, GREEN if on else "white", "white" if on else INK, "filter-" + str(x) + "-" + str(y))
    s += '<g id="pending-order-card">' + rect(18, 295, 354, 286) + text(34, 327, "Đơn #101 · Quán mẫu", 17, weight=700) + text(34, 351, "Bàn 1 · 10:30", 12, "#667085") + badge(34, 366, "Chờ xác nhận", "PENDING")
    s += text(34, 421, "1 × Trà sữa trân châu") + text(34, 447, "1 × Trà đào") + text(34, 477, "Tiền mặt · Chưa thanh toán", 12, "#667085") + text(34, 509, "75.000đ", 21, GREEN, 700)
    s += button(34, 530, 147, "Theo dõi đơn", "white", INK, "track-pending") + button(193, 530, 147, "Hủy đơn", "#fde8dc", "#c2410c", "cancel-pending") + '</g>'
    s += '<g id="preparing-order-card">' + rect(18, 599, 354, 245) + text(34, 632, "Đơn #102 · Quán mẫu", 17, weight=700) + text(34, 656, "Bàn 1 · 10:20", 12, "#667085") + badge(34, 671, "Đang làm", "PREPARING")
    s += text(34, 724, "1 × Phở bò") + text(34, 753, "Tiền mặt · Chưa thanh toán", 12, "#667085") + text(34, 784, "40.000đ", 21, GREEN, 700) + button(208, 787, 132, "Theo dõi đơn", "white", INK, "track-preparing") + '</g>'
    s += text(18, 884, "Dữ liệu minh họa cho thiết kế giao diện.", 11, "#667085")
    save("01-danh-sach-don.svg", s)


def track_frame(status, filename):
    labels = {"PENDING": "Chờ xác nhận", "PREPARING": "Đang làm", "COMPLETED": "Hoàn thành", "CANCELLED": "Đã hủy"}
    descriptions = {"PENDING": "Quán đang chờ xác nhận đơn của bạn.", "PREPARING": "Quán đang chuẩn bị món cho bạn.", "COMPLETED": "Quán đã hoàn thành đơn của bạn.", "CANCELLED": "Đơn đã được hủy."}
    s = header() + text(18, 137, "← Danh sách đơn của bạn", 12, "#667085") + text(18, 174, "Theo dõi đơn #101", 25, weight=800) + text(18, 199, "Tự cập nhật mỗi 7 giây · Tải lại", 12, "#667085")
    s += '<g id="tracking-status">' + rect(18, 218, 354, 301) + text(34, 251, "Quán mẫu", 19, weight=700) + text(34, 277, "Bàn 1 · 10:30", 12, "#667085") + badge(34, 293, labels[status], status) + text(34, 347, descriptions[status], 12)
    if status != "CANCELLED":
        step = ["PENDING", "PREPARING", "COMPLETED"].index(status)
        for i, (x, name) in enumerate(((34, "Chờ xác nhận"), (143, "Đang làm"), (252, "Hoàn thành"))):
            fill = GOLD if i == step else GREEN if i < step else LINE
            s += rect(x, 368, 98, 4, fill, 0, fill) + rect(x, 385, 26, 26, "#fdf0d3" if i == step else "#dff3ee" if i < step else BG, 13)
            s += text(x + 13, 403, str(i + 1), 12, INK, 600, "middle") + text(x, 434, name, 11, INK if i <= step else "#667085", 600)
    else:
        s += text(34, 386, "Lý do hủy: Khách hủy đơn", 13, "#c2410c")
    if status == "PENDING":
        s += button(34, 460, 142, "Hủy đơn", "#fde8dc", "#c2410c", "cancel-order")
    else:
        s += button(34, 460, 168, "Xem / gửi khiếu nại", "white", INK, "complaint-order")
    s += button(214, 460, 126, "Danh sách đơn", "white", INK, "back-orders") + '</g>'
    s += '<g id="tracking-details">' + rect(18, 537, 354, 300) + text(34, 571, "Món đã đặt", 18, weight=700)
    s += text(34, 610, "1 × Trà sữa trân châu", 13, weight=600) + text(340, 610, "40.000đ", 13, GREEN, 600, "end") + text(34, 632, "Size M · Ít đá", 11, "#667085")
    s += rect(34, 649, 306, 1, LINE, 0, LINE) + text(34, 680, "1 × Trà đào", 13, weight=600) + text(340, 680, "35.000đ", 13, GREEN, 600, "end")
    s += rect(34, 705, 306, 1, LINE, 0, LINE) + text(34, 744, "Tổng cộng", 15, weight=700) + text(340, 744, "75.000đ", 22, GREEN, 700, "end")
    s += text(34, 780, "Tiền mặt · Chưa thanh toán", 12, "#667085") + '</g>' + text(18, 877, "Dữ liệu minh họa; trạng thái do quán cập nhật.", 11, "#667085")
    save(filename, s)


if __name__ == "__main__":
    list_frame()
    for state, filename in (("PENDING", "02-theo-doi-cho-xac-nhan.svg"), ("PREPARING", "03-theo-doi-dang-lam.svg"), ("COMPLETED", "04-theo-doi-hoan-thanh.svg"), ("CANCELLED", "05-theo-doi-da-huy.svg")):
        track_frame(state, filename)
    print("Đã tạo 5 bản mẫu SVG trong", ROOT)
