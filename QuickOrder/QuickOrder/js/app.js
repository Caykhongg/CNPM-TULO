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
  const newToken = () => (crypto.randomUUID ? crypto.randomUUID().replace(/-/g,'') : Math.random().toString(36).slice(2) + Date.now().toString(36));
  const qrUrl = t => new URL('../customer/restaurant.html?id=' + t.shop_id + '&table=' + t.qr_token, location.href).href; // DiningTable.qr_url
  const STATUS = {PENDING:['Chờ duyệt','wait'], APPROVED:['Đã duyệt','ok'], REJECTED:['Bị từ chối','no'], LOCKED:['Bị khóa','no']};

  // ===== Tiện ích =====
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = n => Number(n).toLocaleString('vi-VN') + 'đ';
  const norm = s => String(s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d');
  const hash = async raw => { if (crypto.subtle) { const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw));
    return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2,'0')).join(''); }
    let h = 5381; for (const c of raw) h = (h*33) ^ c.charCodeAt(0); return 'x' + (h>>>0).toString(16); };
  const toast = m => { let t = document.getElementById('toast'); if (!t) { t = document.createElement('div'); t.id = 'toast'; document.body.appendChild(t); }
    t.textContent = m; t.classList.add('show'); clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove('show'), 2200); };
  const param = k => new URLSearchParams(location.search).get(k);

  // Phiên chủ quán (không có đăng nhập cho khách)
  const me = () => Number(sessionStorage.getItem('qo_user')) || null;
  const login = id => sessionStorage.setItem('qo_user', id);
  const logout = () => { sessionStorage.removeItem('qo_user'); location.href = 'login.html'; };
  const requireOwner = async () => { const id = me(); const u = id && await get('users', id);
    if (!u) { location.replace('login.html'); throw 0; } return u; };
  const myShop = async () => (await by('shops', 'owner_id', me()))[0];

  // Giỏ hàng (lớp phiên, lưu localStorage)
  const getCart = () => { try { return JSON.parse(localStorage.getItem('qo_cart')) || {shop_id:null, table:null, items:[]}; } catch { return {shop_id:null, table:null, items:[]}; } };
  const setCart = c => { localStorage.setItem('qo_cart', JSON.stringify(c)); badge(); };
  const badge = () => { const n = getCart().items.reduce((s, i) => s + i.qty, 0), b = document.getElementById('cart-n'); if (b) b.textContent = n || ''; if (b) b.style.display = n ? '' : 'none'; };

  const header = kind => { const file = location.pathname.split('/').pop(); const a = f => f === file ? ' class="on"' : '';
    const nav = kind === 'merchant'
      ? (me() ? `<a href="shop.html"${a('shop.html')}>Quán</a><a href="tables.html"${a('tables.html')}>Bàn</a><a href="menu.html"${a('menu.html')}>Menu</a><button onclick="QO.logout()">Đăng xuất</button>` : '')
      : `<a href="home.html"${a('home.html')}>Khám phá</a><a href="cart.html"${a('cart.html')}>Giỏ hàng<span class="badge-n" id="cart-n"></span></a><a href="../merchant/login.html">Dành cho chủ quán</a>`;
    document.body.insertAdjacentHTML('afterbegin', `<header class="topbar"><div class="in"><a class="logo" href="${kind==='merchant'?'shop.html':'home.html'}">Quick<b>Order</b></a><nav class="nav">${nav}</nav></div></header>`); badge(); };

  return {api, all, get, by, put, del, isOpenNow, isAccepting, isOrderable, validateSelection, newToken, qrUrl, STATUS,
    esc, money, norm, hash, toast, param, me, login, logout, requireOwner, myShop, getCart, setCart, header};
})();