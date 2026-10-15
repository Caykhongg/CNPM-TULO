# Sequence Diagram - TULO Quickorder

Dưới đây là sơ đồ tuần tự (Sequence Diagram) cho luồng cốt lõi **Đặt món và Xử lý đơn hàng** của hệ thống **TULO Quickorder**, được viết bằng mã nguồn chuẩn **Mermaid.js**. Bạn có thể copy nội dung bên dưới dán vào các công cụ hỗ trợ Mermaid (như Notion, GitHub, draw.io hoặc [Mermaid Live Editor](https://mermaid.live)) để hiển thị thành hình ảnh sơ đồ hoàn chỉnh.

```mermaid
sequenceDiagram
    autonumber
    actor KhachHang as Khách hàng
    participant FE_KH as Frontend Khách hàng
    participant Backend as Flask Backend
    participant DB as SQLite Database
    actor ChuQuan as Chủ quán / Nhân viên
    participant FE_Quan as Frontend Chủ quán

    %% 1. Xem menu và chọn món
    KhachHang->>FE_KH: Truy cập trang menu của quán / quét mã QR bàn
    FE_KH->>Backend: Yêu cầu lấy danh sách món (GET /api/menu)
    Backend->>DB: Truy vấn danh sách Dish, Category
    DB-->>Backend: Trả về dữ liệu menu
    Backend-->>FE_KH: Hiển thị menu cho khách
    
    KhachHang->>FE_KH: Chọn món, thêm tùy chọn (size, topping, ghi chú) & thêm vào giỏ hàng
    KhachHang->>FE_KH: Xác nhận đặt hàng (Nhập thông tin, chọn hình thức nhận & thanh toán)
    
    %% 2. Gửi đơn hàng
    FE_KH->>Backend: Gửi dữ liệu đơn hàng (POST /api/orders)
    Backend->>DB: Lưu thông tin Order & OrderItem (Trạng thái: "Chờ xác nhận")
    DB-->>Backend: Xác nhận lưu thành công
    Backend-->>FE_KH: Phản hồi đặt hàng thành công & hiển thị màn hình theo dõi đơn
    
    %% 3. Chủ quán tiếp nhận và xử lý đơn
    Note over ChuQuan, FE_Quan: Chủ quán theo dõi và xử lý đơn hàng
    FE_Quan->>Backend: Kiểm tra đơn hàng mới / Lắng nghe thông báo (GET /api/shop/orders)
    Backend->>DB: Truy vấn đơn hàng theo ID quán
    DB-->>Backend: Trả về danh sách đơn hàng
    Backend-->>FE_Quan: Hiển thị đơn hàng mới ("Chờ xác nhận")
    
    ChuQuan->>FE_Quan: Xem chi tiết đơn và bấm "Xác nhận đơn hàng"
    FE_Quan->>Backend: Cập nhật trạng thái đơn (PUT /api/orders/{id}/status -> "Đang làm")
    Backend->>DB: Cập nhật trạng thái Order
    DB-->>Backend: Xác nhận cập nhật
    
    %% 4. Cập nhật tiến trình cho khách hàng
    Backend-->>FE_KH: Đồng bộ/Cập nhật trạng thái đơn: "Đang làm"
    KhachHang->>FE_KH: Xem tiến trình đơn hàng trên giao diện
    
    Note over ChuQuan, KhachHang: Khi món ăn sẵn sàng / giao xong
    ChuQuan->>FE_Quan: Bấm cập nhật "Đang giao" / "Hoàn thành"
    FE_Quan->>Backend: Gửi yêu cầu cập nhật trạng thái mới
    Backend->>DB: Lưu trạng thái mới vào CSDL
    Backend-->>FE_KH: Thông báo đơn hàng hoàn tất
```

## Các Sequence Diagram bổ sung gợi ý cho nhóm:
1. **Luồng Đăng ký / Đăng nhập & Phân quyền:**
   * Tác nhân: Người dùng (Khách hàng / Chủ quán / Admin) $\rightarrow$ Frontend $\rightarrow$ Backend (Kiểm tra mật khẩu đã mã hóa) $\rightarrow$ Database $\rightarrow$ Phân quyền điều hướng màn hình phù hợp.
2. **Luồng Quản lý Menu của Chủ quán:**
   * Tác nhân: Chủ quán $\rightarrow$ Frontend Chủ quán $\rightarrow$ Backend $\rightarrow$ Database (Thêm, Sửa, Xóa món hoặc cập nhật trạng thái còn/hết hàng).