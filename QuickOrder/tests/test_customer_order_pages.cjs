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
  const utils = vm.runInNewContext(read('js/app.js') + '\nQO;', {document, location, localStorage, URL, URLSearchParams, console});
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

async function cartFixture({failure = false, table = true, accepting = true, blocked = false, deferred = false} = {}) {
  const e = environment('cart.html');
  e.blocked = blocked;
  let cart = {shop_id: 7, table: table ? 'qr-test' : null,
    items: [{key: '4:', dish_id: 4, name: 'Phở', price: 40000, qty: 1, options: []}]};
  let posted = 0, resolve;
  const shop = {id: 7, name: 'Quán thử', status: 'APPROVED'};
  Object.assign(e.QO, {getCart: () => cart, setCart: c => { cart = c; },
    getGuest: () => null, session: async () => null, all: async () => [], get: async () => shop,
    isAccepting: () => accepting,
    api: async (method, url, body) => {
      if (method === 'GET') return {shop, table: {id: 9, table_number: '1'}};
      assert.equal(url, 'orders'); assert.equal(body.table_id, 9); posted++;
      if (failure) throw Error('Gửi đơn thất bại');
      if (deferred) return new Promise(r => { resolve = r; });
      return {id: 1, shop_id: 7, access_token: 'order-proof'};
    },
  });
  await e.run(inline('customer/cart.html'));
  return Object.assign(e, {cart: () => cart, posted: () => posted,
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
