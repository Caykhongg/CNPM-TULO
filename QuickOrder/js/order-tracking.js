/* Theo dõi một đơn: dữ liệu từ server, tự cập nhật 7 giây và hủy khi còn chờ xác nhận. */
QO.header('customer');
(async () => {
  const $ = id => document.getElementById(id);
  const root = $('tracking-root'), refresh = $('refresh-order'), error = $('tracking-error');
  const id = Number(QO.param('id'));
  const showError = message => { error.textContent = message; error.hidden = !message; };
  $('history-warning').hidden = QO.param('history') !== 'missing';
  if (!Number.isSafeInteger(id) || id < 1) {
    root.innerHTML = '<div class="empty"><b>Liên kết đơn không hợp lệ</b><a class="btn" href="orders.html">Mở danh sách đơn</a></div>';
    $('tracking-updated').textContent = '';
    refresh.disabled = true;
    return;
  }
  const saved = QO.getOrders().find(o => o.id === id);
  const fragmentToken = new URLSearchParams(location.hash.slice(1)).get('token') || '';
  const token = fragmentToken || saved?.token || '';
  const query = token ? '?token=' + encodeURIComponent(token) : '';
  let order = null, loading = false, cancelling = false, stopped = false;
  const descriptions = {
    PENDING: 'Quán đang chờ xác nhận đơn của bạn.',
    CONFIRMED: 'Quán đã nhận và đang chuẩn bị món.',
    PREPARING: 'Quán đã nhận và đang chuẩn bị món.',
    COMPLETED: 'Quán đã hoàn thành đơn của bạn.',
    CANCELLED: 'Đơn đã được hủy.'
  };
  const render = () => {
    if (!order) return;
    const o = order, [label, tone] = QO.ORDER_STATUS[o.status] || ['Không rõ', ''];
    const step = ['PENDING', 'PREPARING', 'COMPLETED'].indexOf(o.status === 'CONFIRMED' ? 'PREPARING' : o.status);
    const steps = o.status === 'CANCELLED' ? '' : '<ol class="order-steps" aria-label="Tiến trình đơn hàng">' +
      ['Chờ xác nhận', 'Đang làm', 'Hoàn thành'].map((name, i) => `<li class="${i < step ? 'done' : i === step ? 'current' : ''}"${i === step ? ' aria-current="step"' : ''}><span class="step-number">${i + 1}</span>${name}</li>`).join('') + '</ol>';
    const table = o.table_number || saved?.table_number;
    $('tracking-title').textContent = 'Theo dõi đơn #' + o.id;
    document.title = 'Đơn #' + o.id + ' - QuickOrder';
    root.innerHTML = `<section class="card">
      <div class="row"><div><h2>${QO.esc(o.shop_name || saved?.shop_name || 'Quán')}</h2><span class="meta">${table ? QO.esc(QO.tableLabel(table)) + ' · ' : ''}${QO.esc(QO.fmtTime(o.created_at))}</span></div><span class="tag ${tone}">${label}</span></div>
      <p style="margin-top:12px">${descriptions[o.status] || ''}</p>${steps}
      ${o.status === 'CANCELLED' && o.cancel_reason ? `<p class="tracking-note" style="margin-top:12px"><b>Lý do hủy:</b> ${QO.esc(o.cancel_reason)}</p>` : ''}
      <div class="tracking-actions">${o.status === 'PENDING' ? `<button class="btn bad" type="button" id="cancel-order"${loading || cancelling ? ' disabled' : ''}>${cancelling ? 'Đang hủy...' : 'Hủy đơn'}</button>` : ''}
        ${o.status !== 'PENDING' ? '<button class="btn ghost" type="button" id="complain-order">Xem / gửi khiếu nại</button>' : ''}
        <a class="btn ghost" href="orders.html">Danh sách đơn</a></div>
    </section>
    <section class="card"><h2>Món đã đặt</h2><ul class="tracking-items">${o.items.map(i => `<li><div><b>${i.quantity} × ${QO.esc(i.dish_name)}</b>${i.note ? `<div class="meta tracking-note">${QO.esc(i.note)}</div>` : ''}</div><span class="price">${QO.money(i.quantity * i.unit_price)}</span></li>`).join('')}</ul>
      ${o.note ? `<p class="tracking-note" style="margin-top:12px"><b>Ghi chú:</b> ${QO.esc(o.note)}</p>` : ''}
      <div class="tracking-total">${o.discount_amount ? `<div class="row meta"><span>Tạm tính</span><span>${QO.money(o.total_amount + o.discount_amount)}</span></div><div class="row meta"><span>Giảm giá (${QO.esc(o.coupon_code)})</span><span>−${QO.money(o.discount_amount)}</span></div>` : ''}
        <div class="row"><b>Tổng cộng</b><span class="price">${QO.money(o.total_amount)}</span></div>
        <p class="meta" style="margin-top:8px">${QO.PAY_METHOD[o.payment_method] || ''} · ${o.payment_status === 'PAID' ? 'Đã thanh toán' : 'Chưa thanh toán'}</p></div>
    </section>`;
  };
  const load = async () => {
    if (loading || cancelling || stopped) return;
    loading = true; refresh.disabled = true;
    const cancel = $('cancel-order'); if (cancel) cancel.disabled = true;
    try {
      const result = await QO.api('GET', 'orders/' + id + query);
      if (stopped) return;
      order = result;
      if (token) {
        const stored = QO.addOrder({id, token, shop_id: result.shop_id, shop_name: result.shop_name, table_number: result.table_number});
        if (stored && fragmentToken && location.hash) history.replaceState(null, '', location.pathname + location.search);
      }
      showError('');
      $('tracking-updated').textContent = 'Tự cập nhật mỗi 7 giây · Cập nhật lúc ' + new Date().toLocaleTimeString('vi-VN');
    } catch (e) {
      if (stopped) return;
      showError(e.name === 'NotFound' ? 'Không tìm thấy đơn hoặc bạn chưa có quyền xem. Hãy mở trên trình duyệt đã đặt hoặc đăng nhập đúng tài khoản khách.' : 'Chưa tải được trạng thái mới nhất. Bạn có thể bấm Tải lại hoặc đợi lần cập nhật tiếp theo.');
      if (e.name === 'NotFound') order = null;
      if (!order) root.innerHTML = '<div class="empty"><b>Chưa tải được đơn hàng</b><a href="orders.html">Mở danh sách đơn của bạn</a></div>';
    } finally {
      loading = false;
      if (!stopped) { refresh.disabled = false; render(); }
    }
  };
  root.onclick = async e => {
    if (e.target.closest('#complain-order')) { QO.complaintDialog({orderId: id, token}); return; }
    if (!e.target.closest('#cancel-order') || !order || order.status !== 'PENDING' || loading || cancelling) return;
    if (!confirm('Hủy đơn #' + id + '? Chỉ hủy được khi quán chưa xác nhận.')) return;
    cancelling = true; render(); showError('');
    let failure = '';
    try {
      order = {...order, ...await QO.api('PUT', 'orders/' + id + '/cancel', {token})};
      QO.toast('Đã hủy đơn #' + id);
    } catch (err) { failure = err.message; }
    finally {
      cancelling = false; render();
      await load(); // Nếu quán vừa xác nhận, lấy lại trạng thái để bỏ nút hủy ngay.
      if (failure) showError(failure);
    }
  };
  refresh.onclick = load;
  document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });
  const timer = setInterval(() => { if (!document.hidden) load(); }, 7000);
  window.addEventListener('pagehide', () => { stopped = true; clearInterval(timer); });
  window.addEventListener('pageshow', e => { if (e.persisted) location.reload(); });
  await load();
})();
