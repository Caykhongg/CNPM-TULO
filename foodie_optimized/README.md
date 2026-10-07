# Foodie - phiên bản tối ưu

## Cấu trúc
- `index.html`: điểm vào, chuyển tới trang chào mừng.
- `customer/*.html`: mỗi màn hình người dùng là một file riêng.
- `merchant/*.html`: mỗi màn hình chủ quán là một file riêng.
- `css/style.css`: CSS dùng chung.
- `js/script.js`: JavaScript dùng chung.
- Giỏ hàng được lưu bằng `localStorage` để chuyển trang không mất dữ liệu.

## Full screen / responsive
- Không còn khung điện thoại giả lập.
- Không còn `max-width`, border và bo góc kiểu mockup ở phần app.
- Dùng `100dvh`/`100%` để giao diện chiếm toàn bộ viewport trên desktop, tablet và mobile.
- `viewport-fit=cover` hỗ trợ thiết bị có tai thỏ / vùng an toàn.

## Lưu ý
Tailwind CDN vẫn được giữ vì giao diện gốc đang sử dụng rất nhiều utility class Tailwind.
CSS tùy chỉnh đã được đưa sang `css/style.css`, JavaScript sang `js/script.js`.
