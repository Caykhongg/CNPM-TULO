# Chủ quán tự cấu hình ngân hàng — thanh toán thật

Bản này thay cấu hình xAPI theo từng quán trong `.env` bằng giao diện **Chủ quán → Ngân hàng & thanh toán**.
Dùng trên ứng dụng thật `python app.py`, cổng mặc định 5000. Không cần chạy demo hoặc nhập lệnh `pay`.

## Hành vi

| Cấu hình quán | Khách chuyển khoản | Ai xác nhận? |
|---|---|---|
| Có ngân hàng, không token | QR điền sẵn số tiền và mã chuyển khoản riêng | Chủ quán kiểm tra sao kê rồi bấm xác nhận |
| Có ngân hàng và token/URL xAPI đã kết nối | QR điền sẵn số tiền và mã chuyển khoản riêng | Server đọc xAPI và tự đối chiếu |
| Tiền mặt | Gửi đơn như trước | Quán thu tiền trực tiếp |

Phiếu chờ thanh toán chưa phải đơn bếp. Sau khi xác nhận, server tạo đúng một đơn `PENDING / PAID`, khách tự thấy **Thanh toán thành công**. Không duyệt thanh toán chỉ vì HTTP 200, ảnh biên lai hoặc khách tự bấm “đã chuyển”.
QR được tạo riêng theo phiếu qua VietQR Quick Link; không cần chủ quán tự upload ảnh QR cho từng đơn.

## 1. Cập nhật folder VS Code hiện tại

Tải `Update_QuickOrder_Bank.py` vào Downloads. Dừng server đang chạy bằng Ctrl+C, mở PowerShell tại folder Git hiện tại:

```powershell
cd "C:\Users\nhtanh\CNPM-TULO-FRESH"
python "$env:USERPROFILE\Downloads\Update_QuickOrder_Bank.py" --check
python "$env:USERPROFILE\Downloads\Update_QuickOrder_Bank.py"
```

- Đây là script cập nhật các file thanh toán ngay trong folder Git hiện tại, không tạo một bộ source ZIP khác.
- Hỗ trợ source main `5df8be9` và các bản XAPI trước đã gửi. Nhận diện cả LF/CRLF.
- Trước khi ghi, kiểm tra tất cả file. Nếu phát hiện sửa đổi riêng chưa biết, dừng và báo tên file, không ghi đè.
- Sao lưu các file code sẽ đổi vào thư mục `QuickOrder-code-backups` trong thư mục người dùng, ngoài repo.
- Không sửa `.env`, không reset/xóa CSDL, không đổi nhánh/remote, không commit/push.
- Nếu chỉ báo file có sửa riêng, gửi log và file đó để gộp thay đổi; không dùng reset/force để vượt qua.
- Có file patch đi kèm để xem toàn bộ thay đổi trước khi chạy.

Cài thêm thư viện mã hóa token:

```powershell
cd QuickOrder
python -m pip install -r requirements.txt
```

Ứng dụng tự thêm bảng/cột khi khởi động và giữ phiếu, giao dịch, đơn cũ. Không chạy `init_db.py --reset`.

## 2. Cấu hình chung của website một lần

Mở `QuickOrder/.env`. Giữ các biến mail đang dùng.
Cần có `SECRET_KEY` ngẫu nhiên, cố định, ít nhất 32 ký tự để bảo vệ phiên và mã hóa token ngân hàng.
Nếu đã có giá trị phù hợp thì giữ nguyên.

Tạo giá trị nếu chưa có:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Điền kết quả vào:

```dotenv
SECRET_KEY=KET_QUA_VUA_TAO
HTTPS=0
```

Nếu `SECRET_KEY` đang dùng cần giữ nguyên nhưng ngắn hơn yêu cầu, có thể dùng khóa mã hóa riêng:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Điền kết quả vào `PAYMENT_ENCRYPTION_KEY` trong `.env`. Luôn giữ cố định và sao lưu khóa mã hóa khi sao lưu CSDL.
Không đổi/xóa khóa sau khi đã lưu token, vì sẽ không đọc được dữ liệu đã mã hóa.

Không cần thêm `XAPI_SHOP_1`, `XAPI_SHOP_2`... cho các quán mới. Chủ quán sẽ nhập trên web.
Biến `XAPI_SHOP_<ID>` cũ chỉ được giữ để các phiếu cũ tiếp tục hoạt động trước khi chủ quán chuyển cấu hình lên web.

Chạy server:

```powershell
python app.py
```

## 3. Chủ quán thêm ngân hàng thật

Mở:

```text
http://127.0.0.1:5000/merchant/shop.html#bank-section
```

Đăng nhập tài khoản chủ quán của ứng dụng thật. Nếu chưa có quán, lưu thông tin quán ở phía trên trước.
Quán cần được quản trị duyệt và đang trong giờ nhận món khi thử đặt đơn.

Trong **Ngân hàng nhận chuyển khoản**:

