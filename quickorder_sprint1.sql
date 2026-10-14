-- QuickOrder - Database Sprint 1
-- Target: SQLite 3 / Flask-SQLAlchemy compatible
-- Scope: tài khoản, phân quyền, quán, duyệt quán, bàn/QR, danh mục, món, menu QR

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

DROP TABLE IF EXISTS dishes;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS restaurant_tables;
DROP TABLE IF EXISTS restaurants;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    phone TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('customer', 'owner', 'admin')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'locked')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE restaurants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    phone TEXT NOT NULL,
    image_url TEXT,
    open_time TEXT,
    close_time TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'locked')),
    rejection_reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE restaurant_tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL,
    table_number INTEGER NOT NULL CHECK (table_number > 0),
    qr_token TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (restaurant_id) REFERENCES restaurants(id) ON UPDATE CASCADE ON DELETE CASCADE,
    UNIQUE (restaurant_id, table_number)
);

CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE dishes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    price INTEGER NOT NULL CHECK (price >= 0),
    image_url TEXT,
    is_available INTEGER NOT NULL DEFAULT 1 CHECK (is_available IN (0, 1)),
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (restaurant_id) REFERENCES restaurants(id) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX idx_restaurants_owner_id ON restaurants(owner_id);
CREATE INDEX idx_restaurants_status ON restaurants(status);
CREATE INDEX idx_tables_restaurant_id ON restaurant_tables(restaurant_id);
CREATE INDEX idx_dishes_restaurant_id ON dishes(restaurant_id);
CREATE INDEX idx_dishes_category_id ON dishes(category_id);
CREATE INDEX idx_dishes_visible ON dishes(restaurant_id, is_deleted, is_available);

-- Dữ liệu danh mục mẫu cho Sprint 1.
INSERT INTO categories (name, description) VALUES
    ('Cà phê', 'Các loại cà phê'),
    ('Trà', 'Các loại trà'),
    ('Trà sữa', 'Các loại trà sữa'),
    ('Đồ ăn', 'Các món ăn nhẹ'),
    ('Nước giải khát', 'Nước đóng chai và nước giải khát');

COMMIT;

-- Ghi chú tích hợp Flask:
-- 1. password_hash phải được tạo bằng generate_password_hash() của Werkzeug.
-- 2. Không lưu mật khẩu dạng rõ.
-- 3. Chủ quán chỉ được truy cập restaurant có owner_id = current_user.id.
-- 4. Menu QR chỉ hiển thị khi restaurant.status = 'approved'
--    và restaurant_tables.status = 'active'.
-- 5. Xóa món bằng UPDATE dishes SET is_deleted = 1, không DELETE vật lý.
