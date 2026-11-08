# Kịch bản demo QuickOrder

Thời lượng khoảng 10 phút. Người trình bày: Nguyễn Xuân Anh. Dùng một laptop cho chủ quán và admin, một điện thoại hoặc cửa sổ ẩn danh cho khách.

## Chuẩn bị (làm trước giờ demo)

1. Trong thư mục `QuickOrder/`: `python seed_data.py --reset`
2. Chạy: `SECRET_KEY=demo MAIL_CONSOLE=1 python app.py`, mở http://127.0.0.1:5000. Nếu demo trên bản đã deploy thì chạy seed trên một CSDL riêng, không dùng CSDL thật.
3. Cửa sổ 1 (chủ quán): đăng nhập `owner1@quickorder.vn` (mật khẩu `Demo@1234`), vào **Bàn & QR**, sao chép đường dẫn của Bàn 1.
4. Cửa sổ 2 (khách): cửa sổ ẩn danh, chưa đăng nhập.
5. Cửa sổ 3 (admin): cửa sổ ẩn danh khác, đăng nhập `admin@quickorder.vn` tại `/admin/shops.html`.

Mã giảm giá có sẵn của mọi quán: `WELCOME10` (giảm 10%, đơn từ 50.000đ) và `GIAM20K` (giảm 20.000đ, đơn từ 100.000đ). Quán "Bún Chả 36" (`owner4`) chưa nhập số tài khoản để thử trường hợp thiếu thông tin chuyển khoản.

## Kịch bản

| # | Thời gian | Vai | Thao tác | Điểm cần nhấn mạnh |
|---|---|---|---|---|
| 1 | 1 phút | Chung | Mở trang chủ, giới thiệu hai lối vào cho khách và chủ quán | Quán nhỏ nhận đơn trực tiếp, không thu hoa hồng |
| 2 | 1 phút | Admin | Ở **Quản lý quán**, duyệt "Phở Gia Truyền Cô Lan", khóa rồi mở khóa một quán | Quán chỉ hiện cho khách sau khi được duyệt |
| 3 | 2 phút | Khách | Dán đường dẫn Bàn 1, xem menu và mục gợi ý món, chọn "Trà sữa trân châu đường đen", Size L, topping, mức đường | Mỗi bàn có mã QR riêng, không cần tài khoản. Tùy chọn bắt buộc được kiểm tra |
| 4 | 2 phút | Khách | Mở Giỏ hàng, nhập `WELCOME10`, chọn thanh toán, bấm Đặt hàng | Tổng tiền gồm phụ thu tùy chọn và giảm giá, tính ở máy chủ |
| 5 | 1 phút | Khách | Mở trang Đơn hàng, xem đơn ở trạng thái Chờ xác nhận. Thử hủy rồi đặt lại một đơn | Khách chỉ hủy được khi đơn còn Chờ xác nhận |
| 6 | 2 phút | Chủ quán | Mở **Đơn hàng**, thấy đơn mới trong khoảng 7 giây. Bấm Xác nhận (sang Đang làm), rồi Hoàn thành. Thử Hủy đơn để thấy bắt buộc nhập lý do | Luồng 3 bước, 4 trạng thái, không có "Đang giao" vì chỉ phục vụ tại bàn |
| 7 | 1 phút | Chủ quán | Mở **Doanh thu**, đổi giữa Hôm nay, 7 ngày, 30 ngày, Tháng này; xem món bán chạy | Chỉ đơn Hoàn thành được tính. Đơn vừa xong được cộng vào ngay |
| 8 | Dự phòng | Khách | Đăng ký tài khoản khách, lấy mã 6 số trong terminal (do `MAIL_CONSOLE=1`), vào **Lịch sử** và bấm Đặt lại | Email được xác nhận trước khi tạo tài khoản. Đặt lại dùng giá hiện tại |

## Kịch bản phụ (nếu còn thời gian)

- **Quán đóng cửa:** sửa giờ mở cửa ở **Hồ sơ quán** để quán đang đóng, tải lại menu: nút Đặt hàng đổi thành "Quán hiện không nhận đơn".
- **Mã QR bị đổi:** ở **Bàn & QR** đổi mã, rồi mở đường dẫn cũ: không mở được menu.
- **Quán chưa có số tài khoản:** vào Bún Chả 36, chọn chuyển khoản, xem thông báo quán chưa cập nhật.
- **Tính tiền theo bàn, đánh giá, khiếu nại:** dùng các mục trong README, phần "Kiểm tra nhanh các chức năng Sprint 3".

## Số liệu mẫu (để trả lời câu hỏi)

- 4 quán đã duyệt có đơn trong 15 ngày gần nhất, đủ 4 trạng thái. Hôm nay luôn có đơn Chờ xác nhận và Đang làm để thử xử lý.
- Số doanh thu thay đổi theo giờ chạy `seed_data.py`.

## Xử lý sự cố nhanh

| Sự cố | Cách xử lý |
|---|---|
| Camera không mở được | Trang cần HTTPS. Dùng ô dán đường dẫn hoặc mã bàn |
| Không nhận được mã email | Xem mã trong terminal đang chạy `app.py` (cần `MAIL_CONSOLE=1`) |
| Dữ liệu lộn xộn sau khi thử nhiều | Dừng server, chạy lại `python seed_data.py --reset` |
| Mất phiên đăng nhập | Đặt `SECRET_KEY` cố định khi chạy server |
