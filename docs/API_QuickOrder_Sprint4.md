# Hợp đồng API QuickOrder, đợt Sprint 4

Người soạn: Nguyễn Xuân Anh (BA). Cùng chốt: Nguyễn Tú Anh (Backend).
Căn cứ: SRS v1.1 (Phụ lục A, B, C) và `QuickOrder/app.py` ở commit `d36fc67` trên `main`.
Tài liệu này mô tả **đúng những gì code đang làm**. Phần SRS yêu cầu mà code chưa làm được ghi ở mục 7.

Chỉ mô tả đơn hàng, thanh toán và thống kê. Tài khoản, quán, menu, bàn dùng API chung `/api/<name>` như trước.

## 1. Quy ước chung

- Đường dẫn bắt đầu bằng `/api`. Dữ liệu gửi và nhận là JSON UTF-8, yêu cầu có thân phải gửi `Content-Type: application/json`.
- Lỗi trả về `{"error": "<thông báo tiếng Việt>"}` kèm mã HTTP: 400 dữ liệu sai; 401 chưa đăng nhập; 403 sai quyền; 404 không thấy (cũng dùng khi không được xem đơn, để không lộ đơn của người khác); 409 xung đột trạng thái.
- Thời gian trong CSDL là UTC (`created_at`). Mọi thống kê theo ngày tính theo giờ Việt Nam (UTC+7).
- Khách **không cần đăng nhập** để đặt món. Khi gửi đơn, máy chủ cấp `access_token` (chỉ trả về một lần, máy chủ chỉ giữ bản băm). Trình duyệt lưu token này để xem và hủy đơn. Khách đã đăng nhập thì đơn còn gắn vào tài khoản (`user_id`) và xuất hiện trong Lịch sử.
- Chủ quán chỉ thao tác trên đơn của quán mình; admin được phép như chủ quán.

## 2. Trạng thái đơn

| SRS | Giá trị API | Ghi chú |
|---|---|---|
| Chờ xác nhận | `PENDING` | Đơn mới tạo |
| Đang làm | `PREPARING` | Chủ quán đã xác nhận |
| Hoàn thành | `COMPLETED` | Trạng thái cuối |
| Đã hủy | `CANCELLED` | Trạng thái cuối |
| (dữ liệu cũ) | `CONFIRMED` | Chỉ còn ở đơn cũ, hiển thị là Đang làm, vẫn xử lý tiếp được. Đơn mới không chuyển sang trạng thái này |

Luồng chuyển hợp lệ (`NEXT_STATUS`, BR-05):

| Từ | Sang | Ai làm |
|---|---|---|
| `PENDING` | `PREPARING` | Chủ quán |
| `PENDING` | `CANCELLED` | Khách (`/cancel`) hoặc chủ quán (`/status`, bắt buộc có `reason`) |
| `PREPARING` | `COMPLETED` | Chủ quán |
| `PREPARING` | `CANCELLED` | Chủ quán, bắt buộc có `reason` |
| `CONFIRMED` (cũ) | `PREPARING`, `COMPLETED`, `CANCELLED` | Chủ quán |

Mọi chuyển khác trả 409. Trạng thái thanh toán (`UNPAID`, `PAID`) độc lập với trạng thái đơn (BR-08).

## 3. Đối tượng đơn

Các trường chính: `id`, `shop_id`, `table_id`, `table_number` (khi xem một đơn), `customer_name`, `status`, `payment_method` (`CASH` hoặc `TRANSFER`), `payment_status`, `total_amount`, `discount_amount`, `coupon_code`, `note`, `cancel_reason`, `created_at`, `reviewed`, `items[]`.

Mỗi phần tử `items`: `dish_id`, `dish_name`, `quantity`, `unit_price`, `note`, `option_ids`.

- `unit_price` = giá món + tổng giá cộng thêm của các tùy chọn đã chọn, chốt tại lúc gửi đơn (BR-04).
- `note` của dòng món ghép tên các tùy chọn đã chọn với ghi chú của khách, ví dụ `Lớn, Trân châu; ít đá`.
- `total_amount` = tổng `quantity × unit_price` trừ `discount_amount` (BR-13).
- Không bao giờ trả về `access_hash` và `user_id`.

## 4. Đơn hàng

### 4.1. `POST /api/orders/quote` — Tính thử tổng tiền (FR-23)

