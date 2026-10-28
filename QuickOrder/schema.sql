PRAGMA foreign_keys = ON;

-- An toàn khi chạy nhiều lần: KHÔNG xóa dữ liệu cũ.
-- Muốn làm lại từ đầu: python init_db.py --reset

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    phone TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'owner' CHECK (role IN ('customer', 'owner', 'admin')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS shops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    phone TEXT NOT NULL,
    open_time TEXT,
    close_time TEXT,
    bank_account_number TEXT,
    payment_qr_image TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'LOCKED')),
    status_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS shop_tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id INTEGER NOT NULL,
    table_number TEXT NOT NULL COLLATE NOCASE,
    qr_token TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (shop_id) REFERENCES shops(id) ON UPDATE CASCADE ON DELETE CASCADE,
    UNIQUE (shop_id, table_number)
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dishes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    price INTEGER NOT NULL CHECK (price >= 0),
    is_available INTEGER NOT NULL DEFAULT 1 CHECK (is_available IN (0, 1)),
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (shop_id) REFERENCES shops(id) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS option_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dish_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    is_required INTEGER NOT NULL DEFAULT 0 CHECK (is_required IN (0, 1)),
    is_multiple INTEGER NOT NULL DEFAULT 0 CHECK (is_multiple IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (dish_id) REFERENCES dishes(id) ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    extra_price INTEGER NOT NULL DEFAULT 0 CHECK (extra_price >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (group_id) REFERENCES option_groups(id) ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_shops_owner ON shops(owner_id);
CREATE INDEX IF NOT EXISTS idx_tables_shop ON shop_tables(shop_id);
CREATE INDEX IF NOT EXISTS idx_dishes_shop ON dishes(shop_id);
CREATE INDEX IF NOT EXISTS idx_dishes_cat ON dishes(category_id);
CREATE INDEX IF NOT EXISTS idx_groups_dish ON option_groups(dish_id);
CREATE INDEX IF NOT EXISTS idx_options_group ON options(group_id);

INSERT OR IGNORE INTO categories (name) VALUES
    ('Cà phê'), ('Trà'), ('Trà sữa'), ('Đồ ăn'), ('Nước giải khát');


CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id INTEGER NOT NULL,
    table_id INTEGER,
    customer_name TEXT NOT NULL DEFAULT 'Khách tại bàn',
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN (
            'PENDING',
            'CONFIRMED',
            'PREPARING',
            'COMPLETED',
            'CANCELLED'
        )),
    payment_method TEXT NOT NULL DEFAULT 'CASH'
        CHECK (payment_method IN ('CASH', 'TRANSFER')),
    payment_status TEXT NOT NULL DEFAULT 'UNPAID'
        CHECK (payment_status IN ('UNPAID', 'PAID')),
    total_amount INTEGER NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    access_hash TEXT NOT NULL DEFAULT '',          -- băm SHA-256 của mã riêng của đơn (khách dùng để xem và hủy)
    cancel_reason TEXT NOT NULL DEFAULT '',        -- lý do hủy đơn
    coupon_code TEXT NOT NULL DEFAULT '',          -- mã giảm giá đã dùng (rỗng nếu không dùng)
    discount_amount INTEGER NOT NULL DEFAULT 0,    -- số tiền đã giảm; total_amount là số tiền khách phải trả sau giảm
    note TEXT NOT NULL DEFAULT '',
    user_id INTEGER,                               -- tài khoản khách đã đăng nhập lúc gửi đơn (NULL nếu khách ẩn danh); dùng cho lịch sử đơn (FR-21)
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (shop_id) REFERENCES shops(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (table_id) REFERENCES shop_tables(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    dish_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price INTEGER NOT NULL CHECK (unit_price >= 0),
    note TEXT NOT NULL DEFAULT '',
    option_ids TEXT NOT NULL DEFAULT '',           -- id các tùy chọn đã chọn, cách nhau bằng dấu phẩy; dùng để đặt lại món (FR-22)
    FOREIGN KEY (order_id) REFERENCES orders(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (dish_id) REFERENCES dishes(id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_orders_shop
    ON orders(shop_id);

CREATE INDEX IF NOT EXISTS idx_orders_status
    ON orders(status);

CREATE INDEX IF NOT EXISTS idx_order_items_order
    ON order_items(order_id);

-- Đăng ký tài khoản khách đang chờ nhập mã xác nhận email.
-- Chưa tạo dòng trong users cho đến khi nhập đúng mã, nên email chưa xác nhận không chiếm tài khoản.
-- Chỉ lưu hash của mật khẩu và của mã 6 số.
CREATE TABLE IF NOT EXISTS pending_signups (
    email TEXT PRIMARY KEY COLLATE NOCASE,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    expires_at INTEGER NOT NULL,          -- unix time: mã hết hạn lúc nào
    tries INTEGER NOT NULL DEFAULT 0,     -- số lần nhập sai mã hiện tại
    last_sent_at INTEGER NOT NULL,        -- lần gửi mã gần nhất
    window_start INTEGER NOT NULL,        -- đầu cửa sổ 1 giờ đang đếm số lần gửi
    sent_in_window INTEGER NOT NULL DEFAULT 0
);

-- Mã giảm giá của quán (FR-46). Giảm theo phần trăm hoặc số tiền; ngày để trống nghĩa là không giới hạn;
-- max_uses = 0 nghĩa là không giới hạn số lượt. Mã không phân biệt hoa thường và duy nhất trong một quán.
CREATE TABLE IF NOT EXISTS coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id INTEGER NOT NULL,
    code TEXT NOT NULL COLLATE NOCASE,
    discount_type TEXT NOT NULL CHECK (discount_type IN ('PERCENT', 'AMOUNT')),
    discount_value INTEGER NOT NULL CHECK (discount_value > 0),
    min_order INTEGER NOT NULL DEFAULT 0 CHECK (min_order >= 0),
    start_date TEXT NOT NULL DEFAULT '',          -- YYYY-MM-DD (giờ Việt Nam) hoặc rỗng
    end_date TEXT NOT NULL DEFAULT '',            -- YYYY-MM-DD, dùng được hết ngày này
    max_uses INTEGER NOT NULL DEFAULT 0 CHECK (max_uses >= 0),
    used_count INTEGER NOT NULL DEFAULT 0 CHECK (used_count >= 0),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (shop_id, code),
    FOREIGN KEY (shop_id) REFERENCES shops(id)
        ON UPDATE CASCADE ON DELETE CASCADE
);

-- Đánh giá của khách (FR-24): mỗi đơn hoàn thành đánh giá một lần (BR-09).
-- rating là điểm cho quán; review_dishes là điểm riêng cho từng món trong đơn (không bắt buộc).
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL UNIQUE,
    shop_id INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (shop_id) REFERENCES shops(id)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_dishes (
    review_id INTEGER NOT NULL,
    dish_id INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    PRIMARY KEY (review_id, dish_id),
    FOREIGN KEY (review_id) REFERENCES reviews(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (dish_id) REFERENCES dishes(id)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_reviews_shop
    ON reviews(shop_id, id);

CREATE INDEX IF NOT EXISTS idx_review_dishes_dish
    ON review_dishes(dish_id);

-- Tính tiền theo bàn (FR-45) tìm các đơn chưa thanh toán của một bàn.
CREATE INDEX IF NOT EXISTS idx_orders_table_unpaid
    ON orders(table_id, payment_status);

-- Khiếu nại về đơn hàng (FR-26). Khách có tài khoản gửi (user_id) hoặc khách ẩn danh gửi bằng mã riêng của đơn (user_id NULL).
-- Admin xử lý ở FR-55: phản hồi (REPLIED) rồi đóng (CLOSED). Mỗi đơn chỉ có một khiếu nại chưa đóng tại một thời điểm.
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    shop_id INTEGER NOT NULL,
    user_id INTEGER,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'REPLIED', 'CLOSED')),
    admin_reply TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (shop_id) REFERENCES shops(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_complaints_order
    ON complaints(order_id);

CREATE INDEX IF NOT EXISTS idx_complaints_user
    ON complaints(user_id, id);
