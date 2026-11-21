QO.header('customer');
(async () => {
  const $ = id => document.getElementById(id), id = QO.param('id');
  const root = $('payment-root'), error = $('payment-error'), button = $('check-payment'), updated = $('payment-updated');
  if (!/^[a-f0-9]{32}$/.test(id || '')) {
    root.innerHTML = '<div class="empty"><b>Liên kết thanh toán không hợp lệ</b><a class="btn" href="orders.html">Mở đơn hàng của bạn</a></div>';
    button.hidden = true;
    updated.textContent = '';
    return;
  }
  const saved = QO.getPendingPayments().find(p => p.id === id);
  const fragment = new URLSearchParams(location.hash.slice(1)).get('token') || '';
  const previous = QO.getOrders().find(o => o.payment_id === id);
  const token = fragment || saved?.token || previous?.token || '';
  let busy = false, stopped = false, state = '', timer;
  const showError = message => { error.textContent = message; error.hidden = !message; };
  const render = p => {
    // Giữ nguyên QR và nút sao chép khi lần kiểm tra tiếp theo vẫn trả về cùng phiếu.
    if (state === 'WAITING' && p.state === 'WAITING') return;
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
      root.innerHTML = `<section class="card payment-card payment-success">
        <div class="payment-checkmark" aria-hidden="true">✓</div><h2>Đơn #${o.id} đã gửi tới quán</h2>
        <p class="meta">${QO.esc(p.shop_name)}</p><p class="price">${QO.money(p.amount)}</p>
        <a class="btn" href="${QO.esc(href)}">Theo dõi đơn hàng</a>
      </section>`;
    } else if (p.state === 'WAITING') {
      const expires = new Date(p.expires_at * 1000).toLocaleTimeString('vi-VN');
      const manual = p.verification_mode === 'MANUAL';
      button.textContent = manual ? 'Tải lại trạng thái' : 'Kiểm tra thanh toán';
      root.innerHTML = `<section class="card payment-card">
        <div class="row"><h2>${QO.esc(p.shop_name)}</h2><span class="tag wait">${manual ? 'Chờ quán xác nhận thanh toán' : 'Chờ thanh toán'}</span></div>
        <div class="row"><b>Số tiền cần chuyển</b><span class="price">${QO.money(p.amount)}</span></div>
        <img class="payment-qr" src="${QO.esc(p.qr_url)}" alt="QR chuyển khoản có số tiền và nội dung riêng" referrerpolicy="no-referrer">
        <p class="meta">Quét bằng ứng dụng ngân hàng. Nếu đang dùng cùng điện thoại, hãy chụp màn hình rồi chọn ảnh QR trong ứng dụng ngân hàng nếu ứng dụng có hỗ trợ.</p>
        <dl class="payment-details">
          <div class="row"><div><dt class="meta">Nội dung chuyển khoản</dt><dd>${QO.esc(p.transfer_code)} <button class="btn ghost sm" type="button" data-copy="${QO.esc(p.transfer_code)}" aria-label="Sao chép nội dung chuyển khoản">Sao chép</button></dd></div></div>
          <div><dt class="meta">Tài khoản nhận · ${QO.esc(p.account_name)}</dt><dd>${QO.esc(p.account_number)}</dd></div>
        </dl>
        <p class="meta">Thanh toán trước ${QO.esc(expires)}. Kiểm tra người nhận, giữ nguyên số tiền và nội dung.</p>
        <p class="payment-message"><b>Đã chuyển tiền?</b> Quay lại trang này để xem kết quả. ${manual ? 'Quán sẽ xác nhận sau khi kiểm tra tiền vào.' : 'Trạng thái tự cập nhật khi phát hiện tiền vào.'} Chỉ chuyển một lần cho phiếu này.</p>
      </section>`;
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
      if (!state) {
        // Hiện ngay thông tin phiếu đã lưu trước khi chờ ngân hàng đối soát.
        const snapshot = await QO.api('GET', 'payments/' + id + '?token=' + encodeURIComponent(token)).catch(() => null);
        if (stopped) return;
        if (snapshot) render(snapshot);
        if (state === 'PAID') { showError(''); updated.textContent = ''; return; }
      }
      const p = await QO.api('POST', 'payments/' + id + '/check', {token});
      if (stopped) return;
      render(p); showError('');
      if (p.state !== 'PAID' && token) {
        const stored = QO.savePendingPayment({...saved, id, token, shop_name: p.shop_name});
        if (stored && fragment) history.replaceState(null, '', location.pathname + location.search);
      }
      updated.textContent = p.state === 'WAITING' ? 'Trạng thái tự cập nhật khi trang đang mở.' : '';
    } catch (e) {
      if (!stopped) {
        if (state === 'WAITING') {
          showError('Chưa kiểm tra được thanh toán. Nếu đã chuyển tiền, hãy chờ và thử kiểm tra lại.');
          updated.textContent = 'Trang sẽ tự kiểm tra lại.';
        } else if (state) {
          showError('');
          updated.textContent = '';
        } else {
          root.innerHTML = '<div class="empty"><b>Chưa tải được phiếu thanh toán</b><p>Kiểm tra kết nối hoặc mở lại phiếu từ mục Đơn hàng.</p></div>';
          showError(e.message);
          updated.textContent = '';
        }
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