Thân: `{"shop_id", "items": [...], "coupon_code": ""}`. Trả `{subtotal, discount, total, coupon_code}`. Không ghi gì vào CSDL.

### 4.2. `POST /api/orders` — Gửi đơn (FR-17, khách)

Không cần đăng nhập.

```json
{
  "shop_id": 1,
  "table_id": 3,
  "customer_name": "An",
  "payment_method": "CASH",
  "note": "",
  "coupon_code": "",
  "items": [{"dish_id": 7, "quantity": 2, "option_ids": [11, 14], "note": "ít đá"}]
}
```

Kiểm tra theo thứ tự (lỗi đầu tiên được trả về):

| Điều kiện | Kết quả |
|---|---|
| `shop_id`, `table_id` thiếu hoặc không phải số | 400 |
| `items` rỗng hoặc quá 50 dòng | 400 |
| `payment_method` không phải `CASH` hoặc `TRANSFER` | 400 |
| Tên khách quá 100 ký tự, ghi chú quá 500 ký tự | 400 |
| Quán không tồn tại hoặc chưa `APPROVED` (kể cả bị khóa, từ chối) | 404 “Quán không tồn tại hoặc chưa được duyệt.” |
| Ngoài giờ mở cửa (giờ Việt Nam, kể cả quán mở qua nửa đêm) | 409 “Quán hiện không nhận đơn (ngoài giờ mở cửa).” |
| Bàn không thuộc quán | 400 |
| Món không có, đã xóa, hoặc hết hàng | 400 “Món <mã món> không tồn tại hoặc đã hết món.” |
| Số lượng ngoài 1 đến 50, tùy chọn sai món, thiếu nhóm bắt buộc, chọn hai tùy chọn trong nhóm chọn một | 400 |
| Mã giảm giá sai, hết hạn, hết lượt, chưa đủ đơn tối thiểu | 400 kèm lý do |

Thành công: 201 và đối tượng đơn, thêm `access_token` và `in_my_history`. Toàn bộ ghi đơn, chi tiết đơn và lượt dùng mã nằm trong một giao dịch; lỗi giữa chừng thì không ghi gì (NFR-30).

### 4.3. `GET /api/orders/<id>?token=<access_token>` — Xem một đơn (FR-19, FR-41)

Được xem nếu là: khách đăng nhập sở hữu đơn, hoặc người có `token` đúng, hoặc chủ quán của quán có đơn, hoặc admin. Còn lại 404. Trả đơn kèm `table_number`, `shop_name`, `can_save_to_history`.

### 4.4. `GET /api/orders` — Danh sách đơn của chủ quán (FR-39, FR-40)

Cần đăng nhập chủ quán hoặc admin. Chủ quán chỉ thấy đơn của quán mình dù truyền `shop_id` nào.

| Tham số | Ý nghĩa |
|---|---|
| `status` | `PENDING`, `PREPARING`, `COMPLETED`, `CANCELLED` (và `CONFIRMED` cho dữ liệu cũ); khác thì 400 |
| `shop_id` | Lọc một quán |
| `from`, `to` | `YYYY-MM-DD`, theo ngày Việt Nam, gồm cả hai đầu |
| `limit` | 1 đến 200, mặc định 50 |
| `before` | Mã đơn; chỉ lấy đơn cũ hơn (phân trang) |

Sắp xếp mới nhất trước. Giao diện chủ quán làm mới danh sách mỗi 7 giây (NFR-03).

### 4.5. `PUT /api/orders/<id>/status` — Đổi trạng thái (FR-42, FR-43, chủ quán)

Thân: `{"status": "PREPARING"}` hoặc `{"status": "CANCELLED", "reason": "Hết nguyên liệu"}`.

| Điều kiện | Kết quả |
|---|---|
| Trạng thái không có trong danh sách (ví dụ “Đang giao”) | 400 |
| Chủ quán của quán khác | 403 |
| Hủy mà thiếu `reason`; `reason` quá 200 ký tự | 400 |
| Đơn đã `COMPLETED` hoặc `CANCELLED` | 409 “Không thể sửa đơn đã kết thúc.” |
| Chuyển không có trong bảng ở mục 2 (nhảy bước, ngược, sang `CONFIRMED`) | 409 “Không thể chuyển đơn sang trạng thái này.” |
| Đơn vừa bị người khác đổi | 409 “Đơn vừa được cập nhật, hãy tải lại.” |

