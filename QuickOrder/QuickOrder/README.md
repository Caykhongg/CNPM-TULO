# QuickOrder
Mở `index.html` (nên chạy qua server: `python -m http.server`).

- `customer/home.html`: tìm quán/món (không dấu cũng được), lọc theo Category.
- `customer/restaurant.html?id=..`: xem menu theo danh mục, chọn OptionGroup/Option, thêm giỏ.
- `merchant/login.html`: đăng ký/đăng nhập chủ quán (User, role OWNER). Khách không cần đăng nhập.
- `merchant/shop.html` (Shop), `tables.html` (DiningTable + qr_token), `menu.html` (Category, Dish, OptionGroup, Option).
- `admin/shops.html`: duyệt/từ chối/khóa quán (Shop.approve/reject/lock/unlock). Quán phải APPROVED mới hiện cho khách.
- CSDL: IndexedDB trong trình duyệt (js/app.js), cấu trúc giống `schema.sql` (SQL Server). Không có dữ liệu mẫu.
