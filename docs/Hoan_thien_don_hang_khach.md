# Luồng đặt, theo dõi và danh sách đơn của khách

## Các chức năng trong bản sửa

- `QuickOrder/customer/cart.html`: gửi đơn, chặn bấm lặp khi đang gửi, giữ giỏ nếu API báo lỗi; khi thành công lưu mã đơn, xóa giỏ và mở `track.html?id=...`.
- `QuickOrder/customer/track.html` + `js/order-tracking.js`: theo dõi từng đơn, tiến trình ba bước Chờ xác nhận → Đang làm → Hoàn thành; thể hiện riêng Đã hủy và lý do; xem món, tùy chọn, tiền, giảm giá, thanh toán; cập nhật mỗi 7 giây, khi quay lại tab hoặc bấm Tải lại.
- `QuickOrder/customer/orders.html`: danh sách đơn lưu trên thiết bị, lọc bốn trạng thái, mở theo dõi, hủy đơn chờ xác nhận; giữ chức năng đánh giá và khiếu nại. Lỗi kết nối có thông báo và nút Tải lại.
- `QuickOrder/customer/history.html`: đơn thuộc tài khoản cũng có liên kết Theo dõi đơn.
- API hủy đơn kiểm tra mã riêng hoặc tài khoản khách sở hữu đơn, sau đó chỉ cập nhật khi trạng thái vẫn là PENDING. Nếu quán vừa xác nhận, trả 409; giao diện lấy lại trạng thái mới và bỏ nút hủy.
- Trạng thái cũ CONFIRMED được hiển thị là Đang làm. Bộ lọc và tiến trình chỉ dùng bốn trạng thái theo yêu cầu.
- Khi trình duyệt không lưu được localStorage, đơn vừa tạo vẫn mở được bằng mã trong fragment của URL. Fragment không được gửi lên server như tham số trang; nếu lưu lại được thì mã được bỏ khỏi thanh địa chỉ. Khách giữ liên kết này riêng vì nó cấp quyền xem/hủy đơn.

## Chạy trong folder VS Code đang dùng

Dùng app ở `QuickOrder/`. Repo có một bản cũ nằm trong thư mục lồng `QuickOrder/QuickOrder/`.

Từ thư mục gốc repo, kích hoạt môi trường ảo hiện có rồi chạy:

```powershell
cd QuickOrder
python -m pip install -r requirements.txt
python app.py
```

Mở `http://127.0.0.1:5000`. Dùng một cửa sổ chủ quán và một cửa sổ ẩn danh cho khách. Tại cửa sổ chủ quán, mở **Bàn & QR**, sao chép liên kết bàn local rồi mở trong cửa sổ khách. Chọn quán đã duyệt và đang mở cửa.

## Kiểm thử

Trong `QuickOrder/`, chạy các test Python bằng CSDL tạm:

```powershell
python -m unittest discover -s tests -v
```

Nếu máy có Node.js, chạy thêm kiểm thử logic trang, không cần cài npm package:

```powershell
node --test tests/test_customer_order_pages.cjs
```

| Ca | Thao tác | Kết quả cần thấy |
|---|---|---|
| 1 | Chọn đủ tùy chọn món, vào giỏ, bấm Đặt hàng | Mở Theo dõi đơn có đúng mã đơn; giỏ trống |
| 2 | Bấm Đặt hàng nhanh hai lần | Chỉ có một yêu cầu trong lúc nút đang gửi |
| 3 | Gửi đơn khi API bị lỗi | Có thông báo, giữ món trong giỏ |
| 4 | Hủy đơn A khi còn Chờ xác nhận | Chuyển Đã hủy, bỏ nút Hủy đơn |
| 5 | Tạo đơn B; chủ quán xác nhận | Trang theo dõi và danh sách tự đổi sang Đang làm trong khoảng 7 giây, bỏ nút Hủy đơn |
| 6 | Chủ quán hoàn thành B | Tự đổi Hoàn thành; tổng tiền và món giữ nguyên |
| 7 | Khách bấm hủy khi quán vừa xác nhận | Thông báo không hủy được; lấy lại trạng thái Đang làm |
| 8 | Tạm mất mạng ở trang theo dõi/danh sách rồi kết nối lại | Giữ dữ liệu đã tải/đơn đã lưu, Tải lại phục hồi được |
| 9 | Mở Lịch sử ở phiên đăng nhập khác của cùng tài khoản, vào Theo dõi và hủy đơn chờ | Xem/hủy được đơn thuộc tài khoản mà không cần mã lưu trên thiết bị đó |
| 10 | Dùng tài khoản khách khác, chỉ đổi id đơn | Không đọc hoặc hủy được đơn của người khác |

Giữ tab khách đang hiển thị khi kiểm tra tự cập nhật. Khi quay lại tab, trang tải lại ngay. Chụp ảnh kết quả trên máy thực tế để đính kèm issue.

## Hoàn thiện phần Figma

Các file trong `docs/figma-don-hang/` là bản mẫu SVG do code tạo, không phải file Figma đã xuất bản:

1. `01-danh-sach-don.svg`.
2. `02-theo-doi-cho-xac-nhan.svg`.
3. `03-theo-doi-dang-lam.svg`.
4. `04-theo-doi-hoan-thanh.svg`.
5. `05-theo-doi-da-huy.svg`.

Tạo một Figma Design file rồi kéo các SVG vào canvas. SVG được nhập thành vector, không phải ảnh chụp. Đặt mỗi mẫu trong một Frame, kiểm tra chữ/font và điều chỉnh theo giao diện thực tế. Nội dung mẫu minh họa dữ liệu, không phải dữ liệu đơn thật.

Nối prototype từ nút Theo dõi sang màn theo dõi, nút Hủy sang trạng thái Đã hủy (có thể thêm hộp xác nhận), và nút Danh sách đơn quay lại danh sách. Các trạng thái Đang làm/Hoàn thành mô phỏng thay đổi từ chủ quán, khách không tự chuyển trạng thái.

Chọn Share, cấp quyền xem cho nhóm/giảng viên và sao chép link thật. Thêm link đó vào README/issue. SVG chỉ giúp chuẩn bị thiết kế; nhiệm vụ Figma được chốt khi có file Figma hoàn thiện và link mở được.

Tạo lại SVG từ thư mục gốc repo nếu cần:

```powershell
python docs/figma-don-hang/generate_frames.py
```

## Minh chứng nộp nhiệm vụ

- Link Figma thật.
- Ảnh đặt thành công, giỏ trống, Chờ xác nhận, Đang làm, Hoàn thành và Đã hủy.
- Kết quả kiểm thử trên máy.
- Commit/PR chứa code và tài liệu liên quan.

Không đưa `.env`, thông tin xác thực hoặc database chứa dữ liệu người dùng vào commit.
