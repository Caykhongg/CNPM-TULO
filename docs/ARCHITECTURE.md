# QuickOrder – Kiến trúc sản phẩm

## 1. Tổng quan sản phẩm

QuickOrder là web app gọi món tại bàn cho quán nhỏ. Khách quét mã QR trên bàn, xem menu và gọi món, không cần tài khoản. Chủ quán quản lý quán, thực đơn, bàn/QR và đơn hàng. Quản trị viên duyệt quán.

| Vai trò | Khu vực | Cách vào | Việc chính |
|---|---|---|---|
| Khách (guest) | `customer/` | Quét QR bàn | Xem menu, giỏ hàng, hồ sơ tạm (sessionStorage) |
| Khách có tài khoản | `customer/` | Đăng ký + xác nhận email | Lưu hồ sơ lâu dài, đăng nhập mọi thiết bị |
| Chủ quán (`owner`) | `merchant/` | Đăng ký/đăng nhập | Hồ sơ quán, menu, bàn & QR, đơn, doanh thu |
| Quản trị (`admin`) | `admin/` | Đăng nhập | Duyệt, từ chối, khóa, mở khóa quán |

## 2. Kiến trúc tổng thể

Mô hình 3 lớp, triển khai một khối (monolith) gọn nhẹ: **Web tĩnh nhiều trang → Flask REST API → SQLite**.

```mermaid
flowchart TB
    subgraph Client["Trình duyệt (điện thoại / máy tính)"]
        direction TB
        CU["customer/*.html<br/>home, scan, restaurant, cart,<br/>orders, profile, account"]
        ME["merchant/*.html<br/>login, dashboard, shop, menu,<br/>tables, orders, revenue"]
        AD["admin/shops.html<br/>duyệt quán"]
        JS["js/app.js – module QO<br/>api client · quy tắc nghiệp vụ · header<br/>giỏ hàng + hồ sơ tạm (sessionStorage)"]
        CSS["css/style.css"]
        CU --> JS
        ME --> JS
        AD --> JS
    end

    subgraph Server["Máy chủ: Flask (gunicorn)  –  app.py"]
        direction TB
        STATIC["Phục vụ file tĩnh<br/>(chỉ whitelist: customer/ merchant/ admin/ css/ js/)"]
        AUTH["Xác thực & phiên<br/>/api/register · login · logout · me<br/>cookie ký, HttpOnly, SameSite=Lax"]
        SIGNUP["Đăng ký khách có xác nhận email<br/>/api/customer/signup · verify · resend"]
        CRUD["CRUD chung /api/&lt;name&gt;<br/>shops · tables · categories · dishes<br/>optionGroups · options"]
        QR["/api/qr/&lt;token&gt;<br/>tra bàn + quán"]
        ORD["Đơn hàng /api/orders<br/>tạo · xem · liệt kê · đổi trạng thái · hủy"]
        GUARD["Lớp phân quyền<br/>login_required · shop_scope · item_scope<br/>guard_write · assert_owns · check_values"]
        MAIL["mailer.py"]
        AUTH --- GUARD
        CRUD --- GUARD
        ORD --- GUARD
        SIGNUP --> MAIL
    end

    DB[("SQLite database.db<br/>schema.sql")]
    BREVO["Brevo Email API<br/>(gửi mã 6 số)"]
    EXT1["jsQR (CDN jsdelivr)<br/>đọc QR bằng camera"]
    EXT2["Google Fonts"]

    JS -- "fetch JSON /api/*" --> AUTH
    JS --> CRUD
    JS --> QR
    JS --> SIGNUP
    JS --> ORD
    Client -- "GET trang tĩnh" --> STATIC
    Server --> DB
    MAIL -- "HTTPS" --> BREVO
    CU -.-> EXT1
    Client -.-> EXT2
```

## 3. Các thành phần

### 3.1 Frontend (HTML/CSS/JS thuần, không framework, không bước build)
- **Nhiều trang tĩnh**, mỗi trang tự gọi API qua `QO.api / all / get / by / put / del`.
- **`js/app.js` (module `QO`)** gom: gọi API, quy tắc nghiệp vụ khớp sơ đồ lớp (`isOpenNow` hỗ trợ qua nửa đêm, `isAccepting`, `isOrderable`, `validateSelection`, `qrUrl`), tiện ích (`esc` chống XSS, `money`, `norm` tìm tiếng Việt không dấu), thanh header chung, giỏ hàng và hồ sơ tạm.
- **Trạng thái phía trình duyệt**: giỏ hàng (`qo_cart`) và hồ sơ tạm (`qo_guest`) nằm trong `sessionStorage`, đóng tab là mất. Phiên đăng nhập **không** nằm ở trình duyệt mà là cookie HttpOnly của server.
- **Quét QR**: `scan.html` dùng camera + jsQR, chỉ chấp nhận link cùng origin tới `restaurant.html` có `id` và `table`; có đường dự phòng dán link hoặc mã bàn.

