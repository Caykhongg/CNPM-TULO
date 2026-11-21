# Báo cáo kiểm thử QuickOrder — 21/11/2026

## 1. Kết luận tóm tắt

Lần báo cáo này áp dụng cho đúng source trong repository `Caykhongg/CNPM-TULO`, branch `khainguyen020507-patch-5`, commit `7471c0e` (thư mục ứng dụng `QuickOrder/`). Source này khác với bản local lớn hơn đã được kiểm thử trước đó; vì vậy **không dùng số liệu 187 test / 81,8% coverage của bản local để mô tả branch này**.

| Phạm vi | Kết quả | Căn cứ |
|---|---:|---|
| Unittest trên branch | 61 chạy, 61 PASS, 0 FAIL, 0 ERROR, 0 SKIP | `QuickOrder/tests/`: 22 customer, 30 orders, 9 revenue |
| Statement coverage trên branch | 63,0% tổng; `app.py` 71%; `mailer.py` 48% | Coverage report của lần chạy branch; không phải branch coverage |
| 29 case Sprint 3 | 8 PASS, 6 PASS MỘT PHẦN, 14 KHÔNG CÓ TÍNH NĂNG, 1 CHƯA TEST | [Sprint3_Test_Cases_VN.xlsx](./Sprint3_Test_Cases_VN.xlsx), sheet `Test Cases` |
| Doanh thu | Khoảng 7/30 ngày, nhóm ngày/tháng, dữ liệu tổng và món bán chạy được kiểm tra | UI cục bộ và `tests/test_revenue.py` |
| QR / bàn | Link bàn và token cũ/mới được kiểm tra; ảnh QR không tải được; chưa quét camera thật | UI/API; CDN tạo QR bị browser chặn |
| Coupon / đánh giá / một số trang Admin | Không có trong branch đã kiểm thử | Route/API và source branch; ghi cụ thể ở workbook |

`KHÔNG CÓ TÍNH NĂNG` nghĩa là không tìm thấy chức năng cần kiểm thử trong đúng branch, không phải kết luận rằng chức năng hoạt động. `CHƯA TEST` nghĩa là chưa có bằng chứng thực hiện; không suy ra PASS/FAIL.

## 2. Căn cứ và phạm vi

- Mô tả nhiệm vụ Sprint 3 người dùng cung cấp: thống kê doanh thu/Chart.js, coupon, đánh giá, QR đặt tại bàn, hoàn thiện Admin và responsive mobile.
- Tài liệu yêu cầu hiện có trong branch: `docs/SRS_QuickOrder_v1.0.docx`. Đây là căn cứ dự án; các chức năng bổ sung riêng của Sprint 3 vẫn đối chiếu thêm theo mô tả sprint.
- Source và giao diện trong branch `khainguyen020507-patch-5`, commit `7471c0e`.
- Assertion trong `QuickOrder/tests/` và kết quả thao tác UI/API trên server local cô lập.

Phạm vi kiểm thử thủ công dùng database QA tạm, không dùng production. Địa chỉ kiểm thử local là `http://127.0.0.1:5002`. Các số liệu về doanh thu là dữ liệu QA tạo cho lần chạy, không phải doanh thu thật.

## 3. Kết quả unittest và coverage

| File test | Số test | Kết quả |
|---|---:|---|
| `tests/test_customer.py` | 22 | 22 PASS |
| `tests/test_orders.py` | 30 | 30 PASS |
| `tests/test_revenue.py` | 9 | 9 PASS |
| **Tổng** | **61** | **61 PASS, 0 lỗi** |

Statement coverage đo được là 63,0% tổng thể; `app.py` 71%; `mailer.py` 48%. Đây không phải branch coverage và không chứng minh mọi yêu cầu nghiệp vụ hoặc giao diện đã được kiểm thử. `init_db.py` và `seed_data.py` không được suite thực thi.

Môi trường kiểm thử dùng Python 3.9.6, thiếu `hashlib.scrypt`; để chạy setup test, tiến trình test dùng fallback PBKDF2 cho Werkzeug. Thay đổi này chỉ ở tiến trình kiểm thử, không sửa source ứng dụng hoặc cấu hình dữ liệu production. Khi chạy lại, ưu tiên phiên bản Python theo README của dự án; nếu dùng Python 3.9 thì cần thực hiện đúng fallback test-only đã ghi trong báo cáo/workbook.

## 4. Kiểm tra UI/API đã thực hiện

### Doanh thu

- Trang doanh thu hiển thị lựa chọn hôm nay, 7 ngày, 30 ngày, tháng này và chọn khoảng ngày.
- 7 ngày hiển thị khoảng 15/11/2026–21/11/2026; 30 ngày hiển thị 23/10/2026–21/11/2026.
- Chuyển nhóm theo tháng làm đổi nhãn/tiêu đề biểu đồ.
- Với dữ liệu QA, trang hiển thị 60.000đ, 1 đơn hoàn thành và món QA Coffee bán 1 phần, doanh thu 60.000đ.
- Gửi khoảng ngày sai thứ tự nhận HTTP 400 cùng thông báo khoảng ngày không hợp lệ. Tuy nhiên UI vẫn giữ số liệu/khoảng cũ trong khi input đang là khoảng sai, có thể gây nhầm; vì vậy S3-REV-04 được ghi PASS MỘT PHẦN, không phải PASS toàn bộ.
- Ở viewport 390×844, trang không tràn ngang theo `document.documentElement.scrollWidth`; biểu đồ canvas được render.

