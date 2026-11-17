# Thiết kế cơ sở dữ liệu (ERD) QuickOrder

Sơ đồ này vẽ đúng theo `QuickOrder/schema.sql` (SQLite) ở thời điểm hoàn thành Sprint 4, kèm các cột bổ sung trong `init_db()` của `app.py` cho CSDL cũ. Mở bằng GitHub, VS Code (có Mermaid) hoặc [mermaid.live](https://mermaid.live).

## Sơ đồ quan hệ

```mermaid
erDiagram
    users ||--o{ shops : "sở hữu (owner_id)"
    users ||--o{ orders : "lịch sử đơn (user_id, có thể NULL)"
    users ||--o{ complaints : "gửi (user_id, có thể NULL)"
    shops ||--o{ shop_tables : "có bàn"
    shops ||--o{ categories : "danh mục riêng (shop_id, NULL là danh mục chung)"
    shops ||--o{ dishes : "bán"
    shops ||--o{ orders : "nhận"
    shops ||--o{ coupons : "phát hành"
    shops ||--o{ reviews : "được đánh giá"
    shops ||--o{ complaints : "nhận khiếu nại"
    categories ||--o{ dishes : "phân loại"
    dishes ||--o{ option_groups : "có nhóm tùy chọn"
    option_groups ||--o{ options : "gồm"
    shop_tables ||--o{ orders : "đặt tại bàn (table_id, có thể NULL)"
    orders ||--|{ order_items : "gồm dòng món"
    dishes ||--o{ order_items : "được gọi"
    order_items ||--o{ order_item_options : "ảnh chụp tùy chọn lúc đặt"
    options ||--o{ order_item_options : "tham chiếu (option_id, NULL khi tùy chọn bị xóa)"
    orders ||--o| reviews : "đánh giá một lần"
    reviews ||--o{ review_dishes : "điểm từng món"
    dishes ||--o{ review_dishes : "được chấm"
    orders ||--o{ complaints : "bị khiếu nại"

    users {
        int id PK
        text full_name
        text email UK
        text phone
        text password_hash
        text role "customer | owner | admin"
        int is_active
        text created_at
    }
    shops {
        int id PK
        int owner_id FK
        text name
        text address
        text phone
        text open_time
        text close_time
        text bank_account_number
        text payment_qr_image
        text status "PENDING | APPROVED | REJECTED | LOCKED"
        text status_note
    }
    shop_tables {
        int id PK
        int shop_id FK
        text table_number "duy nhất trong quán"
        text qr_token UK
    }
    categories {
        int id PK
        int shop_id FK "NULL: danh mục chung"
        text name
    }
    dishes {
        int id PK
        int shop_id FK
        int category_id FK
        text name
        int price
        int is_available
        int is_deleted "xóa mềm"
    }
    option_groups {
        int id PK
        int dish_id FK
        text name
        int is_required
        int is_multiple
    }
    options {
        int id PK
        int group_id FK
        text name
        int extra_price
    }
    orders {
        int id PK
        int shop_id FK
        int table_id FK
        int user_id FK
        text customer_name
        text status "PENDING | CONFIRMED | PREPARING | COMPLETED | CANCELLED"
        text payment_method "CASH | TRANSFER"
        text payment_status "UNPAID | PAID"
        int total_amount "sau giảm giá"
        int discount_amount
        text coupon_code
        text access_hash "băm mã riêng của đơn"
        text request_id UK "mã chống gửi trùng"
        text cancel_reason
        text note
        text created_at "UTC"
    }
    order_items {
        int id PK
        int order_id FK
        int dish_id FK
        int quantity
        int unit_price "đã gồm phụ thu tùy chọn"
        text note
        text option_ids
    }
    order_item_options {
        int id PK
        int order_item_id FK
        int option_id FK
        text option_name
        int extra_price
        text group_name
    }
    coupons {
        int id PK
        int shop_id FK
        text code "duy nhất trong quán"
        text discount_type "PERCENT | AMOUNT"
        int discount_value
        int min_order
        text start_date
        text end_date
        int max_uses "0: không giới hạn"
        int used_count
        int is_active
    }
    reviews {
        int id PK
        int order_id FK "UNIQUE"
        int shop_id FK
        int rating "1 đến 5"
        text comment
    }
    review_dishes {
        int review_id PK
        int dish_id PK
        int rating "1 đến 5"
    }
    complaints {
        int id PK
        int order_id FK
        int shop_id FK
        int user_id FK
        text content
        text status "OPEN | REPLIED | CLOSED"
        text owner_reply
    }
    pending_signups {
        text email PK
        text full_name
        text phone
        text password_hash
        text code_hash "băm mã 6 số"
        int expires_at
        int tries
        int last_sent_at
        int window_start
        int sent_in_window
    }
```

`pending_signups` đứng riêng: đăng ký khách chờ xác nhận email, chỉ thành dòng trong `users` khi nhập đúng mã.

## Quy ước và ràng buộc đáng chú ý

| Nội dung | Cách thiết kế |
|---|---|
| Khóa ngoại | Bật bằng `PRAGMA foreign_keys = ON` ở mọi kết nối |
| Xóa quán | Xóa bàn, danh mục riêng, món, đơn, mã giảm giá, đánh giá, khiếu nại của quán (`ON DELETE CASCADE`). Chủ quán không xóa được quán, chỉ admin |
| Xóa chủ quán | Bị chặn (`ON DELETE RESTRICT`) khi còn quán |
| Xóa món | Xóa mềm (`is_deleted`) để đơn cũ vẫn giữ tên món; `order_items.dish_id` là `RESTRICT` |
| Xóa bàn | Đơn cũ giữ lại, `table_id` thành NULL |
| Xóa tài khoản khách | `user_id` của đơn và khiếu nại thành NULL |
| Giá | Chốt lúc đặt: `unit_price` gồm giá món cộng phụ thu; `order_item_options` lưu tên và giá thêm, sửa menu sau đó không đổi đơn cũ (BR-04) |
| Mã riêng của đơn | Chỉ lưu băm SHA-256 (`access_hash`); mã gốc trả về một lần |
| Mã chống gửi trùng | `request_id` có chỉ mục duy nhất (NULL không bị tính trùng), mỗi mã chỉ tạo một đơn |
| Mã QR bàn | `qr_token` duy nhất, sinh ngẫu nhiên ở máy chủ; đổi mã thì mã cũ vô hiệu |
| Mật khẩu và mã xác nhận | Chỉ lưu băm (`password_hash`, `code_hash`) |
| Thời gian | Lưu UTC; thống kê theo ngày tính theo giờ Việt Nam (UTC+7) |
| Danh mục | Tên không phân biệt hoa thường, duy nhất trong phạm vi (chung hoặc theo quán) |
| Chỉ mục | `orders(shop_id)`, `orders(status)`, `orders(user_id, id)`, `orders(table_id, payment_status)`, `orders(request_id)` duy nhất, `reviews(shop_id, id)`, `complaints(shop_id, status, id)` và các chỉ mục khóa ngoại khác |