### 3.2 Backend (Flask, một file `app.py`)
| Nhóm | Endpoint | Ghi chú |
|---|---|---|
| Tĩnh | `GET /`, `/<path>` | Whitelist thư mục, chặn `..` |
| Phiên | `POST /api/register` (owner), `/login`, `/logout`, `GET/PUT /api/me` | Khóa đăng nhập 5 lần sai / 15 phút (lưu RAM) |
| Khách | `POST /api/customer/signup`, `/verify`, `/resend` | Mã 6 số, hash, hạn 10 phút, 5 lần sai, gửi lại cách 60 giây, tối đa 5 mã/giờ |
| CRUD | `/api/<name>` GET/POST, `/api/<name>/<id>` GET/PUT/DELETE | `users` không mở qua CRUD |
| QR | `GET /api/qr/<token>` | Trả bàn + quán để kiểm tra trước khi gọi món |
| Đơn | `POST/GET /api/orders`, `GET /api/orders/<id>`, `PUT .../status`, `PUT .../cancel` | Backend đã có, giao diện chưa nối |

- **`mailer.py`**: gửi mã qua API Brevo; `MAIL_CONSOLE=1` để in mã ra terminal khi dev; lỗi gửi trả 502.
- **`init_db.py`**: tạo DB từ `schema.sql`, tạo admin từ biến môi trường. **`seed_data.py`**: nạp dữ liệu mẫu.

### 3.3 Phân quyền (điểm mấu chốt của kiến trúc)
```mermaid
flowchart LR
    REQ["Request /api/*"] --> S{"Có phiên?<br/>session.uid"}
    S -- "Không" --> G["Khách vãng lai"]
    S -- "Có" --> R{"role"}
    R -- "customer" --> C["Chỉ thấy quán APPROVED<br/>Sửa hồ sơ của mình"]
    R -- "owner" --> O["Thấy quán của mình + quán APPROVED<br/>Ghi: chỉ dữ liệu thuộc quán mình<br/>Không tự đổi status/owner_id"]
    R -- "admin" --> A["Thấy và ghi tất cả<br/>Đổi trạng thái quán"]
    G --> GV["Chỉ thấy quán APPROVED<br/>Món chưa xóa mềm"]
```
- `shop_scope` / `item_scope`: lọc dữ liệu hiển thị theo vai trò (BR-06).
- `guard_write`: quán mới luôn `PENDING` và thuộc người tạo; không gắn bản ghi vào quán/món/nhóm của người khác; quán `REJECTED` được sửa là tự gửi lại duyệt.
- `qr_token` luôn do server sinh; "Đổi mã" làm mã cũ vô hiệu ngay (BR-07).

## 4. Mô hình dữ liệu

```mermaid
erDiagram
    users ||--o{ shops : "owner_id"
    shops ||--o{ shop_tables : "shop_id"
    shops ||--o{ dishes : "shop_id"
    categories ||--o{ dishes : "category_id"
    dishes ||--o{ option_groups : "dish_id"
    option_groups ||--o{ options : "group_id"
    shops ||--o{ orders : "shop_id"
    shop_tables ||--o{ orders : "table_id"
    orders ||--|{ order_items : "order_id"
    dishes ||--o{ order_items : "dish_id"

    users { int id PK
        text email UK
        text role "customer|owner|admin"
        int is_active }
    shops { int id PK
        int owner_id FK
        text status "PENDING|APPROVED|REJECTED|LOCKED"
        text open_time
        text close_time
        text bank_account_number
        text payment_qr_image }
    shop_tables { int id PK
        text table_number
        text qr_token UK }
    dishes { int id PK
        int price
        int is_available
        int is_deleted "xóa mềm" }
    option_groups { int id PK
        int is_required
        int is_multiple }
    options { int id PK
        int extra_price }
    orders { int id PK
        text status "PENDING|CONFIRMED|PREPARING|COMPLETED|CANCELLED"
        text payment_method "CASH|TRANSFER"
        text payment_status
        int total_amount }
    order_items { int id PK
        int quantity
        int unit_price }
    pending_signups { text email PK
        text code_hash
        int expires_at
        int tries
        int sent_in_window }
```
`pending_signups` đứng riêng: email chưa xác nhận chưa chiếm tài khoản trong `users`; chỉ lưu hash mật khẩu và hash mã.

## 5. Luồng chính