Không chặn theo giờ đóng cửa. Hủy đơn trả lại lượt dùng mã giảm giá.

### 4.6. `PUT /api/orders/<id>/cancel` — Khách hủy đơn (FR-20)

Thân: `{"token": "<access_token>"}`. Sai hoặc thiếu token: 404. Đơn không còn `PENDING`: 409 “Chỉ có thể hủy đơn đang chờ xác nhận.” Thành công: `CANCELLED`, `cancel_reason` là “Khách hủy đơn”.

### 4.7. `PUT /api/orders/<id>/payment` — Đánh dấu thanh toán (FR-44, chủ quán)

Thân: `{"payment_status": "PAID"}` hoặc `"UNPAID"` (cho phép sửa nhầm). Quán khác: 403. Giá trị khác: 400. Đơn `CANCELLED`: 409 “Đơn đã hủy, không ghi nhận thanh toán.” Không làm đổi `status`. Đơn `COMPLETED` vẫn đánh dấu được.

## 5. Đơn của khách đã đăng nhập (FR-21, FR-22)

| Điểm cuối | Ý nghĩa |
|---|---|
| `GET /api/my/orders` | Lịch sử đơn của tài khoản, mới nhất trước. Tham số `status`, `limit` (1 đến 100), `before`. Trả `{orders, next_before}` |
| `GET /api/my/orders/<id>` | Chi tiết một đơn của mình; đơn người khác 404 |
| `POST /api/my/orders/<id>/claim` | Lưu đơn ẩn danh vào tài khoản bằng `{"token"}`; không chuyển được đơn giữa hai tài khoản |
| `POST /api/my/orders/<id>/reorder` | Dựng lại giỏ từ đơn cũ theo giá hiện tại; món hết hoặc đổi tùy chọn nằm trong `skipped` kèm lý do |

## 6. Thống kê (FR-47, FR-48)

`GET /api/revenue?shop_id=<id>&range=today|7d|30d|month` (hoặc `from` và `to`; `group=day|month`). Chủ quán của quán đó hoặc admin; quán khác 403. Khoảng tối đa 366 ngày.

Trả về:

- `summary`: `orders`, `completed`, `cancelled`, `revenue`, `average` (doanh thu chia số đơn hoàn thành, 0 nếu không có).
- `series`: từng ngày (hoặc tháng) trong khoảng, kể cả kỳ không có đơn.
- `now`: số đơn đang `pending` và `working` hiện tại, không phụ thuộc khoảng ngày.
- `dishes`: tối đa 20 món bán chạy.

Doanh thu và món bán chạy chỉ tính đơn `COMPLETED` (BR-17), tính theo `created_at` đổi sang ngày Việt Nam. Món đã xóa mềm vẫn xuất hiện trong các đơn cũ (BR-12).

## 7. Chỗ còn lệch giữa SRS và code

| # | SRS yêu cầu | Code đang làm | Đề xuất |
|---|---|---|---|
| 1 | BR-14: số lượng mỗi món từ 1 đến 99 | `MAX_QTY = 50` | Chọn một con số và sửa nơi còn lại. Tiêu chí AC-17-12 chỉ thử 0 và 100 nên đạt với cả hai |
| 2 | NFR-31: khóa nút và **kiểm tra trùng ở máy chủ** | Chỉ khóa nút ở giao diện (`sending`); máy chủ không chống trùng | Thêm `client_request_id` duy nhất cho mỗi lần gửi, hoặc sửa NFR-31 chỉ còn yêu cầu khóa nút |
| 3 | BR-07: mã cũ vô hiệu khi đổi mã | Quét mã cũ không mở được menu (404). Nhưng `POST /api/orders` nhận `table_id` chứ không kiểm `qr_token`, nên trang đã mở trước khi đổi mã vẫn đặt được | Nhận thêm `qr_token` khi đặt nếu muốn chặt hơn |
| 4 | BR-06: báo “Quán tạm ngưng nhận món” | Giao diện hiện “Quán hiện không nhận đơn” | Thống nhất một câu |
| 5 | Ngoại lệ FR-17: báo tên món vừa hết | Thông báo ghi mã món | Đổi thông báo sang tên món |

Đã sửa trong đợt này (commit `d36fc67`): `PENDING` không còn chuyển được sang `CONFIRMED`.
