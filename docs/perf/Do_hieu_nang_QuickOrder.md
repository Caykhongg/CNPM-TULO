# Báo cáo đo hiệu năng QuickOrder (Sprint 4)

Mục tiêu theo yêu cầu phi chức năng: thời gian tải dưới 3 giây, và xử lý được nhiều bàn gọi món cùng lúc mà không phát sinh lỗi.

## Cách đo

- Script: [`measure_performance.py`](measure_performance.py), chỉ dùng thư viện chuẩn Python. Mỗi "khách" là một client riêng có cookie riêng; thời gian đo từ lúc gửi yêu cầu đến khi nhận xong phản hồi.
- Dữ liệu: `python seed_data.py --reset` (4 quán đã duyệt, 154 đơn mẫu). Mỗi mức tải đo trên CSDL nạp lại từ đầu.
- Máy chủ: `gunicorn app:app --workers 1 --threads 8` (một tiến trình, như hướng dẫn triển khai trong README), Flask 3.1.3, Python 3.13, SQLite.
- Máy đo: Linux 2 CPU, chạy script và máy chủ **cùng một máy**, kết nối localhost.
- Quán thử: Cà Phê Góc Phố (8 bàn). Kịch bản gửi đơn đặt thật, kèm `qr_token` và `client_request_id`.
- Kiểm tra mất đơn: so số đơn gửi thành công với số đơn mới trong CSDL (đếm hết các trang của API).

Chạy lại:

```bash
cd QuickOrder
python seed_data.py --reset
SECRET_KEY=perf MAIL_CONSOLE=1 gunicorn app:app --workers 1 --threads 8 --bind 127.0.0.1:5000
python ../docs/perf/measure_performance.py --base http://127.0.0.1:5000 --tables 8 --repeat 30 --out ../docs/perf/ket_qua_8ban.json
```

Quán phải đang trong giờ mở cửa (giờ Việt Nam) thì kịch bản gửi đơn mới tạo được đơn. Chỉ chạy trên CSDL mẫu.

## Kết quả mức 1: 8 bàn cùng lúc

Mỗi trang hoặc API đọc đơn lẻ lặp 30 lần; mở menu đầy đủ do 8 khách cùng lúc, mỗi khách 10 lần (mỗi lần 4 lời gọi API, như trang menu thật); 40 đơn từ 8 bàn.

| Kịch bản | Số yêu cầu | Lỗi | p50 (ms) | p95 (ms) | Lớn nhất (ms) | Yêu cầu/giây |
|---|---:|---:|---:|---:|---:|---:|
| Trang chủ | 30 | 0 | 1.1 | 1.7 | 2.6 | 826.0 |
| Trang menu quán (HTML) | 30 | 0 | 1.1 | 1.3 | 1.4 | 886.2 |
| Tra mã QR bàn | 30 | 0 | 1.7 | 2.3 | 2.4 | 576.4 |
| Danh sách món của quán | 30 | 0 | 1.7 | 2.3 | 3.3 | 548.9 |
| Gợi ý món | 30 | 0 | 1.5 | 2.1 | 2.1 | 618.8 |
| Danh mục | 30 | 0 | 1.3 | 1.8 | 1.9 | 699.7 |
| Mở menu đầy đủ, 8 khách cùng lúc (4 lời gọi mỗi lần) | 80 | 0 | 56.2 | 78.7 | 105.5 | 114.2 |
| Gửi đơn, 8 bàn cùng lúc (40 đơn) | 40 | 0 | 24.8 | 63.3 | 141.5 | 152.9 |
| Chủ quán: danh sách đơn | 30 | 0 | 3.4 | 4.0 | 4.0 | 273.1 |
| Chủ quán: doanh thu 30 ngày | 30 | 0 | 2.3 | 2.6 | 2.7 | 419.2 |
| Chủ quán: đánh giá | 30 | 0 | 2.2 | 2.9 | 3.3 | 425.0 |

