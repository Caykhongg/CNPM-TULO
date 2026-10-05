# 🍵 QuickOrder – Ứng dụng đặt món cho quán nhỏ

> Đồ án cuối kỳ môn **Công nghệ phần mềm** – Khoa Công nghệ Thông tin và Truyền thông, Đại học CMC
> Nhóm thực hiện: **Nhóm TULO**

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5-purple)
![Status](https://img.shields.io/badge/Status-Đang%20phát%20triển-orange)

---

## 📌 Mục lục

1. [Giới thiệu](#-giới-thiệu)
2. [Vấn đề và giải pháp](#-vấn-đề-và-giải-pháp)
3. [Đối tượng người dùng](#-đối-tượng-người-dùng)
4. [Chức năng chính](#-chức-năng-chính)
5. [Công nghệ sử dụng](#-công-nghệ-sử-dụng)
6. [Cấu trúc thư mục](#-cấu-trúc-thư-mục)
7. [Hướng dẫn cài đặt và chạy](#-hướng-dẫn-cài-đặt-và-chạy)
8. [Tài khoản demo](#-tài-khoản-demo)
9. [Tài liệu dự án](#-tài-liệu-dự-án)
10. [Quy trình làm việc nhóm](#-quy-trình-làm-việc-nhóm)
11. [Kế hoạch thực hiện](#-kế-hoạch-thực-hiện)
12. [Thành viên nhóm](#-thành-viên-nhóm)

---

## 📖 Giới thiệu

**QuickOrder** là ứng dụng web giúp các quán ăn, quán nước quy mô nhỏ (trà sữa, cà phê, cơm, bún phở) nhận và quản lý đơn hàng trực tuyến.

- Mỗi quán có **một trang menu riêng**, khách hàng đặt món trực tiếp.
- Chủ quán **xử lý đơn và theo dõi doanh thu** ngay trên hệ thống.
- **Không thu phí hoa hồng** cho nền tảng trung gian.

## 🎯 Vấn đề và giải pháp

**Vấn đề:** các quán nhỏ hiện nhận đơn chủ yếu qua điện thoại, Zalo hoặc ghi tay, dẫn đến:

- Dễ nhầm đơn, sót món, khó theo dõi trạng thái đơn hàng.
- Khách phải chờ quán trả lời mới biết món còn hay hết.
- Chủ quán không có số liệu doanh thu, món bán chạy để ra quyết định.
- Các nền tảng lớn (GrabFood, ShopeeFood) thu hoa hồng cao, quán nhỏ khó chịu nổi.

**Giải pháp:** hệ thống đặt món trực tuyến gồm ba phân hệ **Khách hàng – Chủ quán – Quản trị viên**.

## 👥 Đối tượng người dùng

| Vai trò | Mục tiêu sử dụng |
|---|---|
| **Khách hàng** | Xem menu, đặt món nhanh, theo dõi đơn, xem lịch sử và đánh giá |
| **Chủ quán / nhân viên** | Nhận đơn, cập nhật trạng thái, quản lý menu và khuyến mãi, xem thống kê |
| **Quản trị viên (Admin)** | Duyệt và khóa quán, quản lý người dùng, xem thống kê chung, xử lý khiếu nại |

## ✨ Chức năng chính

### 🛒 Phân hệ khách hàng
- Đăng ký, đăng nhập, quản lý thông tin cá nhân và địa chỉ giao hàng
- Xem danh sách quán, tìm kiếm, lọc theo loại món
- Xem menu, chọn món kèm tùy chọn (size, topping, ghi chú)
- Quản lý giỏ hàng, đặt hàng giao tận nơi hoặc tự đến lấy
- Thanh toán bằng tiền mặt hoặc chuyển khoản/QR
- Theo dõi trạng thái đơn: *Chờ xác nhận → Đang làm → Đang giao → Hoàn thành*
- Xem lịch sử đơn, đặt lại đơn cũ, đánh giá quán và món

### 🏪 Phân hệ chủ quán
- Quản lý thông tin quán và giờ mở cửa
- Quản lý menu: thêm, sửa, xóa món, hình ảnh, giá, đánh dấu hết món
- Nhận đơn mới, xác nhận hoặc từ chối, cập nhật trạng thái đơn
- Quản lý mã giảm giá và khuyến mãi
- Thống kê doanh thu theo ngày, tháng và món bán chạy

### 🛡️ Phân hệ quản trị viên
- Duyệt hoặc khóa tài khoản quán
- Quản lý người dùng và danh mục món
- Thống kê toàn hệ thống, xử lý khiếu nại

### 🚀 Điểm nổi bật
- **Đặt tại bàn bằng QR:** mỗi bàn có mã QR, khách quét mã, chọn món và gửi thẳng đến quầy bếp
- **Thông báo đơn mới** cho chủ quán
- **Không thu hoa hồng**
- **Gợi ý món hay đặt** dựa trên lịch sử đặt hàng

### 📊 Mức độ ưu tiên

| Mức | Chức năng |
|---|---|
| **Bắt buộc** (làm trước) | Đăng ký, đăng nhập, phân quyền; quản lý menu; xem menu, giỏ hàng, đặt hàng; quản lý và cập nhật trạng thái đơn; lịch sử đơn |
| **Nâng cao** (nếu còn thời gian) | Thống kê doanh thu, mã giảm giá, đánh giá món, QR đặt tại bàn, thanh toán trực tuyến |

### ⚙️ Yêu cầu phi chức năng
- Giao diện responsive, dùng tốt trên điện thoại
- Thời gian tải trang dưới 3 giây
- Bảo mật: mã hóa mật khẩu, phân quyền rõ ràng, chống SQL injection
- Xử lý được nhiều người đặt món cùng lúc mà không phát sinh lỗi

## 🛠️ Công nghệ sử dụng

| Thành phần | Công nghệ |
|---|---|
| Backend | Python, Flask |
| Frontend | HTML, CSS, Bootstrap 5, JavaScript |
| Template engine | Jinja2 |
| Cơ sở dữ liệu | SQLite (có thể nâng lên MySQL) |
| ORM | SQLAlchemy |
| Biểu đồ | Chart.js |
| Mã QR | Thư viện `qrcode` |
| Quản lý mã nguồn | Git, GitHub |
| Quản lý công việc | Trello / GitHub Projects |
| Thiết kế | Figma, draw.io |
| Triển khai | PythonAnywhere / Render |

## 📁 Cấu trúc thư mục

> ⚠️ Cấu trúc dưới đây là bản dự kiến, sẽ được cập nhật khi dự án phát triển.

```
quickorder.app/
│
├── public/                     # Tài nguyên tĩnh
│   ├── favicon.ico
│   └── assets/
│       ├── icons/              # SVG icons (home, cart, user, merchant, etc.)
│       └── images/             # Hình ảnh logo, banner, món ăn mặc định
│
├── src/                        # Mã nguồn chính của dự án
│   ├── assets/                 # CSS/Tailwind styles
│   │   └── main.css            # Styles toàn cục & custom utilities
│   │
│   ├── components/             # Các Component tái sử dụng
│   │   ├── common/             # Component dùng chung cho cả 2 role
│   │   │   ├── Header.js / .jsx
│   │   │   ├── BottomNav.js / .jsx
│   │   │   ├── Modal.js / .jsx
│   │   │   └── SearchBar.js / .jsx
│   │   │
│   │   ├── customer/           # Component riêng cho Người dùng
│   │   │   ├── CategoryList.js
│   │   │   ├── RestaurantCard.js
│   │   │   ├── MenuItemCard.js
│   │   │   ├── CartDrawer.js
│   │   │   └── OrderTracker.js
│   │   │
│   │   └── merchant/           # Component riêng cho Chủ quán
│   │       ├── StatCard.js
│   │       ├── OrderStatusBadge.js
│   │       ├── MerchantOrderItem.js
│   │       ├── MenuManageItem.js
│   │       └── RevenueChart.js
│   │
│   ├── pages/                  # Các Màn hình (Screens) theo đúng UI thiết kế
│   │   ├── customer/           # 7 Màn hình Người dùng
│   │   │   ├── WelcomeScreen.js        # 1. Màn hình chào mừng
│   │   │   ├── HomeScreen.js           # 2. Trang chủ
│   │   │   ├── SearchScreen.js         # 3. Kết quả tìm kiếm
│   │   │   ├── RestaurantDetailScreen.js # 4. Chi tiết & thực đơn
│   │   │   ├── CartScreen.js           # 5. Giỏ hàng & Thanh toán
│   │   │   ├── OrderTrackingScreen.js  # 6. Theo dõi đơn hàng
│   │   │   └── ProfileScreen.js        # 7. Hồ sơ cá nhân
│   │   │
│   │   └── merchant/           # 6 Màn hình Chủ quán
│   │       ├── LoginScreen.js          # 1. Đăng nhập
│   │       ├── DashboardScreen.js      # 2. Trang chủ (Dashboard)
│   │       ├── MenuManageScreen.js     # 3. Quản lý thực đơn
│   │       ├── OrderManageScreen.js    # 4. Quản lý đơn hàng
│   │       ├── RevenueScreen.js        # 5. Thống kê doanh thu
│   │       └── MerchantProfileScreen.js# 6. Tài khoản chủ quán
│   │
│   ├── services/               # Kết nối API Backend & Database
│   │   ├── api.config.js       # Cấu hình Axios / Fetch Base URL
│   │   ├── auth.service.js     # API Đăng nhập, Đăng ký, Token
│   │   ├── restaurant.service.js # API Quán ăn & Món ăn
│   │   ├── order.service.js    # API Đặt hàng & Cập nhật trạng thái
│   │   └── merchant.service.js # API Doanh thu & Quản lý thực đơn
│   │
│   ├── context/                # Quản lý State toàn cục (State Management)
│   │   ├── AuthContext.js      # Lưu thông tin user/merchant đã đăng nhập
│   │   ├── CartContext.js      # Lưu giỏ hàng, tính tổng tiền
│   │   └── RoleContext.js      # Chuyển đổi giữa Customer / Merchant
│   │
│   ├── utils/                  # Hàm tiện ích dùng chung
│   │   ├── formatCurrency.js   # Format tiền tệ (VD: 55.000đ)
│   │   ├── formatDate.js       # Format ngày tháng/thời gian
│   │   └── constants.js        # Khai báo hằng số (Trạng thái đơn, Roles)
│   │
│   ├── App.js                  # Component điều hướng chính (Router)
│   └── index.js                # Entry point
│
├── .env                        # Biến môi trường (URL API, Keys)
├── package.json                # Dependencies & Scripts
└── README.md                   # Hướng dẫn chạy dự án
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
pip install -r requirements.txt
```

**4. Tạo file cấu hình**
```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```
Mở file `.env` và chỉnh các giá trị cần thiết:
```
SECRET_KEY=doi-thanh-chuoi-bi-mat-cua-ban
DATABASE_URL=sqlite:///quickorder.db
```

**5. Khởi tạo cơ sở dữ liệu và dữ liệu mẫu**
```bash
python init_db.py
```

**6. Chạy ứng dụng**
```bash
flask --app run run --debug
```
Truy cập: **http://127.0.0.1:5000**

### Chạy kiểm thử
```bash
pytest
```

> 📝 *Các lệnh ở bước 5 và 6 sẽ được TV4 (Backend) xác nhận lại khi hoàn tất khung dự án.*

## 🔑 Tài khoản demo

> Sẽ cập nhật sau khi có dữ liệu mẫu.

| Vai trò | Email | Mật khẩu |
|---|---|---|
| Admin | `admin@quickorder.vn` | `...` |
| Chủ quán | `owner@quickorder.vn` | `...` |
| Khách hàng | `customer@quickorder.vn` | `...` |

🔗 **Bản demo trực tuyến:** *(cập nhật sau khi deploy)*

## 📚 Tài liệu dự án

Toàn bộ tài liệu nằm trong thư mục [`docs/`](./docs).

| Tài liệu | Trạng thái |
|---|---|
| Danh sách chức năng | ⬜ Chưa làm |
| Đặc tả yêu cầu phần mềm (SRS) | ⬜ Chưa làm |
| Use Case | ⬜ Chưa làm |
| User Story | ⬜ Chưa làm |
| Thiết kế CSDL (ERD) | ⬜ Chưa làm |
| Class Diagram | ⬜ Chưa làm |
| Sequence Diagram | ⬜ Chưa làm |
| Wireframe (Figma) | ⬜ Chưa làm |
| Cấu trúc Route/API | ⬜ Chưa làm |
| Test case và báo cáo kiểm thử | ⬜ Chưa làm |

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
| 1–3 | **Sprint 0** | Chuẩn bị, phân tích và thiết kế (SRS, Use Case, ERD, wireframe...) |
| 4–5 | **Sprint 1** | Nền tảng và Menu: đăng ký/đăng nhập, phân quyền, quản lý menu |
| 6–7 | **Sprint 2** | Đặt hàng và xử lý đơn: giỏ hàng, đặt món, cập nhật trạng thái |
| 8 | **Sprint 3** | Tính năng nâng cao: thống kê, mã giảm giá, đánh giá, QR, trang Admin |
| 9 | **Sprint 4** | Kiểm thử tổng thể, đo hiệu năng, sửa lỗi |
| 10 | Hoàn thiện | Deploy, tài liệu hướng dẫn, báo cáo, slide, demo |

## 👨‍💻 Thành viên nhóm

| STT | Họ và tên | MSSV | Vai trò |
|---|---|---|---|
| 1 | Nguyễn Xuân Anh | BIT250010 | Trưởng nhóm, BA |
| 2 | Phạm Tuấn Anh | BIT250035 | Frontend khách hàng |
| 3 | Nguyễn Huỳnh Tuấn Anh | BIT250018 | Frontend chủ quán, Admin |
| 4 | Nguyễn Tú Anh | BIT253653 | Backend, Database |
| 5 | Triệu Nguyễn Khải | BIT253659 | Tester, DevOps |

**Giảng viên hướng dẫn:** *(điền tên)*

---

<p align="center">Đồ án môn Công nghệ phần mềm – Đại học CMC – Hà Nội, 2026</p>
