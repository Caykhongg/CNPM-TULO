"""Đo hiệu năng QuickOrder (Sprint 4: NFR thời gian tải dưới 3 giây, nhiều bàn gọi món cùng lúc).

Chỉ dùng thư viện chuẩn của Python. Chạy trên một máy chủ đã bật sẵn và đã nạp dữ liệu mẫu:

    cd QuickOrder
    python seed_data.py --reset
    SECRET_KEY=perf MAIL_CONSOLE=1 gunicorn app:app --workers 1 --threads 8 --bind 127.0.0.1:5000
    python ../docs/perf/measure_performance.py --base http://127.0.0.1:5000 --out ../docs/perf/ket_qua_8ban.json

Lưu ý: script tạo đơn thật (đặt tại các bàn của quán mở cửa). Chỉ chạy trên CSDL mẫu, không chạy trên máy chủ thật.
Quán phải đang trong giờ mở cửa (giờ Việt Nam) thì mới đặt được đơn.
"""
import argparse
import concurrent.futures as cf
import http.cookiejar
import json
import statistics
import time
import urllib.error
import urllib.request

PASSWORD = "Demo@1234"


class Client:
    """Một trình duyệt giả: giữ cookie phiên, đo thời gian từng yêu cầu."""

    def __init__(self, base):
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data else {})
        t0 = time.perf_counter()
        try:
            with self.opener.open(req, timeout=30) as r:
                raw = r.read()
                status = r.status
        except urllib.error.HTTPError as e:
            raw, status = e.read(), e.code
        except Exception:
            return 0, None, time.perf_counter() - t0
        elapsed = time.perf_counter() - t0
        try:
            return status, json.loads(raw), elapsed
        except ValueError:
            return status, raw, elapsed


def pct(values, p):
    s = sorted(values)
    return s[min(len(s) - 1, max(0, int(round(p / 100 * len(s) + 0.5)) - 1))]


def summarize(name, samples, ok_codes, wall):
    times = [t for _, t in samples]
    bad = sum(1 for code, _ in samples if code not in ok_codes)
    return {
        "kịch bản": name,
        "số yêu cầu": len(samples),
        "lỗi": bad,
        "p50 (ms)": round(statistics.median(times) * 1000, 1),
        "p95 (ms)": round(pct(times, 95) * 1000, 1),
        "lớn nhất (ms)": round(max(times) * 1000, 1),
        "yêu cầu/giây": round(len(samples) / wall, 1) if wall else 0,
    }


def count_perf_orders(owner):
    """Đếm đơn do script tạo (tên khách 'Đo hiệu năng'), duyệt hết các trang vì API chỉ trả tối đa 200 đơn mỗi lần."""
    total, before = 0, None
    while True:
        path = "/api/orders?limit=200" + (f"&before={before}" if before else "")
        _, rows, _ = owner.call("GET", path)
        if not rows:
            return total
        total += sum(1 for o in rows if o["customer_name"] == "Đo hiệu năng")
        before = min(o["id"] for o in rows)
        if len(rows) < 200:
            return total