- Kiểm tra mất đơn: gửi thành công 40, ghi nhận 40, khớp: **có**.
- Yêu cầu chậm nhất: **141.5 ms**.

## Kết quả mức 2: 24 bàn cùng lúc (gấp 3)

| Kịch bản | Số yêu cầu | Lỗi | p50 (ms) | p95 (ms) | Lớn nhất (ms) | Yêu cầu/giây |
|---|---:|---:|---:|---:|---:|---:|
| Trang chủ | 10 | 0 | 1.2 | 2.7 | 2.7 | 747.7 |
| Trang menu quán (HTML) | 10 | 0 | 1.2 | 1.4 | 1.4 | 806.5 |
| Tra mã QR bàn | 10 | 0 | 1.4 | 1.9 | 1.9 | 696.3 |
| Danh sách món của quán | 10 | 0 | 1.3 | 2.3 | 2.3 | 694.9 |
| Gợi ý món | 10 | 0 | 1.2 | 1.5 | 1.5 | 761.5 |
| Danh mục | 10 | 0 | 1.5 | 2.0 | 2.0 | 647.9 |
| Mở menu đầy đủ, 24 khách cùng lúc (4 lời gọi mỗi lần) | 240 | 0 | 173.9 | 226.8 | 303.8 | 121.6 |
| Gửi đơn, 24 bàn cùng lúc (120 đơn) | 120 | 0 | 80.5 | 242.9 | 412.1 | 131.6 |
| Chủ quán: danh sách đơn | 10 | 0 | 3.3 | 4.7 | 4.7 | 250.7 |
| Chủ quán: doanh thu 30 ngày | 10 | 0 | 2.6 | 3.2 | 3.2 | 355.1 |
| Chủ quán: đánh giá | 10 | 0 | 2.4 | 2.6 | 2.6 | 405.4 |

- Kiểm tra mất đơn: gửi thành công 120, ghi nhận 120, khớp: **có**.
- Yêu cầu chậm nhất: **412.1 ms**.

## Nhận xét

- Không có yêu cầu nào lỗi ở cả hai mức tải, và không mất đơn nào khi nhiều bàn gửi cùng lúc.
- Thời gian xử lý ở máy chủ rất thấp: trang và API đơn lẻ vài mili giây; yêu cầu chậm nhất ở mức 24 bàn là 412.1 ms, thấp hơn nhiều so với ngưỡng 3 giây.
- Khi tăng tải gấp 3, thời gian chờ tăng gần tuyến tính (mở menu đầy đủ p95 từ 78.7 ms lên 226.8 ms) vì chỉ có một tiến trình, tám luồng xử lý và SQLite ghi tuần tự. Với quán nhỏ vài chục bàn, mức này dư dùng.
- Các API của chủ quán (danh sách đơn, doanh thu, đánh giá) dưới 5 ms với ~150 đơn. Danh sách đơn giới hạn 50 dòng mỗi lần (tối đa 200) nên thời gian trả về có giới hạn trên.

## Giới hạn của phép đo (cần nói rõ khi báo cáo)

- Đo ở **phía máy chủ qua localhost**: chưa gồm độ trễ mạng 4G/Wi-Fi của khách, thời gian dựng trang trên điện thoại, hay tải phông chữ Google và thư viện từ CDN. Thời gian tải thực tế trên điện thoại phụ thuộc nhiều vào các yếu tố này; cần đo thêm trên bản đã deploy (Lighthouse hoặc công cụ dev của trình duyệt) khi có link demo.
- Máy chủ và máy đo dùng chung CPU nên số liệu bất lợi hơn chút so với máy riêng.
- Dữ liệu mẫu nhỏ (150 đơn). Chưa thử hàng chục nghìn đơn.
- Chưa đo gunicorn nhiều tiến trình (README hướng dẫn một tiến trình vì bộ đếm đăng nhập sai nằm trong bộ nhớ).
