"""Kiểm tra cấu hình xAPI của một quán, không tạo đơn và không in token.

python check_xapi.py --shop-id 1
python check_xapi.py --shop-id 1 --connect
"""
import argparse
import app
import xapi_client
import bank_connections


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shop-id', type=int, required=True)
    parser.add_argument('--connect', action='store_true', help='Gọi API lịch sử thật (chỉ đọc)')
    args = parser.parse_args()
    with app.db() as c:
        shop = c.execute('SELECT * FROM shops WHERE id=?', (args.shop_id,)).fetchone()
    if not shop:
        print('Không tìm thấy quán.'); return 1
    try:
        with app.db() as c:
            config = bank_connections.current_config(c, shop)
        if config['mode'] == 'MANUAL':
            print('Quán đang xác nhận chuyển khoản thủ công. Thêm token tại Chủ quán > Ngân hàng & thanh toán để bật tự động.')
            return 0
        print(f"Quán #{shop['id']}: {shop['name']}")
        print(f"BIN: {config['bank_bin']} | Tài khoản nhận: {config['account_number']}")
        print('Cấu hình URL/token: hợp lệ về định dạng (không hiển thị bí mật).')
        if args.connect:
            transactions = xapi_client.fetch_transactions(config)
            print(f'xAPI trả lịch sử hợp lệ: {len(transactions)} giao dịch.')
            print('Đây là kiểm tra kết nối, KHÔNG đồng nghĩa một phiếu thanh toán đã được trả tiền.')
        else:
            print('Chưa gọi xAPI. Thêm --connect để kiểm tra kết nối thật.')
    except xapi_client.PaymentError as error:
        print('LỖI:', str(error)); return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