def run_parallel(workers, jobs):
    """jobs: danh sách hàm không tham số trả về (mã, giây). Trả về (mẫu, tổng thời gian)."""
    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        samples = list(pool.map(lambda fn: fn(), jobs))
    return samples, time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5000")
    ap.add_argument("--out", default="")
    ap.add_argument("--repeat", type=int, default=30, help="số lần lặp cho mỗi trang/API đơn lẻ")
    ap.add_argument("--tables", type=int, default=8, help="số bàn gọi món cùng lúc")
    args = ap.parse_args()

    owner = Client(args.base)
    code, _, _ = owner.call("POST", "/api/login", {"email": "owner2@quickorder.vn", "password": PASSWORD})
    assert code == 200, "Không đăng nhập được owner2: đã chạy seed_data.py --reset chưa?"
    _, me, _ = owner.call("GET", "/api/me")
    _, shops, _ = owner.call("GET", f"/api/shops?owner_id={me['id']}")
    shop = next(s for s in shops if s["status"] == "APPROVED")
    _, tables, _ = owner.call("GET", f"/api/tables?shop_id={shop['id']}")
    _, dishes, _ = owner.call("GET", f"/api/dishes?shop_id={shop['id']}")
    dish = next(d for d in dishes if d["is_available"] and not d["is_deleted"])
    _, groups, _ = owner.call("GET", "/api/optionGroups")
    _, options, _ = owner.call("GET", "/api/options")
    chosen = []
    for g in (g for g in groups if g["dish_id"] == dish["id"] and g["is_required"]):
        chosen.append(next(o["id"] for o in options if o["group_id"] == g["id"]))
    token = tables[0]["qr_token"]
    print(f"Quán: {shop['name']} (id {shop['id']}), {len(tables)} bàn, món thử: {dish['name']}")

    results = []
    perf_orders_before = count_perf_orders(owner)

    # 1. Tải trang và API đọc, từng yêu cầu một (khách chưa đăng nhập)
    guest = Client(args.base)
    singles = [
        ("Trang chủ", "GET", "/index.html"),
        ("Trang menu quán (HTML)", "GET", "/customer/restaurant.html"),
        ("Tra mã QR bàn", "GET", f"/api/qr/{token}"),
        ("Danh sách món của quán", "GET", f"/api/dishes?shop_id={shop['id']}"),
        ("Gợi ý món", "GET", f"/api/shops/{shop['id']}/suggestions"),
        ("Danh mục", "GET", "/api/categories"),
    ]
    for name, method, path in singles:
        samples = []
        t0 = time.perf_counter()
        for _ in range(args.repeat):
            c, _, t = guest.call(method, path)
            samples.append((c, t))
        results.append(summarize(name, samples, {200}, time.perf_counter() - t0))

    # 2. Mở menu cùng lúc: 8 khách mỗi người tải menu 10 lần (đủ 3 lời gọi như trang thật)
    def open_menu():
        cl = Client(args.base)
        t_all = time.perf_counter()
        codes = [cl.call("GET", f"/api/qr/{token}")[0], cl.call("GET", f"/api/dishes?shop_id={shop['id']}")[0],
                 cl.call("GET", "/api/optionGroups")[0], cl.call("GET", "/api/options")[0]]
        return (200 if all(c == 200 for c in codes) else max(codes)), time.perf_counter() - t_all

    samples, wall = run_parallel(args.tables, [open_menu for _ in range(args.tables * 10)])
    results.append(summarize(f"Mở menu đầy đủ, {args.tables} khách cùng lúc (4 lời gọi mỗi lần)", samples, {200}, wall))

    # 3. Nhiều bàn gửi đơn cùng lúc
    def place(i):
        def job():
            cl = Client(args.base)
            body = {"shop_id": shop["id"], "table_id": tables[i % len(tables)]["id"],
                    "qr_token": tables[i % len(tables)]["qr_token"],
                    "client_request_id": f"perf{int(time.time() * 1000):013d}{i:05d}",
                    "customer_name": "Đo hiệu năng", "payment_method": "CASH",
                    "items": [{"dish_id": dish["id"], "quantity": 1, "option_ids": chosen}]}
            c, _, t = cl.call("POST", "/api/orders", body)
            return c, t
        return job

    samples, wall = run_parallel(args.tables, [place(i) for i in range(args.tables * 5)])
    results.append(summarize(f"Gửi đơn, {args.tables} bàn cùng lúc ({args.tables * 5} đơn)", samples, {201}, wall))

    # 4. Chủ quán tải danh sách đơn và doanh thu
    for name, path in [("Chủ quán: danh sách đơn", "/api/orders"),
                       ("Chủ quán: doanh thu 30 ngày", f"/api/revenue?shop_id={shop['id']}&range=30d"),
                       ("Chủ quán: đánh giá", "/api/reviews")]:
        samples = []
        t0 = time.perf_counter()
        for _ in range(args.repeat):
            c, _, t = owner.call("GET", path)
            samples.append((c, t))
        results.append(summarize(name, samples, {200}, time.perf_counter() - t0))

    # 5. Kiểm tra không mất đơn: số đơn mới "Đo hiệu năng" trong CSDL = số đơn đã gửi thành công
    made = count_perf_orders(owner) - perf_orders_before
    sent_ok = results[-4]["số yêu cầu"] - results[-4]["lỗi"]
    check = {"đơn gửi thành công": sent_ok, "đơn ghi nhận trong CSDL": made, "khớp": sent_ok == made}

    header = ["kịch bản", "số yêu cầu", "lỗi", "p50 (ms)", "p95 (ms)", "lớn nhất (ms)", "yêu cầu/giây"]
    print()
    print(" | ".join(header))
    for r in results:
        print(" | ".join(str(r[h]) for h in header))
    print()
    print("Kiểm tra mất đơn:", check)
    worst = max(r["lớn nhất (ms)"] for r in results)
    print(f"Yêu cầu chậm nhất: {worst} ms ({'đạt' if worst < 3000 else 'KHÔNG đạt'} mục tiêu dưới 3 giây)")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"kết quả": results, "kiểm tra mất đơn": check, "chậm nhất (ms)": worst}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
