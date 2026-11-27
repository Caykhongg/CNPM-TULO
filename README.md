# 🍵 QuickOrder – Ứng dụng gọi món tại bàn cho quán nhỏ

> Đồ án cuối kỳ môn **Công nghệ phần mềm** – Khoa Công nghệ Thông tin và Truyền thông, Đại học CMC
> Nhóm thực hiện: **Nhóm TULO**

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey)
![SQLite](https://img.shields.io/badge/SQLite-3-green)
![Status](https://img.shields.io/badge/Status-Hoàn%20thành%20Sprint%205-brightgreen)

---

## 📌 Mục lục

1. [Giới thiệu](#-giới-thiệu)
2. [Luồng hoạt động](#-luồng-hoạt-động)
3. [Vấn đề và giải pháp](#-vấn-đề-và-giải-pháp)
4. [Đối tượng người dùng](#-đối-tượng-người-dùng)
5. [Chức năng chính](#-chức-năng-chính)
6. [Công nghệ sử dụng](#-công-nghệ-sử-dụng)
7. [Cấu trúc thư mục](#-cấu-trúc-thư-mục)
8. [Hướng dẫn cài đặt và chạy](#-hướng-dẫn-cài-đặt-và-chạy)
9. [Tài khoản demo](#-tài-khoản-demo)
10. [Các endpoint API chính](#-các-endpoint-api-chính)
11. [Tài liệu dự án](#-tài-liệu-dự-án)
12. [Quy trình làm việc nhóm](#-quy-trình-làm-việc-nhóm)
13. [Kế hoạch thực hiện](#-kế-hoạch-thực-hiện)
14. [Thành viên nhóm](#-thành-viên-nhóm)

---

## 📖 Giới thiệu

**QuickOrder** là ứng dụng web giúp các quán ăn, quán nước quy mô nhỏ (trà sữa, cà phê, cơm, bún phở) nhận và quản lý đơn gọi món **ngay tại bàn**.

- Mỗi bàn có **một mã QR**. Khách ngồi tại quán quét mã bằng điện thoại, xem menu và gọi món, **không cần cài ứng dụng, không cần đăng nhập**.
- Đơn được gửi **thẳng đến quầy/bếp**. Chủ quán nhận đơn, cập nhật trạng thái và theo dõi doanh thu ngay trên hệ thống.
- **Không thu phí hoa hồng** cho nền tảng trung gian.
- Hỗ trợ **thanh toán chuyển khoản qua VietQR** với đối soát tự động hoặc chủ quán xác nhận thủ công (FR-27).
- Hệ thống chỉ phục vụ **khách ăn tại quán**, không có đặt hàng từ xa hay giao hàng.

## 🔄 Luồng hoạt động

```mermaid
flowchart LR
    A[Khách quét QR tại bàn] --> B[Xem menu và chọn món]
    B --> C[Gửi đơn]
    C --> D{Chủ quán xác nhận}
    D -->|Đồng ý| E[Đang làm]
    D -->|Từ chối| G[Đã hủy]
    E --> F[Hoàn thành]
```

## 🎯 Vấn đề và giải pháp

**Vấn đề:** các quán nhỏ hiện nhận món chủ yếu bằng cách nhân viên ghi tay hoặc gọi miệng tại bàn, dẫn đến:

- Dễ nhầm đơn, sót món, khó theo dõi trạng thái từng đơn.
- Khách phải vẫy gọi nhân viên nhiều lần, chờ lâu mới được ghi món; không biết món còn hay hết.
- Chủ quán không có số liệu thống kê doanh thu, món bán chạy để ra quyết định kinh doanh.
- Các nền tảng lớn thu phí hoa hồng cao, quán nhỏ khó chịu nổi.

**Giải pháp:** hệ thống gọi món tại bàn gồm ba phân hệ **Khách hàng – Chủ quán – Quản trị viên**.

## 👥 Đối tượng người dùng

| Vai trò | Mục tiêu sử dụng |
|---|---|
| **Khách hàng** (ngồi tại quán) | Quét QR, xem menu, gọi món nhanh, theo dõi đơn; không cần tài khoản |
| **Chủ quán / nhân viên** | Quản lý bàn và QR, quản lý menu, nhận đơn, cập nhật trạng thái, xem thống kê, xử lý khiếu nại của quán |
| **Quản trị viên (Admin)** | Duyệt và khóa quán, quản lý người dùng, xem thống kê chung |

## ✨ Chức năng chính

### 🛒 Phân hệ khách hàng (không cần đăng nhập)
- Quét mã QR tại bàn để mở menu đúng quán, gắn sẵn số bàn
- Xem menu, tìm món, lọc theo danh mục
- Chọn món kèm tùy chọn (size, topping, ghi chú), quản lý giỏ hàng
- **Gợi ý món** ở đầu menu: món bán chạy của quán và món bạn hay gọi (khi có tài khoản)
- **Nhập mã giảm giá** ở giỏ hàng, xem tổng tiền sau giảm trước khi gửi đơn
- Gửi đơn thẳng đến quầy bếp; gọi thêm món bất cứ lúc nào
- Thanh toán **tiền mặt** tại quầy hoặc **chuyển khoản VietQR**: mã QR điền sẵn số tiền và mã chuyển khoản riêng (dạng `QO…`); giá được tính lại ở máy chủ; đơn chỉ được gửi đến quán sau khi tiền về hoặc chủ quán xác nhận; xem lại các phiếu thanh toán của mình
- Theo dõi trạng thái đơn: *Chờ xác nhận → Đang làm → Hoàn thành*; hủy đơn khi chưa được xác nhận
- **Đánh giá** quán và từng món sau khi đơn hoàn thành (mỗi đơn một lần)
- **Gửi khiếu nại** về một đơn và xem phản hồi của quán ngay trong đơn đó
- *(Nâng cao)* Đăng ký tài khoản tùy chọn (xác nhận bằng mã 6 số gửi qua email) và sửa hồ sơ cá nhân. Đơn đặt khi đăng nhập tự lưu vào lịch sử tài khoản. Đơn đặt trước khi đăng nhập có thể chọn “Lưu vào lịch sử” trên đúng trình duyệt còn mã đơn. Hỗ trợ **lịch sử đơn** và **đặt lại món** (kiểm tra món còn hay hết, dùng giá hiện tại)

### 🏪 Phân hệ chủ quán
- Đăng ký quán, quản lý thông tin quán và giờ mở cửa
- **Quản lý bàn và tạo mã QR** cho từng bàn
- Quản lý menu: thêm, sửa, xóa món, hình ảnh, giá, tùy chọn, đánh dấu hết món
- **Cấu hình nhận chuyển khoản** (FR-27): chọn ngân hàng, nhập số tài khoản và token/URL xAPI ngay trên web, có nút kiểm tra kết nối. Không nhập token thì chạy chế độ **thủ công** (chủ quán xác nhận); kết nối xAPI hợp lệ thì chạy chế độ **tự động** đối soát. Token được mã hóa ở máy chủ, không trả về trình duyệt
- **Phiếu thanh toán và biên lai:** xem phiếu chờ, xác nhận thủ công, xem biên lai nhận tiền; biên lai lệch tiền hoặc không khớp vào trạng thái **REVIEW** để chủ quán xử lý; chống trùng biên lai
- Vẫn có thể tải ảnh QR thanh toán lên (cách cũ)
- **Nhận thông báo đơn mới** (số đơn chờ trên tiêu đề trang, âm báo tùy chọn), lọc đơn theo trạng thái và ngày, xác nhận hoặc từ chối đơn (kèm lý do), cập nhật trạng thái đơn
- Xác nhận thanh toán; **tính tiền theo bàn** (xem các đơn chưa trả của bàn và thu một lần)
- Thống kê doanh thu theo ngày/tháng và món bán chạy (chỉ tính đơn đã hoàn thành, ngày theo giờ Việt Nam)
- **Mã giảm giá**: tạo, tắt/bật, xóa mã giảm theo % hoặc số tiền, đơn tối thiểu, thời hạn, số lượt; khách nhập mã ở giỏ hàng
- **Khiếu nại (FR-55)**: chỉ chủ quán xem, phản hồi và đóng khiếu nại về các quán của mình; quản trị viên không có API xử lý khiếu nại
- **Xem đánh giá** của khách (điểm trung bình, phân bố sao, nhận xét, điểm từng món); khách đánh giá đơn đã hoàn thành một lần

### 🛡️ Phân hệ quản trị viên
- Duyệt, từ chối, **khóa hoặc mở khóa quán** (quán bị khóa không nhận đơn, mã QR cũ dùng lại được khi mở khóa)
- **Quản lý người dùng**: tìm theo tên, email, số điện thoại; lọc theo vai trò và trạng thái; khóa hoặc mở khóa tài khoản (không tự khóa chính mình)
- **Quản lý danh mục món**: thêm, sửa, xóa; không xóa được danh mục đang có món
- **Thống kê toàn hệ thống**: tổng số quán, người dùng, đơn hàng và doanh thu (chỉ tính đơn đã hoàn thành)
- Khiếu nại do chủ quán của quán đó xử lý, quản trị viên không can thiệp (FR-55)

### 🚀 Điểm nổi bật
- **Gọi món bằng QR tại bàn:** khách quét là gọi, không cần app, không cần đăng ký
- **Thông báo đơn mới** cho chủ quán: trang tự kiểm tra mỗi 7 giây, không cần tải lại
- **Không thu hoa hồng**
- **Thanh toán chuyển khoản VietQR tự động đối soát** qua xAPI, kèm chế độ thủ công khi quán chưa kết nối ngân hàng
- **Gợi ý món hay đặt** dựa trên đơn đã hoàn thành của quán và lịch sử của khách có tài khoản
- **Quản lý mã giảm giá và tính tiền theo bàn** ngay trên trang chủ quán

### 📊 Mức độ ưu tiên

| Mức | Chức năng |
|---|---|
| **Bắt buộc** (làm trước) | Đăng ký, đăng nhập, phân quyền (chủ quán, admin); quản lý bàn và QR; quản lý menu; quét QR, xem menu, giỏ hàng, gửi đơn; xử lý và cập nhật trạng thái đơn; xác nhận thanh toán |
| **Nâng cao** (nếu còn thời gian) | Thống kê doanh thu, mã giảm giá, đánh giá món, tính tiền theo bàn, lịch sử đơn cho khách có tài khoản, trang Admin hoàn chỉnh |
| **Mở rộng** | Thanh toán chuyển khoản VietQR có đối soát tự động (FR-27) — ✅ đã hoàn thành sau Sprint 4 (PR #68, 21/11/2026) |

### ⚙️ Yêu cầu phi chức năng
- Giao diện responsive, ưu tiên điện thoại (khách dùng điện thoại để quét QR)
- Thời gian tải trang dưới 3 giây
- Bảo mật: mã hóa mật khẩu, phân quyền rõ ràng, chống SQL injection, mã bàn (QR) ngẫu nhiên khó đoán
- Xử lý được nhiều bàn gọi món cùng lúc mà không phát sinh lỗi

## 🛠️ Công nghệ sử dụng

| Thành phần | Công nghệ |
|---|---|
| Backend | Python, Flask (API JSON, phiên đăng nhập phía server); mã tách theo nhóm: `app.py`, `admin_api.py`, `complaint_api.py`, `payment_api.py`, `owner_bank_api.py` |
| Frontend | HTML, CSS, JavaScript thuần: các trang tĩnh gọi API bằng `fetch` |
| Cơ sở dữ liệu | SQLite, dùng thư viện `sqlite3` có sẵn của Python (không dùng ORM); cấu trúc bảng trong `schema.sql` |
| Biểu đồ | Chart.js (nạp từ CDN) |
| Mã QR | `qrcode.js` (nạp từ CDN, tạo mã QR ngay trên trình duyệt chủ quán) |
| Gửi email xác nhận | Brevo (API), đọc cấu hình từ biến môi trường hoặc file `.env` (`python-dotenv`) |
| Thanh toán chuyển khoản | VietQR (QR điền sẵn số tiền), xAPI để đối soát giao dịch, thư viện `cryptography` (Fernet) để mã hóa token ngân hàng |
| Kiểm thử | `unittest` (có sẵn trong Python), `node --test` cho logic JavaScript |
| Quản lý mã nguồn | Git, GitHub |
| Quản lý công việc | Trello / GitHub Projects |
| Thiết kế | Figma, draw.io |
| Triển khai | Render (chạy bằng `gunicorn`) hoặc PythonAnywhere |

## 📁 Cấu trúc thư mục

```
CNPM-TULO/
├── QuickOrder/                  # Mã nguồn ứng dụng
│   ├── app.py                   # Flask: API (tài khoản, quán, menu, bàn, đơn hàng, mã giảm giá, đánh giá, lịch sử, doanh thu) và phục vụ trang tĩnh
│   ├── admin_api.py             # API quản trị viên: người dùng, thống kê toàn hệ thống (FR-52, FR-54)
│   ├── complaint_api.py         # API khiếu nại dành cho chủ quán (FR-55)
│   ├── payment_api.py           # API thanh toán chuyển khoản: phiếu, kiểm tra, xác nhận, biên lai, đối soát (FR-27)
│   ├── owner_bank_api.py        # API chủ quán cấu hình ngân hàng nhận tiền, kiểm tra kết nối
│   ├── xapi_client.py           # Gọi xAPI để lấy giao dịch ngân hàng
│   ├── bank_connections.py      # Danh mục ngân hàng, kết nối và mã hóa token
│   ├── bank_catalog.json        # Danh sách ngân hàng hỗ trợ
│   ├── reconcile_payments.py    # Đối soát giao dịch với phiếu thanh toán
│   ├── check_xapi.py            # Kiểm tra kết nối xAPI
│   ├── diagnose_xapi.py         # Chẩn đoán lỗi kết nối xAPI
│   ├── seed_order_local.py      # Tạo đơn thử cục bộ để thử thanh toán
│   ├── schema.sql               # Cấu trúc cơ sở dữ liệu SQLite (21 bảng)
│   ├── init_db.py               # Tạo database trống (và tài khoản admin nếu đặt biến môi trường)
│   ├── seed_data.py             # Nạp dữ liệu mẫu để chạy thử
│   ├── mailer.py                # Gửi mã xác nhận email khi khách đăng ký (Brevo)
│   ├── check_brevo.py           # Kiểm tra cấu hình Brevo, có thể gửi một email thử
│   ├── .env.example             # Mẫu file cấu hình `.env` (khóa Brevo, HTTPS, khóa thanh toán)
│   ├── requirements.txt         # Thư viện Python (flask, gunicorn, python-dotenv, cryptography)
│   ├── index.html               # Trang chủ
│   ├── customer/                # Giao diện khách: menu, giỏ hàng, đơn hàng, lịch sử đơn, tài khoản, hồ sơ
│   ├── merchant/                # Giao diện chủ quán: tổng quan, thông tin quán, menu, bàn và QR, đơn hàng, tính tiền theo bàn, mã giảm giá, đánh giá, khiếu nại, doanh thu
│   ├── admin/                   # Giao diện quản trị: duyệt và khóa quán, người dùng, danh mục, thống kê
│   ├── css/, js/                # Giao diện dùng chung, hàm gọi API (js/app.js, js/admin.js) và thư viện qrcode (js/vendor)
│   └── tests/                   # Kiểm thử tự động (unittest 263 test, Node 26 test)
├── docs/                        # Tài liệu dự án (SRS v1.1, Use Case, ARCHITECTURE, thiết kế, Route/API, thanh toán xAPI, kịch bản demo, hướng dẫn sử dụng...)
├── QuickOrder_TestCase(test by Python + Playwright).xlsx   # Bộ test case tổng hợp (chạy bằng Python và Playwright)
├── sequence_diagram.md          # Sơ đồ tuần tự luồng đặt món và xử lý đơn (Mermaid)
└── README.md
```

## 🚀 Hướng dẫn cài đặt và chạy

### Yêu cầu
- [Python 3.10+](https://www.python.org/downloads/)
- [Git](https://git-scm.com/)

### Các bước

**1. Clone dự án**
```bash
git clone https://github.com/Caykhongg/CNPM-TULO.git
cd CNPM-TULO
```

**2. Tạo và kích hoạt môi trường ảo**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

**3. Cài đặt thư viện**
```bash
cd QuickOrder
pip install -r requirements.txt
```

**4. Tạo cơ sở dữ liệu**

Nạp dữ liệu mẫu để chạy thử (có sẵn quán, menu, bàn và tài khoản demo, xem mục [Tài khoản demo](#-tài-khoản-demo)):
```bash
python seed_data.py --reset
```
Hoặc tạo database trống kèm tài khoản admin (dùng khi triển khai thật):
```bash
# macOS / Linux
ADMIN_EMAIL=admin@quickorder.vn ADMIN_PASSWORD=mat-khau-manh python init_db.py

# Windows (PowerShell)
$env:ADMIN_EMAIL="admin@quickorder.vn"; $env:ADMIN_PASSWORD="mat-khau-manh"; python init_db.py
```
> `--reset` xóa toàn bộ dữ liệu cũ trong `database.db`.

**5. Chạy ứng dụng** (vẫn trong thư mục `QuickOrder/`)
```bash
flask --app app run --debug
```
Truy cập: **http://127.0.0.1:5000**

Khi chạy thật nên đặt `SECRET_KEY` cố định, nếu không mỗi lần khởi động lại mọi người sẽ bị đăng xuất.

### Biến môi trường

| Biến | Ý nghĩa |
|---|---|
| `SECRET_KEY` | Khóa ký phiên đăng nhập; đặt một chuỗi bí mật cố định |
| `HTTPS` | Đặt `1` khi chạy trên HTTPS (Render), để cookie đăng nhập chỉ đi qua HTTPS |
| `QO_DB` | Đường dẫn file database (mặc định `QuickOrder/database.db`) |
| `QO_UPLOADS` | Thư mục lưu ảnh QR thanh toán do chủ quán tải lên (mặc định `QuickOrder/uploads`) |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Dùng với `init_db.py` để tạo tài khoản admin (mật khẩu từ 8 ký tự) |
| `PAYMENT_ENCRYPTION_KEY` | Khóa Fernet dùng mã hóa token ngân hàng của chủ quán. **Bắt buộc giữ cố định** khi dùng thanh toán tự động; mất khóa thì không giải mã được token đã lưu |
| `PAYMENT_RECONCILE_SECRET` | Chuỗi bí mật bảo vệ `POST /api/internal/payments/reconcile` (đối soát từ bên ngoài) |
| `PAYMENT_WORKER` | Mặc định `1`: tác vụ nền đối soát chạy trong server; đặt `0` để tắt |
| `XAPI_SHOP_<id>` | *(Tùy chọn)* Cấu hình xAPI JSON của quán có mã `<id>`, thay cho cấu hình lưu trong CSDL |
| `XAPI_ENDPOINTS_JSON` | *(Tùy chọn)* JSON bổ sung địa chỉ xAPI cho các ngân hàng |
| `FLASK_DEBUG` | Đặt `1` để bật chế độ debug khi chạy `python app.py`; không bật trên máy chủ thật |

> ⚠️ Database và thư mục ảnh tải lên nằm trên ổ đĩa của máy chủ. Nếu nơi triển khai dùng ổ đĩa tạm thời (như gói miễn phí của Render) thì dữ liệu mất khi khởi động lại hoặc triển khai lại; cần gắn ổ đĩa lưu trữ lâu dài và trỏ `QO_DB`, `QO_UPLOADS` vào đó.

### Triển khai thật (Render)

Làm theo thứ tự này khi đưa lên máy chủ thật:

1. **Ổ đĩa lưu trữ:** gắn Persistent Disk (ví dụ mount `/var/data`) rồi đặt `QO_DB=/var/data/database.db` và `QO_UPLOADS=/var/data/uploads`. Không có ổ đĩa thì database, ảnh QR thanh toán và cấu hình ngân hàng của chủ quán mất sau mỗi lần deploy (gói miễn phí của Render dùng ổ đĩa tạm).
2. **Lệnh chạy (Start Command):** `gunicorn app:app --workers 1`. Chỉ dùng một tiến trình vì bộ đếm đăng nhập sai nằm trong bộ nhớ.
3. **Tạo database trống kèm admin**, không chạy `seed_data.py` (tài khoản demo có mật khẩu công khai và dữ liệu giả sẽ lẫn vào số liệu thật):
   ```bash
   ADMIN_EMAIL=<email-that> ADMIN_PASSWORD=<mat-khau-manh> python init_db.py
   ```
4. **Biến môi trường:** `SECRET_KEY` (cố định), `HTTPS=1`, `MAIL_API_KEY`, `MAIL_FROM`, `MAIL_FROM_NAME`, và nếu dùng thanh toán chuyển khoản: `PAYMENT_ENCRYPTION_KEY` (cố định, giữ bí mật), `PAYMENT_RECONCILE_SECRET`. Không đặt `MAIL_CONSOLE` và `FLASK_DEBUG`.
5. **Sao lưu** `database.db` trước mỗi lần triển khai bản mới.
6. **Kiểm tra sau khi deploy:** mở `/api/shops` xem có quán mẫu lọt vào không, thử đăng nhập `admin@quickorder.vn` với `Demo@1234` (phải thất bại), rồi đặt thử một đơn từ mã QR, xử lý đơn và khởi động lại dịch vụ để chắc dữ liệu còn nguyên.

### Chạy kiểm thử
Chạy trong thư mục `QuickOrder/` (không cần cài thêm thư viện ngoài `requirements.txt`):
```bash
python -m unittest discover -s tests -v
```
(`pytest` cũng chạy được các test này.) Kiểm thử dùng CSDL và thư mục ảnh tạm, không gửi email thật. Nếu máy có Node.js, chạy thêm kiểm thử logic trang giỏ hàng, theo dõi đơn: `node --test tests/test_customer_order_pages.cjs` (không cần cài package).

Kết quả lần chạy cuối (bản `main` sau khi hoàn thành FR-27, release v1.1): **263 test Python và 26 test Node, tất cả đạt**.

| File test | Nội dung | Số test |
|---|---|---|
| `test_customer.py` | Đăng ký khách có xác nhận email, hồ sơ khách | 23 |
| `test_mailer.py` | Gửi email xác nhận qua Brevo | 17 |
| `test_orders.py` | Gửi đơn, trạng thái đơn, hủy đơn, thanh toán; giới hạn số lượng 1 đến 99; mã QR đã đổi bị từ chối; chống gửi trùng đơn; nâng cấp CSDL cũ | 50 |
| `test_sprint2_extras.py`, `test_sprint2_review.py` | Bổ sung và rà soát Sprint 2 (ảnh QR thanh toán, giờ mở cửa...) | 9 |
| `test_revenue.py` | Thống kê doanh thu và món bán chạy (FR-47, FR-48) | 9 |
| `test_sprint3.py` | Mã giảm giá, tính tiền theo bàn, đánh giá (FR-23, FR-24, FR-45, FR-46, FR-49) | 18 |
| `test_customer_utilities.py` | Lịch sử đơn, đặt lại món, gợi ý món, khiếu nại của khách (FR-21, FR-22, FR-25, FR-26) | 23 |
| `test_order_history_complaints.py` | Lưu đơn vào lịch sử, khiếu nại do chủ quán xử lý (FR-55) | 14 |
| `test_admin.py` | Khóa/mở khóa quán, người dùng, danh mục, thống kê (FR-51 đến FR-54) | 9 |
| `test_categories.py` | Danh mục dùng chung và danh mục riêng của quán | 19 |
| `test_customer_tracking.py` | Theo dõi đơn và danh sách đơn của khách | 8 |
| `test_xapi_payments.py` | Thanh toán chuyển khoản: phiếu `QO…`, tính giá ở máy chủ, chống trùng biên lai, REVIEW, chế độ thủ công/tự động (FR-27) | 27 |
| `test_owner_bank_connections.py` | Chủ quán cấu hình ngân hàng, mã hóa token, quyền truy cập theo quán | 23 |
| `test_xapi_acb.py` | Đọc và đối soát giao dịch xAPI của ngân hàng ACB | 14 |
| `test_customer_order_pages.cjs` (Node) | Giỏ hàng, theo dõi đơn, danh sách đơn, thanh toán phía trình duyệt; mã chống gửi trùng | 26 |

Ngoài ra, bộ test case tổng hợp (Python và Playwright) nằm ở file `QuickOrder_TestCase(test by Python + Playwright).xlsx` tại thư mục gốc.

### Kiểm tra nhanh các chức năng Sprint 3

Sau khi chạy `python seed_data.py --reset` và mở ứng dụng, có thể thử nhanh như sau (đăng nhập bằng tài khoản ở mục [Tài khoản demo](#-tài-khoản-demo)):

- **Mã giảm giá (FR-46, FR-23):** chủ quán vào **Chủ quán → Mã giảm giá** để tạo, tắt/bật hoặc xóa mã (giảm theo % hoặc số tiền, đơn tối thiểu, thời hạn, số lượt). Khách nhập mã ở **Giỏ hàng**; mã sai, hết hạn, hết lượt hoặc chưa đủ đơn tối thiểu sẽ báo lý do. Hủy đơn thì lượt dùng mã được trả lại.
- **Tính tiền theo bàn (FR-45):** **Chủ quán → Tính tiền bàn** liệt kê các bàn còn đơn chưa trả (không tính đơn đã hủy); bấm thu tiền để đánh dấu đã thanh toán cả bàn hoặc từng đơn.
- **Đánh giá (FR-24, FR-49):** khách đánh giá đơn **Hoàn thành** một lần (điểm 1 đến 5, nhận xét, điểm từng món). Chủ quán xem ở **Chủ quán → Đánh giá**: điểm trung bình, phân bố sao, lọc theo sao.
- **Doanh thu và món bán chạy (FR-47, FR-48):** **Chủ quán → Doanh thu**, chọn Hôm nay, 7 ngày, 30 ngày hoặc Tháng này; chỉ đơn đã hoàn thành được tính, ngày theo giờ Việt Nam.
- **Lịch sử đơn và đặt lại món (FR-21, FR-22):**
  - Khách đăng nhập trước khi đặt: đơn xuất hiện trong **Người dùng → Lịch sử**, kể cả khi đăng nhập ở trình duyệt khác. Bấm **Đặt lại** để dựng lại giỏ; món đã hết hoặc ngừng bán được bỏ qua kèm lý do, giá lấy theo giá hiện tại.
  - Khách đặt trước khi đăng nhập: mở **Lịch sử** trên trình duyệt đã đặt, kiểm tra đơn ở phần “Đơn trên thiết bị chưa lưu vào tài khoản” rồi chọn **Lưu vào lịch sử**. Server kiểm tra mã riêng và chỉ nhận đơn chưa thuộc tài khoản khác; không dựa vào tên hoặc số đơn.
- **Gợi ý món (FR-25):** đầu menu của quán có mục gợi ý món bán chạy; khách có tài khoản thấy thêm món đã gọi từ 2 đơn trở lên ở quán đó.
- **Khiếu nại (FR-26, FR-55):** khách gửi khiếu nại (10 đến 500 ký tự) cho đơn không còn ở trạng thái chờ xác nhận (đơn đang chờ thì hủy đơn thay vì khiếu nại). Chủ quán mở **Chủ quán → Khiếu nại**: xem, lọc trạng thái, phản hồi rồi đóng. Chủ quán khác không đọc hoặc sửa được khiếu nại của quán này. Khách xem phản hồi ở hộp thoại khiếu nại của đơn.
- **Quản trị viên (FR-51 đến FR-54):** đăng nhập tại `/admin/shops.html` (`admin@quickorder.vn`). Các trang: **Quản lý quán** (duyệt, từ chối, khóa, mở khóa), **Người dùng** (`/admin/users.html`), **Danh mục** (`/admin/categories.html`), **Thống kê** (`/admin/dashboard.html`).

**Nâng cấp CSDL đã có dữ liệu:** `init_db()` tự thêm các cột và bảng mới khi khởi động (mã giảm giá, đánh giá, khiếu nại, `user_id` và `request_id` của đơn, `owner_reply`...), và sao chép phản hồi cũ từ `admin_reply` sang `owner_reply` một lần. Không xóa đơn, khiếu nại hoặc phản hồi hiện có. Hãy sao lưu `database.db` trước khi triển khai bản mới.

### Gửi email xác nhận khi khách đăng ký
Khách đăng ký tài khoản sẽ nhận mã 6 số qua email. Đặt các biến môi trường sau trên máy chủ (Render: tab **Environment**), cùng với các biến ở mục trên:

| Biến | Ý nghĩa |
|---|---|
| `MAIL_API_KEY` | Khóa API của Brevo (brevo.com) |
| `MAIL_FROM` | Email người gửi, phải được xác minh trên Brevo |
| `MAIL_FROM_NAME` | Tên người gửi (tùy chọn, mặc định `QuickOrder`) |

Khi thử trên máy chưa có khóa API, đặt `MAIL_CONSOLE=1`: mã xác nhận sẽ in ra terminal thay vì gửi thư. Không bật biến này trên máy chủ thật.


## 🔑 Tài khoản demo

Có sau khi chạy `python seed_data.py --reset` (kèm hơn 150 đơn mẫu trong 15 ngày gần nhất, mã giảm giá, đánh giá và số tài khoản chuyển khoản của 3 quán, để xem ngay danh sách đơn, doanh thu, đánh giá và mã giảm giá). Mật khẩu chung của mọi tài khoản demo: `Demo@1234`. Chỉ dùng để chạy thử, **không dùng trên máy chủ thật**.

Khách hàng không cần tài khoản để gọi món: chỉ cần mở đường dẫn QR của một bàn (chủ quán xem ở trang **Bàn và QR**).

| Vai trò | Email |
|---|---|
| Admin | `admin@quickorder.vn` |
| Chủ quán | `owner1@quickorder.vn` đến `owner6@quickorder.vn` |
| Khách có tài khoản | `khach1@quickorder.vn` đến `khach4@quickorder.vn` |

🔗 **Bản demo trực tuyến:** [https://cnpm-tulo-ii3e.onrender.com/](https://cnpm-tulo-ii3e.onrender.com/)

> Bản demo chạy trên gói miễn phí của Render nên lần mở đầu có thể chậm vài chục giây, và dữ liệu có thể bị đặt lại khi dịch vụ khởi động lại.

## 🔌 Các endpoint API chính

Giao diện là các trang HTML tĩnh gọi API JSON dưới tiền tố `/api` (hàm `QO.api` trong `js/app.js`). Quyền truy cập kiểm tra ở phía server; khách ẩn danh dùng *mã riêng của đơn* (`access_token`, trả về một lần khi gửi đơn) để xem, hủy, đánh giá hoặc khiếu nại đơn của mình. Danh sách đầy đủ có ở mục 9 của [tài liệu Route/API](docs/RouteAPI_QuickOrder_v1.0.docx); API thanh toán chuyển khoản mô tả ở [docs/Thanh_toan_XAPI_QuickOrder.md](docs/Thanh_toan_XAPI_QuickOrder.md).

| Nhóm | Endpoint | Ai dùng |
|---|---|---|
| Tài khoản | `POST /api/register`, `/api/login`, `/api/logout`; `GET, PUT /api/me` | Mọi vai trò |
| Đăng ký khách | `POST /api/customer/signup`, `/api/customer/verify`, `/api/customer/resend` | Khách |
| Quán, bàn, menu | `/api/shops`, `/api/tables`, `/api/categories`, `/api/dishes`, `/api/optionGroups`, `/api/options` (GET, POST, PUT, DELETE); `GET /api/qr/<token>`; `POST /api/shops/<id>/qr` (ảnh QR thanh toán) | Khách (đọc), chủ quán, admin |
| Đơn hàng | `POST /api/orders/quote`, `POST /api/orders`, `GET /api/orders/<id>`, `PUT /api/orders/<id>/cancel`; chủ quán: `GET /api/orders`, `PUT /api/orders/<id>/status`, `PUT /api/orders/<id>/payment` | Khách, chủ quán |
| Mã giảm giá *(Sprint 3)* | `GET, POST /api/coupons`, `PUT, DELETE /api/coupons/<id>` | Chủ quán |
| Tính tiền theo bàn *(Sprint 3)* | `GET /api/shops/<id>/bills`, `POST /api/tables/<id>/settle` | Chủ quán |
| Đánh giá *(Sprint 3)* | `POST /api/orders/<id>/review`; `GET /api/reviews` | Khách; chủ quán |
| Doanh thu *(Sprint 3)* | `GET /api/revenue?shop_id=...&range=today\|7d\|30d\|month` hoặc `from`, `to`; `group=day\|month` | Chủ quán |
| Lịch sử, đặt lại, gợi ý *(Sprint 3)* | `GET /api/my/orders`, `GET /api/my/orders/<id>`, `POST /api/my/orders/<id>/claim`, `POST /api/my/orders/<id>/reorder`; `GET /api/shops/<id>/suggestions` | Khách có tài khoản; gợi ý: mọi người |
| Khiếu nại *(Sprint 3)* | Khách: `POST, GET /api/orders/<id>/complaints`, `GET /api/my/complaints`; chủ quán: `GET /api/merchant/complaints`, `PUT /api/merchant/complaints/<id>/reply`, `PUT /api/merchant/complaints/<id>/close` | Khách; chủ quán |
| Thanh toán chuyển khoản *(FR-27)* | `GET /api/payment-banks`; chủ quán: `PUT, GET /api/shops/<sid>/payment-config`, `POST /api/shops/<sid>/payment-config/test`, `GET /api/shops/<sid>/payment-checkouts`, `POST /api/shops/<sid>/payment-checkouts/<pid>/confirm`, `GET /api/shops/<sid>/payment-receipts`, `PUT /api/shops/<sid>/payment-receipts/<rid>/resolve`; khách: `GET /api/payments/<pid>`, `POST /api/payments/<pid>/check`, `GET /api/payments/mine`; nội bộ: `POST /api/internal/payments/reconcile` (cần `PAYMENT_RECONCILE_SECRET`) | Khách; chủ quán; hệ thống |
| Quản trị *(Sprint 3)* | `GET /api/admin/users`, `PUT /api/admin/users/<id>/status`, `GET /api/admin/statistics`; khóa/mở khóa quán qua `PUT /api/shops/<id>` (trường `status`) | Admin |

Khi gửi đơn (`POST /api/orders`), trình duyệt gửi kèm hai trường:

- `qr_token`: mã QR của bàn. Nếu có, phải khớp mã hiện tại của bàn; quán đã đổi mã thì máy chủ trả 409 và khách phải quét lại (BR-07).
- `client_request_id`: mã ngẫu nhiên (16 đến 64 ký tự) cho mỗi lần đặt. Gửi lại cùng mã (bấm đúp, mạng chập chờn) không tạo đơn thứ hai: máy chủ trả lại đơn đã có kèm đúng mã riêng cũ, và không trừ thêm lượt mã giảm giá (NFR-31).

Số lượng mỗi món từ 1 đến 99 (BR-14). Mọi trường hợp quán không nhận đơn dùng một thông báo: "Quán tạm ngưng nhận món." (BR-06). Hợp đồng API chi tiết của đơn hàng ở [docs/API_QuickOrder_Sprint4.md](docs/API_QuickOrder_Sprint4.md).

## 📚 Tài liệu dự án

Toàn bộ tài liệu nằm trong thư mục [`docs/`](./docs).

| Tài liệu | Trạng thái |
|---|---|
| Danh sách chức năng | ✅ Cập nhật sau Sprint 3: 49/49 chức năng đã Hoàn thành, gồm FR-27 (thanh toán chuyển khoản VietQR) ([xem file](docs/Danh_sach_chuc_nang_QuickOrder.xlsx)) |
| Đặc tả yêu cầu phần mềm (SRS) | ✅ Bản 1.1, cập nhật theo hệ thống đã triển khai ([xem bản 1.1](docs/SRS_QuickOrder_v1.1.docx)); bản gốc 1.0 ([xem file](docs/SRS_QuickOrder_v1.0.docx)) |
| Kiến trúc hệ thống | ✅ Mô tả kiến trúc 3 lớp, thành phần và luồng dữ liệu ([xem file](docs/ARCHITECTURE.md)) |
| Use Case | ✅ Bản 1.0, hoàn thành Sprint 0–1 ([xem file](docs/UseCase_QuickOrder_v1.0.docx)) |
| User Story | ✅ Cập nhật sau Sprint 3: 51/51 story đã Hoàn thành, gồm US-24 (thanh toán chuyển khoản), bản 0.1 ([xem file](docs/UserStory_QuickOrder_v0.1.xlsx)) |
| Thiết kế CSDL (ERD) | ✅ Sơ đồ Mermaid theo `schema.sql` hiện tại, kèm quy ước ràng buộc ([xem file](docs/ERD_QuickOrder.md)) |
| Class Diagram | ✅ Bản 1.0, hoàn thành Sprint 0–1 ([xem file](docs/ClassDiagram_QuickOrder_v1.0.docx)) |
| Sequence Diagram | ✅ Bản 1.0, 9 luồng chính ([xem file](docs/SequenceDiagram_QuickOrder_v1.0.docx)); luồng đặt món theo API thực tế ở [sequence_diagram.md](sequence_diagram.md) |
| Wireframe (Figma) | 🔄 Đã có bản phác thảo 10 màn hình ([xem file](docs/Wireframe_QuickOrder_v1.0.docx)); chờ dựng trên Figma, thêm liên kết Figma khi xong |
| Hợp đồng API đơn hàng (Sprint 4) | ✅ Mô tả đúng những gì code làm; 5 chỗ lệch với SRS đã sửa trong code ([xem file](docs/API_QuickOrder_Sprint4.md)) |
| Báo cáo đo hiệu năng | ✅ Đo 8 và 24 bàn cùng lúc: 0 lỗi, không mất đơn, yêu cầu chậm nhất 412 ms ([xem file](docs/perf/Do_hieu_nang_QuickOrder.md)). Đo ở máy chủ qua localhost, chưa gồm độ trễ mạng của điện thoại |
| Hướng dẫn sử dụng | ✅ Cho khách, chủ quán, quản trị viên ([xem file](docs/Huong_dan_su_dung_QuickOrder.md)) |
| Cấu trúc Route/API | ✅ Bản 1.1 sau Sprint 3: giữ thiết kế ban đầu (mục 1 đến 8) và thêm mục 9 liệt kê API đã triển khai ([xem file](docs/RouteAPI_QuickOrder_v1.0.docx)) |
| Thanh toán chuyển khoản (xAPI, VietQR) | ✅ Cách hoạt động, cấu hình và thử ngân hàng thật ([xem file](docs/Thanh_toan_XAPI_QuickOrder.md)) |
| Kịch bản demo | ✅ Các bước trình diễn khi báo cáo ([xem file](docs/Kich_ban_demo_QuickOrder.md)) |
| Test case và báo cáo kiểm thử | 🔄 Bộ test case tổng hợp Python + Playwright ([xem file](QuickOrder_TestCase(test%20by%20Python%20%2B%20Playwright).xlsx)). Test tự động: 263 test Python và 26 test Node đều đạt (xem mục [Chạy kiểm thử](#chạy-kiểm-thử)), nằm trong `QuickOrder/tests`. Bộ test case thủ công đang được rà soát và bổ sung các ca thanh toán |

## 💳 Thanh toán chuyển khoản

Chủ quán chọn ngân hàng, nhập số tài khoản và token/URL xAPI ngay trên web. Không nhập token thì quán xác nhận thủ công; kết nối xAPI hợp lệ thì máy chủ tự đối soát. QR của mỗi phiếu điền sẵn số tiền và mã riêng; đơn chỉ gửi tới quán sau khi xác nhận thanh toán. Tác vụ nền chạy trong máy chủ, không cần mở lệnh quét riêng.

Xem [hướng dẫn cập nhật thư mục VS Code và thử ngân hàng thật](docs/Thanh_toan_XAPI_QuickOrder.md). Token được mã hóa ở máy chủ, không trả về trình duyệt. Khi nhận tiền thật, CSDL phải được lưu bền vững (ổ đĩa lưu trữ lâu dài) và máy chủ phải duy trì hoạt động.

## 🤝 Quy trình làm việc nhóm

### Quy ước Git
- Nhánh chính: `main` (luôn ổn định, **không commit trực tiếp**).
- Mỗi người làm trên nhánh riêng: `feature/ten-chuc-nang` (ví dụ `feature/gio-hang`).
- Sửa lỗi: `fix/ten-loi`; tài liệu: `docs/ten-tai-lieu`.
- Tạo **Pull Request** và có ít nhất 1 thành viên review trước khi gộp vào `main`.

### Quy ước commit
```
<loại>: <mô tả ngắn>

feat: thêm chức năng thêm món vào giỏ hàng
fix: sửa lỗi tính sai tổng tiền
docs: cập nhật tài liệu SRS
test: thêm test case đăng nhập
refactor: tách hàm tính giá
```

### Quản lý công việc
- Bảng công việc có các cột: **To Do → In Progress → Review → Done**.
- Họp nhóm 1–2 lần mỗi tuần (lập kế hoạch đầu tuần, tổng kết cuối tuần) và ghi biên bản.

## 📅 Kế hoạch thực hiện

| Tuần | Giai đoạn | Nội dung chính |
|---|---|---|
| 1–3 | ✅ **Sprint 0** | Chuẩn bị, phân tích và thiết kế (SRS, Use Case, ERD, wireframe...) |
| 4–5 | ✅ **Sprint 1** | Nền tảng, menu và QR bàn: đăng ký/đăng nhập, phân quyền, quản lý quán, menu, bàn và mã QR, quét QR xem menu |
| 6–7 | ✅ **Sprint 2** | Gọi món và xử lý đơn: giỏ hàng, gửi đơn, thanh toán, thông báo đơn mới, cập nhật trạng thái |
| 8 | ✅ **Sprint 3** | Tính năng nâng cao, hoàn thành 16 chức năng và nâng tổng lên 48/49 chức năng tại thời điểm đó. **Chủ quán:** mã giảm giá (FR-46), tính tiền theo bàn (FR-45), xem đánh giá (FR-49), thống kê doanh thu và món bán chạy (FR-47, FR-48), xử lý khiếu nại thuộc quán mình (FR-55). **Khách:** áp dụng mã giảm giá (FR-23), đánh giá quán và món (FR-24), lịch sử đơn (FR-21), đặt lại món (FR-22), gợi ý món (FR-25), gửi khiếu nại (FR-26). **Quản trị viên:** khóa/mở khóa quán (FR-51), quản lý người dùng (FR-52), quản lý danh mục (FR-53), thống kê toàn hệ thống (FR-54). FR-27 (thanh toán trực tuyến) được làm sau đó ở bước hoàn thiện |
| 9 | ✅ **Sprint 4** | Kiểm thử, đo hiệu năng và sửa lỗi. **Đã làm:** sửa 5 chỗ lệch giữa SRS và code (số lượng mỗi món 1 đến 99, chống gửi trùng đơn ở máy chủ, đơn gửi kèm mã QR bàn để mã đã đổi không đặt được, một thông báo thống nhất khi quán không nhận đơn, báo tên món khi món vừa hết); hợp đồng API đơn hàng; theo dõi đơn của khách; ảnh chụp tùy chọn lúc đặt; đo hiệu năng 8 và 24 bàn; test tăng lên 199 Python và 14 Node (sau này lên 263 và 26); dọn thư mục `QuickOrder/QuickOrder` cũ và gỡ `database.db` khỏi git. **Còn thiếu:** bộ test case thủ công Sprint 3 và báo cáo kiểm thử, được bổ sung ở Sprint 5 |
| 10 | ✅ **Sprint 5 (Hoàn thiện)** | **Hoàn thành FR-27** thanh toán chuyển khoản VietQR với đối soát xAPI, chế độ tự động/thủ công, biên lai và trạng thái REVIEW (PR #68, 21/11/2026), đưa tổng lên **49/49 chức năng** và **51/51 user story**. Tài liệu: README, SRS v1.1, ARCHITECTURE, kịch bản demo, hướng dẫn sử dụng, ERD, tài liệu thanh toán xAPI. Deploy bản demo trên Render. Phát hành **v1.0 (19/11/2026)** và **v1.1 (21/11/2026)**. Test lên 263 Python và 26 Node. **Còn lại:** dựng Figma và thêm link, rà soát bộ test case thủ công, báo cáo, slide |

## 🏷️ Phiên bản phát hành

| Bản | Ngày | Nội dung |
|---|---|---|
| **v1.1** (Latest) | 21/11/2026 | Hoàn thành 49/49 chức năng: thanh toán chuyển khoản VietQR, cấu hình ngân hàng, đối soát xAPI; 263 test Python và 26 test Node |
| **v1.0** | 19/11/2026 | Bản đầy đủ chức năng chính của Sprint 0–4 |

## Đặt và theo dõi đơn của khách

Đặt thành công mở trang `/customer/track.html?id=...`. Trang theo dõi và danh sách đơn cập nhật mỗi 7 giây; khách hủy được khi đơn còn Chờ xác nhận. Có nút Tải lại khi lỗi kết nối và liên kết theo dõi từ Lịch sử tài khoản.

Hướng dẫn thao tác, kiểm thử, file liên quan và hoàn thiện thiết kế Figma: [Luồng đơn hàng khách](docs/Hoan_thien_don_hang_khach.md). Các mẫu SVG để nhập vào Figma nằm trong [docs/figma-don-hang](docs/figma-don-hang/); cần bổ sung link file Figma thật sau khi hoàn thiện.

Kiểm thử logic JavaScript (nếu có Node.js): chạy `node --test tests/test_customer_order_pages.cjs` trong `QuickOrder/`. Kiểm thử Python tiếp tục dùng `python -m unittest discover -s tests -v`.

## 👨‍💻 Thành viên nhóm

| STT | Họ và tên | MSSV | Vai trò |
|---|---|---|---|
| 1 | Nguyễn Xuân Anh | BIT250010 | Trưởng nhóm, BA |
| 2 | Phạm Tuấn Anh | BIT250035 | Frontend khách hàng |
| 3 | Nguyễn Huỳnh Tuấn Anh | BIT250018 | Frontend chủ quán, Admin |
| 4 | Nguyễn Tú Anh | BIT253653 | Backend, Database |
| 5 | Triệu Nguyễn Khải | BIT253659 | Tester, DevOps |

**Giảng viên hướng dẫn:** Ths. Nguyễn Thị Vân Anh

---

<p align="center">Đồ án môn Công nghệ phần mềm – Đại học CMC – Hà Nội, 2026</p>
