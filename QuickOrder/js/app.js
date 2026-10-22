/* QuickOrder - CSDL (SQLite qua Flask API) theo sơ đồ lớp mục 3.1 (Hình 2) + tiện ích dùng chung */
const QO = (() => {
  // Dữ liệu lưu ở server (Flask + SQLite) qua /api/...
  const api = async (method, url, body) => {
    const r = await fetch('/api/' + url, {method, headers: {'Content-Type': 'application/json'}, body: body ? JSON.stringify(body) : undefined});
    if (r.status === 204) return null;
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error(j.error || r.statusText); e.name = r.status === 409 ? 'ConstraintError' : r.status === 404 ? 'NotFound' : 'ApiError'; throw e; }
    return j;
  };
  const all = s => api('GET', s);
  const get = (s, id) => api('GET', s + '/' + Number(id)).catch(e => { if (e.name === 'NotFound') return null; throw e; });
  const by = (s, i, v) => api('GET', s + '?' + i + '=' + encodeURIComponent(v));
  const put = (s, o) => o.id ? api('PUT', s + '/' + o.id, o) : api('POST', s, o);
  const del = (s, id) => api('DELETE', s + '/' + Number(id)).catch(e => { if (e.name === 'ConstraintError') toast('Không xóa được vì đang được sử dụng'); else throw e; });

  // ===== Quy tắc nghiệp vụ trong sơ đồ =====
  const toMin = t => { const [h, m] = t.split(':').map(Number); return h*60 + m; };
  const isOpenNow = (s, at = new Date()) => { const n = at.getHours()*60 + at.getMinutes(), o = toMin(s.open_time), c = toMin(s.close_time);
    return o <= c ? n >= o && n < c : n >= o || n < c; };                       // Shop.is_open_now (qua nửa đêm)
  const isAccepting = s => s.status === 'APPROVED' && isOpenNow(s);              // Shop.is_accepting_orders
  const isOrderable = d => d.is_available && !d.is_deleted;                      // Dish.is_orderable
  const validateSelection = (g, opts) => !(g.is_required && !opts.length) && !(!g.is_multiple && opts.length > 1); // OptionGroup.validate_selection
  const qrUrl = t => new URL('../customer/restaurant.html?id=' + t.shop_id + '&table=' + t.qr_token, location.href).href; // DiningTable.qr_url
  const STATUS = {PENDING:['Chờ duyệt','wait'], APPROVED:['Đã duyệt','ok'], REJECTED:['Bị từ chối','no'], LOCKED:['Bị khóa','no']};
  // Trạng thái đơn theo SRS (Phụ lục B): CONFIRMED và PREPARING đều hiển thị là "Đang làm"
  const ORDER_STATUS = {PENDING:['Chờ xác nhận','wait'], CONFIRMED:['Đang làm','ok'], PREPARING:['Đang làm','ok'], COMPLETED:['Hoàn thành','ok'], CANCELLED:['Đã hủy','no']};
  const PAY_METHOD = {CASH:'Tiền mặt', TRANSFER:'Chuyển khoản / QR'};

  // ===== Tiện ích =====
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = n => Number(n).toLocaleString('vi-VN') + 'đ';
  const norm = s => String(s||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/đ/g,'d');
  const hash = async raw => { if (crypto.subtle) { const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw));
    return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2,'0')).join(''); }
    let h = 5381; for (const c of raw) h = (h*33) ^ c.charCodeAt(0); return 'x' + (h>>>0).toString(16); };
  const toast = m => { let t = document.getElementById('toast'); if (!t) { t = document.createElement('div'); t.id = 'toast'; document.body.appendChild(t); }
    t.textContent = m; t.classList.add('show'); clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove('show'), 2200); };
  const param = k => new URLSearchParams(location.search).get(k);
  // created_at do server ghi theo giờ UTC dạng "YYYY-MM-DD HH:MM:SS"
  const parseTime = s => new Date(String(s).replace(' ', 'T') + 'Z');
  const fmtTime = s => { const d = parseTime(s); return isNaN(d) ? '' : d.toLocaleString('vi-VN', {hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit'}); };

  // Đường dẫn: các trang nằm trong thư mục customer/, merchant/, admin/ phải lùi một cấp để về trang chủ
  const inSub = () => /\/(customer|merchant|admin)\//.test(location.pathname);
  const rootUrl = () => inSub() ? '../' : '';
  const homeUrl = () => rootUrl() + 'index.html';

  // Phiên đăng nhập nằm trên server (cookie HttpOnly). Trình duyệt không lưu và không tự quyết quyền truy cập.
  const session = async () => { try { return await api('GET', 'me'); } catch { return null; } };
  const logout = async () => { try { await api('POST', 'logout'); } catch {} location.href = homeUrl(); };
  const requireOwner = async () => { const u = await session();
    if (!u || u.role !== 'owner') { location.replace('login.html'); throw 0; } return u; };
  const myShop = async () => { const u = await session();
    return u && u.role === 'owner' ? (await by('shops', 'owner_id', u.id))[0] : undefined; };

  // Giỏ hàng: lưu trong phiên của tab (sessionStorage), gắn với bàn; đóng tab là mất giỏ (SRS mục 1.4)
  const getCart = () => { try { return JSON.parse(sessionStorage.getItem('qo_cart')) || {shop_id:null, table:null, items:[]}; } catch { return {shop_id:null, table:null, items:[]}; } };
  const setCart = c => { sessionStorage.setItem('qo_cart', JSON.stringify(c)); badge(); };
  const badge = () => { const n = getCart().items.reduce((s, i) => s + i.qty, 0), b = document.getElementById('cart-n'); if (b) b.textContent = n || ''; if (b) b.style.display = n ? '' : 'none'; };

  // Hồ sơ tạm của khách chưa có tài khoản: chỉ lưu trong sessionStorage của tab, đóng tab là mất (không gửi lên server)
  const getGuest = () => { try { return JSON.parse(sessionStorage.getItem('qo_guest')) || null; } catch { return null; } };
  const setGuest = p => sessionStorage.setItem('qo_guest', JSON.stringify(p));
  const clearGuest = () => sessionStorage.removeItem('qo_guest');

  // Danh sách đơn khách đã gửi, lưu trên thiết bị này (localStorage) để xem lại sau khi đóng tab.
  // Mỗi mục: {id, shop_id, shop_name, table_number}. Server vẫn là nguồn chính về trạng thái đơn.
  const getOrders = () => { try { return JSON.parse(localStorage.getItem('qo_orders')) || []; } catch { return []; } };
  const saveOrders = list => { try { localStorage.setItem('qo_orders', JSON.stringify(list)); } catch {} };
  const addOrder = o => saveOrders([o, ...getOrders().filter(x => x.id !== o.id)].slice(0, 30));

  // ===== Thanh công cụ chung =====
  // Hai khu vực của sản phẩm: "Người dùng" (khách gọi món) và "Chủ quán".
  // Mục quản lý của chủ quán chỉ hiện khi phiên đăng nhập là chủ quán.
  const SECTIONS = {
    customer: [['customer/home.html', 'Gọi món tại bàn'], ['customer/scan.html', 'Quét QR'], ['customer/cart.html', 'Giỏ hàng'], ['customer/orders.html', 'Đơn hàng'], ['customer/profile.html', 'Hồ sơ']],
    merchant: [['merchant/dashboard.html', 'Tổng quan'], ['merchant/orders.html', 'Đơn hàng'], ['merchant/menu.html', 'Thực đơn'], ['merchant/tables.html', 'Bàn & QR'], ['merchant/revenue.html', 'Doanh thu'], ['merchant/shop.html', 'Hồ sơ quán']]
  };
  const linkTo = ([p, t]) => `<a href="${rootUrl()}${p}"${location.pathname.endsWith('/' + p) ? ' class="on" aria-current="page"' : ''}>${t}${p === 'customer/cart.html' ? '<span class="badge-n" id="cart-n"></span>' : ''}</a>`;
  const guestLinks = () => `<a href="${rootUrl()}merchant/login.html">Đăng nhập</a><a href="${rootUrl()}merchant/login.html?mode=register">Đăng ký tài khoản</a>`;
  const closeMenus = () => document.querySelectorAll('.dd.open').forEach(d => { d.classList.remove('open'); d.querySelector('.dd-btn').setAttribute('aria-expanded', 'false'); });

  // Cập nhật khu vực tài khoản và mục chủ quán theo phiên đăng nhập hiện tại
  const refreshAccount = async () => {
    const u = await session(), owner = !!u && u.role === 'owner';
    const acct = document.getElementById('acct'), links = document.getElementById('mer-links'), desc = document.getElementById('mer-desc');
    if (!acct || !links) return;
    acct.hidden = !u;
    if (u) document.getElementById('who').textContent = u.full_name || u.email;
    desc.textContent = owner ? 'Quản lý quán, thực đơn và bàn.' : 'Đăng nhập để quản lý quán của bạn.';
    links.innerHTML = owner ? SECTIONS.merchant.map(linkTo).join('') : guestLinks();
  };

  const header = () => {
    const here = location.pathname;
    const sec = /\/merchant\//.test(here) ? 'merchant' : /\/customer\//.test(here) ? 'customer' : 'home';
    document.body.insertAdjacentHTML('afterbegin', `<header class="topbar"><div class="in">
      <a class="logo" href="${homeUrl()}">Quick<b>Order</b></a>
      <nav class="switch" aria-label="Chọn khu vực">
        <div class="dd">
          <button class="dd-btn${sec === 'customer' ? ' on' : ''}" type="button" aria-expanded="false">Người dùng</button>
          <div class="dd-panel"><div class="dd-box"><p class="dd-desc">Khách gọi món bằng mã QR trên bàn.</p><div class="dd-links">${SECTIONS.customer.map(linkTo).join('')}</div></div></div>
        </div>
        <div class="dd">
          <button class="dd-btn${sec === 'merchant' ? ' on' : ''}" type="button" aria-expanded="false">Chủ quán</button>
          <div class="dd-panel"><div class="dd-box"><p class="dd-desc" id="mer-desc">Đăng nhập để quản lý quán của bạn.</p><div class="dd-links" id="mer-links">${guestLinks()}</div></div></div>
        </div>
      </nav>
      <div class="acct" id="acct" hidden><span id="who"></span><button type="button" id="logout">Đăng xuất</button></div>
    </div></header>`);

    const bar = document.querySelector('.topbar');
    bar.addEventListener('click', e => {
      const btn = e.target.closest('.dd-btn');
      if (btn) { const d = btn.parentElement, open = !d.classList.contains('open'); closeMenus(); d.classList.toggle('open', open); btn.setAttribute('aria-expanded', String(open)); }
      if (e.target.closest('#logout')) logout();
    });
    document.addEventListener('click', e => { if (!e.target.closest('.dd')) closeMenus(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeMenus(); });
    badge();
    refreshAccount();
  };

  return {api, all, get, by, put, del, isOpenNow, isAccepting, isOrderable, validateSelection, qrUrl, STATUS, ORDER_STATUS, PAY_METHOD,
    esc, money, norm, hash, toast, param, parseTime, fmtTime, session, logout, requireOwner, myShop, getCart, setCart, getGuest, setGuest, clearGuest,
    getOrders, saveOrders, addOrder, header};
})();