1. Chọn ngân hàng từ danh sách.
2. Nhập số tài khoản đúng tài khoản đã liên kết bên xapi.vn.
3. Nhập tên chủ tài khoản.
4. Chọn một trong hai cách:
   - **Thủ công:** để trống ô Token/URL, bấm Lưu ngân hàng.
   - **Tự động:** dán token hoặc URL API lịch sử xAPI, bấm Lưu ngân hàng.

Server kiểm tra URL/token bằng một request đọc lịch sử thật trước khi lưu chế độ tự động.
Nếu lỗi, hiển thị lỗi và giữ cấu hình đã hoạt động trước đó; không tự chuyển thành đã kết nối.
Khi thành công, hiện **Đã kết nối xAPI**, có nút Kiểm tra kết nối.

### Token hay URL API?

Mỗi ngân hàng/phiên bản xAPI có thể có đường dẫn riêng. Hiện có mẫu token thuần cho TPBank và ACB. TPBank theo tài liệu công khai; đường dẫn ACB đã được đối chiếu từ báo cáo chẩn đoán của người dùng:

```text
https://id.xapi.vn/historyapitpbv2/TOKEN
https://id.xapi.vn/historyapiacb/TOKEN
```

Với ngân hàng khác hoặc phiên bản khác, dán **nguyên URL API lịch sử do xAPI cấp** vào chính ô Token/URL. Server tự xử lý và mã hóa URL, không cần sửa code theo từng quán.
Không thay tên ngân hàng trong URL mẫu rồi đoán endpoint. Nếu cần mở rộng token thuần cho một loại ngân hàng, quản trị có thể cấu hình mẫu đã kiểm chứng một lần bằng `XAPI_ENDPOINTS_JSON`.

URL hiện hỗ trợ HTTPS trên `id.xapi.vn`, dạng `/historyapi.../TOKEN`, JSON chuẩn có `status=success` và mảng `transactions`. Riêng ACB hỗ trợ `codeStatus=200` và mảng `data`, chuẩn hóa mã giao dịch trước khi đối soát. ACB chỉ nhận `type=IN/OUT`; chiều tiền khác sẽ báo chưa hỗ trợ, không tự đoán. Trường `account` (nếu có) phải khớp STK quán và `currency` (nếu có) phải là VND. Endpoint/JSON khác cần đối chiếu tài liệu thực tế để bổ sung adapter; không suy diễn dữ liệu thanh toán.

Không dán URL trang dashboard/đăng nhập thay cho API lịch sử. Không đưa token vào ảnh chụp hoặc GitHub.
Kết nối đọc được lịch sử chưa chứng minh thông tin STK nhập tay khớp tài khoản trên xAPI: kiểm tra đúng tài khoản ở cả hai bên và thực hiện bài thử tiền thật bên dưới trước khi mở cho khách.

## 4. Thử với ngân hàng thật

Giữ `python app.py` đang chạy. Không chạy `demo_xapi_local.py`.

1. Phía chủ quán, vào **Bàn & QR**, mở/quét QR bàn thật của quán trên localhost.
2. Phía khách, chọn món có giá nhỏ phù hợp để kiểm tra. Có thể dùng cửa sổ ẩn danh để giữ riêng phiên khách và chủ quán.
3. Vào Giỏ hàng → Chuyển khoản → Thanh toán chuyển khoản.
4. Trang phải hiện QR thật, số tiền, tài khoản nhận và mã riêng `QO...`.
5. Dùng một tài khoản khác của anh để chuyển vào tài khoản nhận của quán. Trước khi xác nhận trên app ngân hàng, kiểm tra người nhận, số tiền và nội dung đã điền đúng.
6. Không sửa nội dung/mã thanh toán hoặc số tiền khi thử đối soát tự động.
7. Sau khi xAPI cập nhật giao dịch tiền vào, server tự xác nhận, tạo một đơn đã thanh toán và trang khách tự chuyển sang báo thành công.
8. Bên chủ quán, Đơn hàng xuất hiện đúng một đơn `PAID`, kể cả khi khách refresh nhiều lần.

App ngân hàng có thể không cho tự chuyển vào chính tài khoản đang dùng; dùng tài khoản gửi khác để thử.
Không cần public localhost hoặc ngrok cho luồng này: server chủ động gọi API lịch sử của xAPI.
Server có tác vụ nền tự chạy sau request đầu tiên, tiếp tục đối soát khi khách đóng tab, miễn server vẫn hoạt động.

## 5. Thử chế độ thủ công

Lưu ngân hàng nhưng không nhập token (hoặc bấm **Dùng duyệt thủ công cho phiếu mới**).

1. Khách tạo phiếu chuyển khoản và chuyển tiền theo QR.
2. Trang khách hiện **Chờ quán xác nhận thanh toán**.
3. Chủ quán vào **Ngân hàng & thanh toán → Chuyển khoản đang chờ xác nhận**.
4. Kiểm tra TIỀN VÀO đúng số tiền và nội dung trên app/sao kê ngân hàng.
5. Bấm **Đã kiểm tra và nhận đủ tiền**, nhập mã giao dịch ngân hàng.
6. Server tạo đơn đã thanh toán. Trang khách tự hiện thành công.