### 5.1 Khách đăng ký có xác nhận email
```mermaid
sequenceDiagram
    actor K as Khách
    participant W as account.html
    participant A as Flask API
    participant D as SQLite
    participant B as Brevo
    K->>W: Nhập họ tên, sđt, email, mật khẩu
    W->>A: POST /customer/signup
    A->>D: Email đã có user? (nếu có: vẫn trả cùng thông báo)
    A->>D: Lưu pending_signups (hash mật khẩu, hash mã)
    A->>B: Gửi mã 6 số
    A-->>W: SENT_MSG
    K->>W: Nhập mã
    W->>A: POST /customer/verify
    A->>D: Kiểm tra hạn, số lần sai, hash mã
    A->>D: INSERT users (customer), xóa pending
    A-->>W: 201 + cookie phiên
```

### 5.2 Khách quét QR và đặt món
```mermaid
sequenceDiagram
    actor K as Khách
    participant S as scan.html
    participant R as restaurant.html
    participant A as Flask API
    K->>S: Quét QR (jsQR)
    S->>R: restaurant.html?id=..&table=<token>
    R->>A: GET /api/qr/<token>
    A-->>R: bàn + quán (kiểm tra token thuộc đúng quán)
    R->>A: GET dishes, categories, optionGroups, options
    K->>R: Chọn món, tùy chọn (size, topping)
    R->>R: Lưu giỏ vào sessionStorage
    K->>A: POST /api/orders (cart.html – hiện đang khóa nút)
    A-->>K: Đơn PENDING
```

### 5.3 Vòng đời quán và đơn
```mermaid
stateDiagram-v2
    direction LR
    [*] --> PENDING: Chủ quán tạo quán
    PENDING --> APPROVED: Admin duyệt
    PENDING --> REJECTED: Admin từ chối
    REJECTED --> PENDING: Chủ quán sửa rồi lưu
    APPROVED --> LOCKED: Admin khóa
    LOCKED --> APPROVED: Admin mở khóa
```
```mermaid
stateDiagram-v2
    direction LR
    [*] --> PENDING
    PENDING --> CONFIRMED
    CONFIRMED --> PREPARING
    PREPARING --> COMPLETED
    PENDING --> CANCELLED: khách hoặc quán hủy
    CONFIRMED --> CANCELLED
    PREPARING --> CANCELLED
```

## 6. Triển khai và cấu hình
- Chạy dev: `python app.py`. Chạy thật: `gunicorn app:app` (đã có trong `requirements.txt`).
- Biến môi trường: `SECRET_KEY`, `QO_DB`, `HTTPS=1` (cookie Secure), `FLASK_DEBUG`, `MAIL_API_KEY`, `MAIL_FROM`, `MAIL_FROM_NAME`, `MAIL_CONSOLE`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`.
- Kiểm thử: `python -m unittest discover -s tests -v`.
- Lưu ý khi nâng cấp CSDL cũ: `init_db()` chạy `schema.sql` mỗi lần khởi động nên bảng mới (như `pending_signups`) tự được thêm.

## 7. Trạng thái hiện tại và điểm cần lưu ý

**Đã hoàn thiện:** đăng ký/đăng nhập 3 vai trò, xác nhận email, duyệt quán, menu + tùy chọn, bàn + QR + đổi mã, quét QR, giỏ hàng, hồ sơ khách.

**Chưa nối giao diện:** đặt hàng (`cart.html`), đơn của khách, đơn của chủ quán, dashboard đơn, doanh thu (backend đơn đã có, UI còn placeholder).

**Rủi ro/khoảng trống nên xử lý trước khi mở đơn hàng:**
1. `GET /api/orders/<id>` và `PUT /api/orders/<id>/cancel` chưa kiểm tra quyền, ai biết id đều xem và hủy được. Nên gắn token đơn hoặc kiểm tra quyền.
2. `POST /api/orders` chưa tính `extra_price` của tùy chọn và chưa lưu tùy chọn đã chọn vào `order_items` (chỉ có cột `note`), nên tổng tiền sẽ lệch so với giỏ hàng.
3. `create_order` chưa kiểm tra quán có đang trong giờ mở cửa, chưa xác thực `qr_token` của bàn.
4. UI đang có trạng thái "Đang giao" nhưng schema và API không có (`ORDER_STATUSES` chỉ 5 trạng thái); SRS chỉ phục vụ tại bàn nên nên bỏ khỏi UI.
5. Bộ đếm đăng nhập sai (`LOGIN_FAILS`) nằm trong RAM: mất khi restart, và không dùng chung nếu chạy nhiều worker gunicorn.
6. `/api/register` (chủ quán) và `/api/login` chưa có giới hạn tốc độ; `GET /api/<name>` cho phép lọc theo mọi cột, nên cân nhắc whitelist.
7. SQLite phù hợp quy mô nhỏ; khi nhiều quán/nhiều worker, cân nhắc chuyển PostgreSQL.
