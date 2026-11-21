QO.header('customer');
(async () => {
  const $ = id => document.getElementById(id), id = QO.param('id');
  const root = $('payment-root'), error = $('payment-error'), button = $('check-payment');
  if (!/^[a-f0-9]{32}$/.test(id || '')) { root.innerHTML = '<div class="empty">Liên kết thanh toán không hợp lệ.</div>'; button.disabled = true; return; }
  const saved = QO.getPendingPayments().find(p => p.id === id);
  const fragment = new URLSearchParams(location.hash.slice(1)).get('token') || '';
  const previous = QO.getOrders().find(o => o.payment_id === id);
  const token = fragment || saved?.token || previous?.token || '';
  let busy = false, stopped = false, state = '', timer;
  const showError = message => { error.textContent = message; error.hidden = !message; };
  const render = p => {
    state = p.state;
    if (p.state === 'PAID' && p.order) {
      const o = p.order;
      const stored = QO.addOrder({id: o.id, token, shop_id: p.shop_id, shop_name: p.shop_name, payment_id: id});
      // Không xóa giỏ mới nếu khách đã sửa giỏ trong tab khác.
      const cart = QO.getCart();
      const signature = items => JSON.stringify(items.map(i => [Number(i.dish_id), Number(i.quantity ?? i.qty),
        (i.option_ids || i.options.map(o => o.id)).map(Number).sort((a,b) => a-b)]).sort((a,b) => JSON.stringify(a).localeCompare(JSON.stringify(b))));
      const sameCart = saved?.cart === JSON.stringify(cart) || (Number(cart.shop_id) === p.shop_id && Array.isArray(p.items) && signature(cart.items) === signature(p.items));
      if (sameCart) { try { QO.setCart({shop_id: null, table: null, items: []}); } catch {} }
      QO.forgetPendingPayment(id);
      const href = QO.orderTrackingUrl(o.id, stored ? '' : token);
      document.title = 'Thanh toán thành công - QuickOrder';
      const heading = document.querySelector('main h1'), subtitle = document.querySelector('main .sub');
      if (heading) heading.textContent = 'Thanh toán thành công';
      if (subtitle) subtitle.textContent = 'Hệ thống đã xác nhận thanh toán và gửi đơn tới quán.';
      button.hidden = true;
      root.innerHTML = `<section class="card" style="text-align:center;padding:28px 20px"><div aria-hidden="true" style="display:grid;place-items:center;width:72px;height:72px;border-radius:50%;margin:0 auto 16px;background:#e0f3ec;color:#117a61;font-size:42px">✓</div><span class="tag ok">Thanh toán thành công</span><h2 style="margin-top:16px">Đơn #${o.id} đã gửi tới quán</h2><p>${QO.esc(p.shop_name)} đã nhận đơn chờ xác nhận.</p><p class="price" style="margin:16px 0">${QO.money(p.amount)}</p><a class="btn" href="${QO.esc(href)}">Theo dõi đơn hàng</a></section>`;
    } else if (p.state === 'WAITING') {
      const expires = new Date(p.expires_at * 1000).toLocaleTimeString('vi-VN');
      const manual = p.verification_mode === 'MANUAL';
      button.textContent = manual ? 'Tải lại trạng thái' : 'Kiểm tra thanh toán';
      root.innerHTML = `<section class="card"><span class="tag wait">${manual ? 'Chờ quán xác nhận thanh toán' : 'Chờ thanh toán'}</span><h2 style="margin-top:12px">${QO.esc(p.shop_name)}</h2>
        <img src="${QO.esc(p.qr_url)}" alt="QR chuyển khoản có số tiền và nội dung riêng" referrerpolicy="no-referrer" style="display:block;max-width:300px;width:100%;margin:16px auto">
        <p><b>Số tiền:</b> <span class="price">${QO.money(p.amount)}</span></p><p style="overflow-wrap:anywhere"><b>Nội dung:</b> ${QO.esc(p.transfer_code)}</p>
        <button class="btn ghost sm" type="button" data-copy="${QO.esc(p.transfer_code)}">Sao chép nội dung</button>
        <p style="margin-top:12px"><b>Số tài khoản:</b> ${QO.esc(p.account_number)}</p><p><b>Chủ tài khoản:</b> ${QO.esc(p.account_name)}</p><p class="meta">BIN ngân hàng: ${QO.esc(p.bank_bin)}</p>
        <p class="meta" style="margin-top:12px">${manual ? 'Sau khi chuyển, quán kiểm tra tiền vào và xác nhận.' : 'Hệ thống sẽ tự xác nhận qua xAPI khi thấy tiền vào.'} Thanh toán trước ${QO.esc(expires)}. Giữ nguyên số tiền và nội dung. Nếu đã chuyển, hãy chờ hệ thống kiểm tra và không chuyển thêm.</p></section>`;
    } else {
      root.innerHTML = `<section class="card"><span class="tag no">${p.state === 'EXPIRED' ? 'Phiếu đã hết hạn' : 'Cần quán đối soát'}</span>
        <h2 style="margin-top:12px">${QO.esc(p.shop_name)}</h2><p style="margin-top:12px">${p.state === 'EXPIRED' ? 'Không chuyển tiền theo phiếu này nữa. Nếu đã chuyển tiền, liên hệ quán và cung cấp mã bên dưới để kiểm tra.' : 'Đã phát hiện giao dịch cần kiểm tra thêm. Chưa tự gửi đơn cho quán. Vui lòng không chuyển thêm tiền.'}</p>
        <p style="overflow-wrap:anywhere;margin-top:12px"><b>Mã thanh toán:</b> ${QO.esc(p.transfer_code)}</p><p><b>Liên hệ quán:</b> ${QO.esc(p.shop_phone)}</p><a class="btn ghost" style="margin-top:12px" href="cart.html">Quay lại giỏ</a></section>`;
    }
    if (p.state !== 'WAITING' && timer) clearInterval(timer);
  };
  const check = async () => {
    if (busy || stopped || state === 'PAID') return;
    busy = true; button.disabled = true;
    try {
      const p = await QO.api('POST', 'payments/' + id + '/check', {token});
      if (stopped) return;
      render(p); showError('');
      if (p.state !== 'PAID' && token) {
        const stored = QO.savePendingPayment({...saved, id, token, shop_name: p.shop_name});
        if (stored && fragment) history.replaceState(null, '', location.pathname + location.search);
      }
      $('payment-updated').textContent = p.state === 'PAID'
        ? 'Đã xác nhận thanh toán. Bạn có thể mở Theo dõi đơn hàng để xem quán xử lý đơn.'
        : 'Kiểm tra lúc ' + new Date().toLocaleTimeString('vi-VN') + (p.state === 'WAITING' ? (p.verification_mode === 'MANUAL' ? ' · Đang chờ chủ quán xác nhận' : ' · Tự kiểm tra mỗi 5 giây') : '');
    } catch (e) {
      if (!stopped) {
        // Mất kết nối xAPI không làm mất QR đã tạo; tiếp tục thử lại, tuyệt đối không báo thành công.
        if (!state) { try { const p = await QO.api('GET', 'payments/' + id + '?token=' + encodeURIComponent(token)); if (!stopped) render(p); } catch {} }
        showError(e.message);
      }
    }
    finally { busy = false; if (!stopped) button.disabled = state === 'PAID'; }
  };
  root.onclick = async e => {
    const copy = e.target.closest('[data-copy]');
    if (copy) { try { await navigator.clipboard.writeText(copy.dataset.copy); QO.toast('Đã sao chép nội dung chuyển khoản'); } catch { QO.toast('Hãy chọn và sao chép nội dung chuyển khoản hiển thị phía trên.'); } }
  };
  button.onclick = check;
  document.addEventListener('visibilitychange', () => { if (!document.hidden && state !== 'PAID') check(); });
  window.addEventListener('pagehide', () => { stopped = true; clearInterval(timer); });
  window.addEventListener('pageshow', e => { if (e.persisted) location.reload(); });
  timer = setInterval(() => { if (!document.hidden && (!state || state === 'WAITING')) check(); }, 5000);
  await check();
})();