Khách không có quyền tự duyệt. Chủ quán khác không đọc/duyệt phiếu của quán này.
Mã giao dịch đã dùng không thể duyệt phiếu thứ hai. Bấm hai lần không gửi trùng đơn.

## 6. Đổi ngân hàng, token và các ngoại lệ

- Đổi số tài khoản/ngân hàng thì QR mới dùng tài khoản mới. Các phiếu cũ giữ tài khoản đã in trên QR và vẫn đối soát tài khoản cũ.
- Cập nhật token cho cùng tài khoản sẽ dùng token hợp lệ mới để kiểm tra cả phiếu cũ và mới của tài khoản đó.
- Bỏ trống token khi đang có kết nối sẽ giữ token cũ, không làm mất kết nối. Muốn tắt tự động, dùng nút chuyển thủ công.
- Tắt tự động chỉ áp dụng phiếu mới; các phiếu tự động đã tạo vẫn cần được đối soát theo tài khoản cũ.
- Phiếu có hạn 15 phút; coupon được giữ một lượt và trả lại khi hết hạn. Sai tiền/tiền đến muộn/quán đóng hoặc món hết thì không tự gửi đơn.
- Xem **Giao dịch cần đối soát** để xử lý khoản cần kiểm tra. Ghi chú xử lý không tự hoàn tiền.
- Hủy đơn đã thanh toán không tự hoàn tiền; hệ thống giữ dấu tiền nhận và ghi mục cần xử lý cho quán.
- Chỉ đối soát tiền vào `type=IN`, số VND nguyên, mã riêng khớp và transactionID chưa dùng. Không dùng `status=success` thay cho chứng cứ thanh toán.
- Không tự ghép nhiều khoản thiếu tiền. Nguồn dữ liệu mặc định: `transactionID`, `amount`, `description`, `type`.
- Quét lại các tài khoản có phiếu trong 30 ngày để nhận diện khoản đến muộn/trùng. API có thể chỉ trả một số giao dịch gần nhất, nên cần duy trì server hoạt động và xử lý lỗi kết nối kịp thời.

## 7. Triển khai Render

Bản hiện tại dùng SQLite. Trước khi nhận tiền thật trên Render:

- CSDL `QO_DB` phải nằm trên bộ nhớ bền vững, ví dụ persistent disk `/var/data/quickorder.db`; giữ dữ liệu cũ và sao lưu trước khi chuyển đường dẫn.
- Giữ cố định `SECRET_KEY`/`PAYMENT_ENCRYPTION_KEY`, đặt trong Render Environment; `.env` trên máy không tự lên Render.
- Dùng HTTPS và đặt `HTTPS=1`.
- Server phải hoạt động liên tục để tác vụ nền quét được khi khách đóng tab. Gói tự ngủ sẽ dừng quét lúc service ngủ; request tiếp theo mới đánh thức lại.
- Mặc định `PAYMENT_WORKER=1`. Không cần worker service khác dùng chung SQLite hoặc lệnh quét riêng. Nhiều process trong một service dùng khóa trong CSDL để tránh gọi dồn và xử lý trùng.
- Endpoint scheduler cũ vẫn giữ cho quản trị nếu cần dự phòng, nhưng không bắt buộc cho thử local.

Không đổi CSDL giữa lúc đang có phiếu chờ nhận tiền. Persistent disk/DB bền vững là yêu cầu dữ liệu thanh toán, không thể khắc phục bằng JavaScript.

## 8. File chính và kiểm thử

| File | Chức năng |
|---|---|
| `merchant/shop.html`, `js/owner-bank.js` | Chủ quán nhập ngân hàng và token, duyệt thủ công |
| `bank_catalog.json` | Danh sách ngân hàng chuyển khoản từ API VietQR |
| `bank_connections.py` | Mã hóa token, chọn cấu hình và ghép URL hợp lệ |
| `owner_bank_api.py` | API cấu hình/kiểm tra kết nối và xác nhận thủ công đúng quyền |
| `payment_api.py` | Tạo QR, đối soát nền, chống trùng và tạo đơn |
| `xapi_client.py` | Gọi API lịch sử thật từ server |
| `js/payment.js` | Tự hiện thành công sau khi server xác nhận |
| `app.py`, `schema.sql` | Luồng đặt đơn, nâng cấp dữ liệu và giữ phiếu cũ |

Kiểm thử kỹ thuật không gọi tài khoản/ngân hàng thật:

```powershell
python -m unittest discover -s tests -v
node --test tests/test_customer_order_pages.cjs
```

Để xem toàn bộ thay đổi và commit trên nhánh của anh:

```powershell
cd "C:\Users\nhtanh\CNPM-TULO-FRESH"
git status --short
git diff --stat
```

Stage file code/tài liệu/test qua VS Code; không stage `.env`, CSDL runtime hoặc backup. Commit/push nhánh cá nhân sau khi kiểm tra giao dịch thật thành công.

Nguồn đối chiếu:
- https://xapi.vn/
- https://www.vietqr.io/qr-dong
- https://api.vietqr.io/v2/banks
- https://cryptography.io/en/latest/fernet/
- https://render.com/docs/disks
- https://render.com/docs/free
