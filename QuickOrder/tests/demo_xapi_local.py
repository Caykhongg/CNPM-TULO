"""Demo thanh toán bằng dữ liệu GIẢ, chỉ bind localhost. Không gọi ngân hàng/xAPI thật.

Chạy: python tests/demo_xapi_local.py
Mở link in ra. Sau khi có phiếu QR, nhập: pay <MA_CHUYEN_KHOAN>
QR demo chỉ là chữ cảnh báo, không phải mã chuyển tiền thật.
"""
import os
import secrets
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import json
    from flask import Response
    from werkzeug.security import generate_password_hash
    from werkzeug.serving import WSGIRequestHandler, make_server

    with tempfile.TemporaryDirectory(prefix='qo-demo-xapi-') as directory:
        os.environ.update(QO_DB=str(Path(directory) / 'demo.db'), SECRET_KEY=secrets.token_hex(32), HTTPS='0',
                          XAPI_SHOP_1=json.dumps(dict(history_url='https://id.xapi.vn/historyapitpbv2/DEMO_ONLY',
                                                    bank_bin='970423', account_number='123456789')))
        import app
        import xapi_client
        ledger = []
        xapi_client.fetch_transactions = lambda cfg: list(ledger)
        password = generate_password_hash('Demo@123456')
        with app.db() as c:
            c.execute("INSERT INTO users(id,full_name,email,password_hash,role) VALUES (1,'Chủ quán demo','owner@demo.local',?,'owner')", (password,))
            c.execute("INSERT INTO users(id,full_name,email,password_hash,role) VALUES (2,'Khách demo','customer@demo.local',?,'customer')", (password,))
            c.execute("""INSERT INTO shops(id,owner_id,name,address,phone,open_time,close_time,status,bank_bin,bank_account_number,bank_account_name)
                VALUES (1,1,'Quán DEMO - Không chuyển tiền thật','Dữ liệu thử','0900000000','00:00','24:00','APPROVED','970423','123456789','DEMO KHONG CHUYEN TIEN')""")
            c.execute("INSERT INTO shop_tables(id,shop_id,table_number,qr_token) VALUES (1,1,'1','demo-table-qr')")
            c.execute("INSERT INTO categories(id,shop_id,name) VALUES (100,1,'Món demo')")
            c.execute("INSERT INTO dishes(id,shop_id,category_id,name,price) VALUES (1,1,100,'Trà sữa demo',10000)")
        original_view = app.payment_service.view

        def demo_view(c, row):
            result = original_view(c, row)
            if 'qr_url' in result:
                result['qr_url'] = '/demo-qr.svg'
            return result

        app.payment_service.view = demo_view

        @app.app.get('/demo-qr.svg')
        def demo_qr():
            return Response('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200"><rect width="300" height="200" fill="#fff4d4"/><text x="150" y="80" text-anchor="middle" font-size="30">QR DEMO</text><text x="150" y="125" text-anchor="middle" font-size="15">KHONG CHUYEN TIEN THAT</text></svg>', mimetype='image/svg+xml')

        class QuietHandler(WSGIRequestHandler):
            def log_request(self, code='-', size='-'):
                pass

        server = make_server('127.0.0.1', 5001, app.app, threaded=True, request_handler=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print('DEMO LOCAL: không gọi xAPI/ngân hàng thật.')
        print('Menu: http://127.0.0.1:5001/customer/restaurant.html?id=1&table=demo-table-qr')
        print('Chủ quán: http://127.0.0.1:5001/merchant/login.html')
        print('Chủ quán: owner@demo.local | Khách: customer@demo.local | Mật khẩu cả hai: Demo@123456')
        print('Chọn món > Chuyển khoản > Thanh toán. Sao chép mã QO... rồi nhập pay QO... tại đây.')
        print('Nhập list để xem phiếu, quit để dừng. Dữ liệu demo sẽ bị xóa khi dừng.')
        try:
            while True:
                command = input('demo> ').strip()
                if command == 'quit':
                    break
                if command == 'list':
                    with app.db() as c:
                        for row in c.execute('SELECT transfer_code,amount,state,order_id FROM payment_checkouts'):
                            print(dict(row))
                elif command.startswith('pay '):
                    code = command[4:].strip().upper()
                    with app.db() as c:
                        row = c.execute('SELECT * FROM payment_checkouts WHERE transfer_code=?', (code,)).fetchone()
                        c.execute('DELETE FROM payment_poll_locks')
                    if not row:
                        print('Không tìm thấy phiếu. Nhập list để kiểm tra.'); continue
                    ledger.append(dict(transactionID=secrets.token_hex(8), amount=row['amount'], description=code, type='IN'))
                    created = app.payment_service.reconcile_shop(1)
                    print('Đã thêm giao dịch GIẢ. Số đơn mới:', created)
        except (KeyboardInterrupt, EOFError):
            print('\nĐã dừng demo.')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == '__main__':
    main()