Ảnh bằng chứng:

- [revenue-desktop.png](./evidence/revenue-desktop.png)
- [revenue-mobile.png](./evidence/revenue-mobile.png)
- [revenue-group-by-month.png](./evidence/revenue-group-by-month.png)
- [revenue-invalid-date.png](./evidence/revenue-invalid-date.png)
- [qr-cdn-blocked.png](./evidence/qr-cdn-blocked.png)
- [tables-mobile.png](./evidence/tables-mobile.png)

### QR và bàn

- Tạo bàn `QA-TEST-21-11` thành công; link mở đúng quán `Branch QA Cafe`, đúng bàn và nút gọi món bật.
- Sau khi đổi token, link cũ báo token đã đổi và khóa gọi món; link mới mở đúng bàn.
- `tests/test_orders.py::test_table_must_belong_to_shop` xác nhận không nhận bàn thuộc quán khác.
- Không ghi PASS cho ảnh QR: thư viện QR từ CDN bị browser chặn, ảnh không có `src`. Nút “Tải mã QR” vẫn hiện trên giao diện nhưng không có mã QR để tải; chưa xác nhận tải file. Chưa quét QR bằng camera điện thoại vật lý.

### Admin

- Trang duyệt quán Admin hiện có và đã xem được bằng tài khoản QA.
- API danh mục: tạo 201, danh mục trùng 409, sửa 200, xóa 204.
- API khóa/mở quán trả 200; trạng thái QR đổi giữa `LOCKED` và `APPROVED`; đặt món bị từ chối khi quán khóa và hoạt động lại sau khi mở.
- Admin dashboard, users, categories UI và API admin statistics/users trả 404 trong branch đã kiểm thử. Vì vậy không kết luận các chức năng này đã được triển khai.
- Thao tác khóa quán qua UI chưa xác minh được do browser harness không hỗ trợ hộp thoại `prompt()`; luồng API đã được kiểm tra riêng.

## 5. Tóm tắt 29 test case Sprint 3

| Nhóm | PASS | PASS MỘT PHẦN | KHÔNG CÓ TÍNH NĂNG | CHƯA TEST | Ghi chú |
|---|---:|---:|---:|---:|---|
| Doanh thu | 4 | 1 | 0 | 0 | Khoảng sai bị từ chối, nhưng UI còn giữ số liệu cũ |
| Coupon | 0 | 0 | 6 | 0 | Không có chức năng trong branch |
| Đánh giá món/quán | 0 | 0 | 3 | 0 | Không có chức năng trong branch |
| QR tại bàn | 2 | 1 | 0 | 1 | Link/token hoạt động; tạo ảnh QR và camera chưa xác nhận |
| Admin | 1 | 2 | 3 | 0 | Khóa/mở quán và category API có; một số trang/API không có |
| Responsive mobile | 1 | 2 | 2 | 0 | Chỉ kiểm tra các trang hiện có |
| **Tổng** | **8** | **6** | **14** | **1** | 29 case |

Chi tiết từng bước, kết quả mong đợi, kết quả thực tế và bằng chứng nằm trong sheet `Test Cases` của workbook Sprint 3. Số liệu cũ hiển thị sau khi nhập khoảng ngày sai là một phát hiện giao diện cần cân nhắc sửa; báo cáo hiện không tự thay đổi source ứng dụng.

## 6. Cách chạy lại

Từ thư mục ứng dụng `QuickOrder/`, dùng Python theo README:

```bash
python -m unittest discover -s tests -v
```

Để chạy riêng từng nhóm:

```bash
python -m unittest discover -s tests -p "test_customer.py" -v
python -m unittest discover -s tests -p "test_orders.py" -v
python -m unittest discover -s tests -p "test_revenue.py" -v
```

Chạy lệnh trong bản clone/branch cần kiểm thử và đọc kết quả thực tế của lần chạy đó. Không dùng kết quả từ một bản source khác để báo cáo cho branch này.

## 7. Giới hạn và việc chưa xác nhận

1. Coupon, đánh giá và một số chức năng Admin chưa có trong branch; cần triển khai/merge đúng source trước khi có thể kiểm thử chức năng.
2. QR image phụ thuộc CDN ngoài bị browser chặn trong lần chạy; chưa xác nhận tạo/tải ảnh hoặc quét bằng camera vật lý.
3. Admin lock UI bị giới hạn bởi hộp thoại `prompt()` của browser harness; API được kiểm tra nhưng không thay thế hoàn toàn thao tác UI.
4. Browser test là kiểm tra thủ công trên local QA, không phải kiểm thử production; email thật và giao dịch ngân hàng thật không thuộc lần chạy này.
5. Các kết quả local cũ (187 test, 81,8% coverage) được lưu riêng trong file/sheet lịch sử và áp dụng cho source khác, không gộp vào số liệu branch hiện tại.

## 8. Tài liệu kèm theo

- [Test case Sprint 3](../Sprint3_Test_Cases_VN.xlsx)
- [Báo cáo test Sprint 4 có sheet chạy lại branch](../QuickOrder_Test_spint4.xlsx)
- [Hướng dẫn kiểm thử và trả lời](./QuickOrder_Huong_Dan_Kiem_Thu_va_Tra_Loi.docx)
- [Ảnh bằng chứng](./evidence/)
