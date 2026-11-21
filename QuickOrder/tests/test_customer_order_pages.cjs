/* Chạy: node --test tests/test_customer_order_pages.cjs
   Dùng Node tích hợp, không cài thêm package và không gọi mạng thật. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const test = require('node:test');

const base = path.join(__dirname, '..');
const read = name => fs.readFileSync(path.join(base, name), 'utf8');
const inline = name => read(name).match(/<script>([\s\S]*?)<\/script>/)[1];
const sample = (status = 'PENDING') => ({
  id: 1, shop_id: 7, shop_name: 'Quán thử', table_number: '1', status,
  payment_method: 'CASH', payment_status: 'UNPAID', total_amount: 40000,
  created_at: '2026-11-10 01:00:00', items: [{dish_id: 4, dish_name: 'Phở', quantity: 1, unit_price: 40000}],
});

function environment(page = 'orders.html', search = '', hash = '') {
  const elements = new Map(), data = new Map(), timers = [], events = {};
  const get = id => {
    if (!elements.has(id)) elements.set(id, {innerHTML: '', textContent: '', value: '', hidden: false, disabled: false, style: {}});
    return elements.get(id);
  };
  const document = {hidden: false, getElementById: get, querySelector: get,
    addEventListener: (name, fn) => { events['document:' + name] = fn; }};
  const location = {pathname: '/customer/' + page, search, hash,
    href: 'http://127.0.0.1:5000/customer/' + page + search + hash, reload() {}};
  const env = {get, data, timers, events, location, document, blocked: false, replacements: 0, toasts: []};
  const localStorage = {
    getItem: key => data.get(key) ?? null,
    setItem: (key, value) => { if (env.blocked) throw Error('Storage blocked'); data.set(key, value); },
  };
  const utils = vm.runInNewContext(read('js/app.js') + '\nQO;', {document, location, localStorage, URL, URLSearchParams, console,
    crypto: require('node:crypto').webcrypto});
  const QO = {...utils, header() {}, toast: message => env.toasts.push(message)};
  env.QO = QO;
  env.context = {QO, document, location, URL, URLSearchParams, console, confirm: () => true,
    history: {replaceState() { env.replacements++; location.hash = ''; }},
    window: {addEventListener: (name, fn) => { events['window:' + name] = fn; }},
    setInterval: (fn, ms) => { timers.push({fn, ms}); return timers.length; }, clearInterval() {},
  };
  env.run = code => vm.runInNewContext(code, env.context);
  return env;
}

async function cartFixture({failure = false, table = true, accepting = true, blocked = false, deferred = false, failWith = null} = {}) {
  const e = environment('cart.html');
  e.blocked = blocked;
  let cart = {shop_id: 7, table: table ? 'qr-test' : null,
    items: [{key: '4:', dish_id: 4, name: 'Phở', price: 40000, qty: 1, options: []}]};
  let posted = 0, resolve;
  const bodies = [];
  const shop = {id: 7, name: 'Quán thử', status: 'APPROVED'};
  Object.assign(e.QO, {getCart: () => cart, setCart: c => { cart = c; },
    getGuest: () => null, session: async () => null, all: async () => [], get: async () => shop,
    isAccepting: () => accepting,
    api: async (method, url, body) => {
      if (method === 'GET') return {shop, table: {id: 9, table_number: '1'}};
      assert.equal(url, 'orders'); assert.equal(body.table_id, 9); posted++; bodies.push(body);
      if (failWith) throw failWith();
      if (failure) throw Error('Gửi đơn thất bại');
      if (deferred) return new Promise(r => { resolve = r; });
      return {id: 1, shop_id: 7, access_token: 'order-proof'};
    },
  });
  await e.run(inline('customer/cart.html'));
  return Object.assign(e, {cart: () => cart, posted: () => posted, bodies,
    finish: () => resolve({id: 1, shop_id: 7, access_token: 'order-proof'})});
}

test('Đặt thành công: lưu mã, xóa giỏ và mở đúng trang theo dõi', async () => {
  const e = await cartFixture();
  await e.get('order').onclick();
  assert.equal(e.posted(), 1); assert.equal(e.cart().items.length, 0);
  assert.equal(e.QO.getOrders()[0].token, 'order-proof');
  const next = new URL(e.location.href);
  assert.equal(next.pathname, '/customer/track.html'); assert.equal(next.searchParams.get('id'), '1');
});

test('Gửi lỗi: giữ giỏ và cho thử lại', async () => {
  const e = await cartFixture({failure: true}), original = e.location.href;
  await e.get('order').onclick();
  assert.equal(e.cart().items.length, 1); assert.equal(e.location.href, original);
  assert.equal(e.get('err').textContent, 'Gửi đơn thất bại'); assert.equal(e.get('order').disabled, false);
});

test('Bấm nhanh hai lần chỉ tạo một yêu cầu đặt đơn', async () => {
  const e = await cartFixture({deferred: true});
  const first = e.get('order').onclick();
  await e.get('order').onclick(); assert.equal(e.posted(), 1);
  e.finish(); await first;
});

test('Đơn gửi kèm mã QR của bàn và mã chống gửi trùng', async () => {
  const e = await cartFixture(); await e.get('order').onclick();
  assert.equal(e.bodies[0].qr_token, 'qr-test');
  assert.match(e.bodies[0].client_request_id, /^[0-9a-f]{32}$/);
});

test('Lỗi mạng: gửi lại dùng đúng mã cũ; server báo lỗi: đổi mã mới', async () => {
  const net = await cartFixture({failWith: () => new TypeError('Failed to fetch')});
  await net.get('order').onclick(); await net.get('order').onclick();
  assert.equal(net.bodies[0].client_request_id, net.bodies[1].client_request_id);
  const api = await cartFixture({failWith: () => Object.assign(Error('Món vừa hết'), {name: 'ApiError'})});
  await api.get('order').onclick(); await api.get('order').onclick();
  assert.notEqual(api.bodies[0].client_request_id, api.bodies[1].client_request_id);
});

test('Thiếu bàn hoặc quán đóng cửa: khóa nút và chặn cả lời gọi chương trình', async () => {
  for (const options of [{table: false}, {accepting: false}]) {
    const e = await cartFixture(options);
    assert.equal(e.get('order').disabled, true);
    await e.get('order').onclick(); assert.equal(e.posted(), 0);
  }
});

test('Không ghi được localStorage: đơn vẫn mở bằng mã dự phòng trong fragment', async () => {
  const e = await cartFixture({blocked: true}); await e.get('order').onclick();
  const next = new URL(e.location.href);
  assert.equal(new URLSearchParams(next.hash.slice(1)).get('token'), 'order-proof');
  assert.equal(next.searchParams.has('token'), false); assert.equal(e.cart().items.length, 0);
});

async function ordersFixture({networkError = false, race = false} = {}) {
  const e = environment(); e.QO.addOrder({id: 1, token: 'order-proof', table_number: '1'});
  e.state = 'PENDING'; e.networkError = networkError; e.gets = 0;
  e.QO.api = async (method, url, body) => {
    if (method === 'GET') { e.gets++; if (e.networkError) throw Error('Offline'); return sample(e.state); }
    assert.equal(url, 'orders/1/cancel'); assert.equal(body.token, 'order-proof');
    if (race) { e.state = 'PREPARING'; throw Error('Chỉ có thể hủy đơn đang chờ xác nhận.'); }
    e.state = 'CANCELLED'; return sample(e.state);
  };
  await e.run(inline('customer/orders.html')); return e;
}

test('Danh sách tự tải mỗi 7 giây, bỏ nút hủy sau xác nhận và không có bộ lọc giao hàng', async () => {
  const e = await ordersFixture(); assert.equal(e.timers[0].ms, 7000);
  assert.match(e.get('list').innerHTML, /data-cancel="1"/);
  assert.match(e.get('list').innerHTML, /track\.html\?id=1/);
  assert.doesNotMatch(e.get('chips').innerHTML, /Đang giao/);
  e.state = 'CONFIRMED'; await e.timers[0].fn();
  assert.match(e.get('list').innerHTML, /Đang làm/); assert.doesNotMatch(e.get('list').innerHTML, /data-cancel=/);
});

test('Danh sách lỗi mạng hiển thị lỗi tải, giữ đơn và phục hồi khi bấm Tải lại', async () => {
  const e = await ordersFixture({networkError: true});
  assert.match(e.get('list').innerHTML, /Chưa tải được danh sách đơn/);
  assert.doesNotMatch(e.get('list').innerHTML, /Không có đơn ở mục này/);
  assert.equal(e.QO.getOrders().length, 1);
  e.networkError = false; await e.get('refresh-orders').onclick();
  assert.match(e.get('list').innerHTML, /Đơn #1/);
});

test('Hủy trên danh sách khi quán vừa xác nhận: tải ngay trạng thái mới', async () => {
  const e = await ordersFixture({race: true});
  await e.get('list').onclick({target: {closest: selector => selector === '[data-cancel]' ? {dataset: {cancel: '1'}} : null}});
  assert.match(e.get('list').innerHTML, /Đang làm/); assert.doesNotMatch(e.get('list').innerHTML, /data-cancel=/);
  assert.ok(e.gets >= 2);
});

async function trackingFixture({id = '1', fragment = false, race = false} = {}) {
  const e = environment('track.html', '?id=' + id, fragment ? '#token=order-proof' : '');
  if (!fragment) e.QO.addOrder({id: 1, token: 'order-proof'});
  e.state = 'PENDING'; e.requests = 0; e.networkError = false;
  e.QO.api = async (method, url, body) => {
    e.requests++;
    if (method === 'GET') { if (e.networkError) throw Error('Offline'); return sample(e.state); }
    assert.equal(url, 'orders/1/cancel'); assert.equal(body.token, 'order-proof');
    if (race) { e.state = 'PREPARING'; throw Error('Quán vừa xác nhận đơn.'); }
    e.state = 'CANCELLED'; return {...sample(e.state), cancel_reason: 'Khách hủy đơn'};
  };
  await e.run(read('js/order-tracking.js')); return e;
}

test('Trang theo dõi đổi trạng thái tự động, giữ dữ liệu khi lỗi mạng và phục hồi', async () => {
  const e = await trackingFixture(); assert.equal(e.timers[0].ms, 7000);
  assert.match(e.get('tracking-root').innerHTML, /id="cancel-order"/);
  e.networkError = true; e.timers[0].fn(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(e.get('tracking-error').hidden, false); assert.match(e.get('tracking-root').innerHTML, /Quán thử/);
  e.networkError = false; e.state = 'COMPLETED'; await e.get('refresh-order').onclick();
  assert.equal(e.get('tracking-error').hidden, true);
  assert.match(e.get('tracking-root').innerHTML, /Hoàn thành/); assert.doesNotMatch(e.get('tracking-root').innerHTML, /id="cancel-order"/);
});

test('Trang theo dõi xử lý hủy thành công và cuộc đua với xác nhận', async () => {
  for (const race of [false, true]) {
    const e = await trackingFixture({race});
    await e.get('tracking-root').onclick({target: {closest: selector => selector === '#cancel-order' ? {} : null}});
    assert.match(e.get('tracking-root').innerHTML, race ? /Đang làm/ : /Đã hủy/);
    assert.doesNotMatch(e.get('tracking-root').innerHTML, /id="cancel-order"/);
    if (race) assert.equal(e.get('tracking-error').textContent, 'Quán vừa xác nhận đơn.');
  }
});

test('Mã dự phòng được lưu lại rồi xóa khỏi thanh địa chỉ khi lưu thành công', async () => {
  const e = await trackingFixture({fragment: true});
  assert.equal(e.QO.getOrders()[0].token, 'order-proof'); assert.equal(e.replacements, 1);
});

test('Liên kết sai không gọi API; dữ liệu lưu cũ sai định dạng không làm hỏng trang', async () => {
  const e = await trackingFixture({id: 'invalid'}); assert.equal(e.requests, 0);
  assert.match(e.get('tracking-root').innerHTML, /Liên kết đơn không hợp lệ/);
  e.data.set('qo_orders', '{"bad":"data"}'); assert.equal(e.QO.getOrders().length, 0);
  e.data.set('qo_orders', '[null,{"id":"1"},{"id":"wrong"}]'); assert.equal(e.QO.getOrders().length, 1);
  e.blocked = true; assert.equal(e.QO.saveOrders([]), false);
});

// Các nhánh thanh toán QR: chưa trả tiền không được gửi đơn/hiện thành công.
test('Chuyển khoản: giữ giỏ, lưu phiếu riêng và mở trang thanh toán', async () => {
  const e = await cartFixture();
  const pid = 'a'.repeat(32);
  e.QO.api = async (method, url, body) => {
    assert.equal(method, 'POST'); assert.equal(url, 'orders'); assert.equal(body.payment_method, 'TRANSFER');
    return {kind: 'PAYMENT_CHECKOUT', id: pid, access_token: 'payment-proof', shop_id: 7};
  };
  e.get('pays').onclick({target: {closest: () => ({dataset: {pay: 'TRANSFER'}})}});
  await e.get('order').onclick();
  assert.equal(e.cart().items.length, 1); assert.equal(e.QO.getOrders().length, 0);
  assert.equal(e.QO.getPendingPayments()[0].token, 'payment-proof');
  assert.equal(new URL(e.location.href).pathname, '/customer/pay.html');
});

test('Chuyển khoản khi chặn localStorage vẫn giữ mã dự phòng trong fragment', async () => {
  const e = await cartFixture({blocked: true});
  e.QO.api = async () => ({kind: 'PAYMENT_CHECKOUT', id: 'a'.repeat(32), access_token: 'payment-proof'});
  e.get('pays').onclick({target: {closest: () => ({dataset: {pay: 'TRANSFER'}})}});
  await e.get('order').onclick();
  assert.equal(new URL(e.location.href).hash, '#token=payment-proof');
  assert.equal(e.cart().items.length, 1);
});

async function paymentFixture({failure = false, paid = false, changedCart = false, fragment = false, manual = false} = {}) {
  const pid = 'a'.repeat(32), e = environment('pay.html', '?id=' + pid, fragment ? '#token=payment-proof' : '');
  let cart = {shop_id: changedCart ? 9 : 7, items: [{dish_id: 4, qty: 1, options: []}]};
  if (!fragment) e.QO.savePendingPayment({id: pid, token: 'payment-proof', cart: JSON.stringify(changedCart ? {} : cart)});
  e.QO.getCart = () => cart; e.QO.setCart = value => { cart = value; };
  e.paid = paid; e.failure = failure; e.calls = 0;
  const result = () => ({kind: 'PAYMENT_CHECKOUT', id: pid, state: e.paid ? 'PAID' : 'WAITING', amount: 40000,
    shop_id: 7, shop_name: 'Quán thử', account_number: '123456789', account_name: 'NGUYEN VAN A', bank_bin: '970423',
    verification_mode: manual ? 'MANUAL' : 'AUTO', transfer_code: 'QO1234567890ABCDEF', expires_at: 2000000000,
    items: [{dish_id: 4, quantity: 1, option_ids: []}], qr_url: 'https://img.vietqr.io/image/test.svg',
    ...(e.paid ? {order: {...sample(), payment_method: 'TRANSFER', payment_status: 'PAID'}} : {})});
  e.QO.api = async (method, url, body) => {
    e.calls++;
    if (method === 'POST') { assert.equal(body.token, 'payment-proof'); if (e.failure) throw Error('Chưa kiểm tra được xAPI'); }
    return result();
  };
  await e.run(read('js/payment.js'));
  return Object.assign(e, {cart: () => cart});
}

test('QR đang chờ chỉ hiển thị chờ thanh toán và tự kiểm tra 5 giây', async () => {
  const e = await paymentFixture();
  assert.match(e.get('payment-root').innerHTML, /Chờ thanh toán/);
  assert.doesNotMatch(e.get('payment-root').innerHTML, /Thanh toán thành công/);
  assert.equal(e.timers[0].ms, 5000); assert.equal(e.QO.getOrders().length, 0);
});

test('xAPI lỗi: vẫn xem QR, không báo đã trả tiền và tự thử lại', async () => {
  const e = await paymentFixture({failure: true});
  assert.match(e.get('payment-root').innerHTML, /Chờ thanh toán/);
  assert.equal(e.get('payment-error').hidden, false);
  assert.equal(e.QO.getOrders().length, 0);
  e.failure = false; e.paid = true;
  await e.timers[0].fn(); await new Promise(resolve => setImmediate(resolve));
  assert.match(e.get('payment-root').innerHTML, /Thanh toán thành công/);
  assert.equal(e.QO.getOrders()[0].token, 'payment-proof');
});

test('Server xác nhận: lưu đơn, xóa đúng giỏ và hiện thành công', async () => {
  const e = await paymentFixture({paid: true});
  assert.match(e.get('payment-root').innerHTML, /Đơn #1 đã gửi tới quán/);
  assert.equal(e.QO.getOrders()[0].payment_id, 'a'.repeat(32));
  assert.equal(e.cart().items.length, 0);
  assert.equal(e.get('check-payment').hidden, true);
  assert.equal(e.get('main h1').textContent, 'Thanh toán thành công');
  assert.equal(e.document.title, 'Thanh toán thành công - QuickOrder');
  await e.run(read('js/payment.js')); // reload trang thành công vẫn tìm được quyền xem từ đơn đã lưu
  assert.match(e.get('payment-root').innerHTML, /Thanh toán thành công/);
});

test('Phiếu tự chuyển từ QR sang thành công theo kết quả server rồi dừng kiểm tra', async () => {
  const e = await paymentFixture();
  assert.match(e.get('payment-root').innerHTML, /QR chuyển khoản/);
  e.paid = true;
  await e.timers[0].fn(); await new Promise(resolve => setImmediate(resolve));
  assert.match(e.get('payment-root').innerHTML, /Thanh toán thành công/);
  assert.doesNotMatch(e.get('payment-root').innerHTML, /<img/);
  assert.equal(e.get('check-payment').hidden, true);
  assert.equal(e.cart().items.length, 0);
  const calls = e.calls;
  await e.timers[0].fn();
  await e.get('check-payment').onclick();
  await e.events['document:visibilitychange']();
  assert.equal(e.calls, calls);
});

test('Thanh toán xong không xóa giỏ khác vừa chọn', async () => {
  const e = await paymentFixture({paid: true, changedCart: true});
  assert.equal(e.cart().shop_id, 9); assert.equal(e.cart().items.length, 1);
});

test('Mã từ fragment thanh toán xong vẫn lưu được quyền xem đơn', async () => {
  const e = await paymentFixture({paid: true, fragment: true});
  assert.equal(e.QO.getOrders()[0].token, 'payment-proof');
  assert.equal(e.cart().items.length, 0);
});


test('Phiếu không token: báo chờ chủ quán, vẫn có QR và tự nhận kết quả xác nhận', async () => {
  const e = await paymentFixture({manual: true});
  assert.match(e.get('payment-root').innerHTML, /Chờ quán xác nhận thanh toán/);
  assert.match(e.get('payment-root').innerHTML, /QR chuyển khoản/);
  assert.equal(e.get('check-payment').textContent, 'Tải lại trạng thái');
  e.paid = true;
  await e.timers[0].fn(); await new Promise(resolve => setImmediate(resolve));
  assert.match(e.get('payment-root').innerHTML, /Thanh toán thành công/);
});

async function bankFixture({auto = false, pending = false} = {}) {
  const e = environment('shop.html');
  let config = {bank_bin: '970423', account_number: '123456789', account_name: 'NGUYEN VAN A',
    mode: auto ? 'AUTO' : 'MANUAL', has_token: auto, message: auto ? 'Đã kết nối xAPI' : 'Xác nhận thủ công'};
  e.QO.requireOwner = async () => ({id: 1});
  e.QO.myShop = async () => ({id: 7});
  e.posts = []; e.confirmed = 0;
  e.context.prompt = () => 'BANK-12345';
  e.QO.api = async (method, url, body) => {
    if (url === 'payment-banks') return {banks: [{bin: '970423', name: 'TPBank', full_name: 'Ngân hàng Tiên Phong'}]};
    if (url.endsWith('/payment-config') && method === 'GET') return config;
    if (url.endsWith('/payment-config') && method === 'PUT') {
      e.posts.push(body);
      config = {...body, has_token: body.mode === 'AUTO', message: 'Đã lưu'}; delete config.credential;
      return config;
    }
    if (url.endsWith('/payment-checkouts')) return pending && !e.confirmed ? [{id: 'a'.repeat(32), transfer_code: 'QO1234567890ABCDEF', amount: 10000, account_number: '123456789', customer_name: 'Khách', can_confirm: true}] : [];
    if (url.endsWith('/confirm')) { e.confirmed++; e.reference = body.transaction_id; return {state: 'PAID', order_id: 8}; }
    throw Error(url);
  };
  await e.run(read('js/owner-bank.js'));
  return e;
}

test('Chủ quán lưu ngân hàng không token chọn thủ công; có token tự bật xAPI và xóa ô bí mật', async () => {
  const e = await bankFixture();
  await e.get('bank-form').onsubmit({preventDefault() {}});
  assert.equal(e.posts[0].mode, 'MANUAL');
  e.get('bank-token').value = 'MY_PRIVATE_TOKEN';
  await e.get('bank-form').onsubmit({preventDefault() {}});
  assert.equal(e.posts[1].mode, 'AUTO');
  assert.equal(e.posts[1].credential, 'MY_PRIVATE_TOKEN');
  assert.equal(e.get('bank-token').value, '');
  assert.equal(e.get('test-bank').hidden, false);
  assert.equal([...e.data.values()].some(v => String(v).includes('MY_PRIVATE_TOKEN')), false);
});

test('Bỏ trống token đã lưu giữ AUTO; đổi tài khoản không token thì MANUAL', async () => {
  const e = await bankFixture({auto: true});
  await e.get('bank-form').onsubmit({preventDefault() {}});
  assert.equal(e.posts[0].mode, 'AUTO');
  e.get('bank-number').value = '987654321';
  await e.get('bank-form').onsubmit({preventDefault() {}});
  assert.equal(e.posts[1].mode, 'MANUAL');
});

test('Chủ quán xác nhận thủ công gửi mã giao dịch và phiếu biến khỏi danh sách chờ', async () => {
  const e = await bankFixture({pending: true});
  assert.match(e.get('bank-queue').innerHTML, /Đã kiểm tra và nhận đủ tiền/);
  const dataset = {confirmPayment: 'a'.repeat(32), code: 'QO1234567890ABCDEF', amount: '10000'};
  await e.get('bank-queue').onclick({target: {closest: () => ({dataset})}});
  assert.equal(e.reference, 'BANK-12345');
  assert.equal(e.confirmed, 1);
  assert.doesNotMatch(e.get('bank-queue').innerHTML, /Đã kiểm tra và nhận đủ tiền/);
});
