/* Phiếu QR tách khỏi bộ lọc trạng thái đơn; tài khoản xem lại được trên thiết bị khác. */
(async () => {
  const root = document.getElementById('pending-payments');
  if (!root) return;
  const local = QO.getPendingPayments(), by = new Map();
  await Promise.all(local.map(async p => {
    try { by.set(p.id, {...await QO.api('GET', 'payments/' + p.id + '?token=' + encodeURIComponent(p.token || '')), token: p.token}); }
    catch (e) { if (e.name !== 'NotFound') by.set(p.id, {...p, state: 'UNKNOWN'}); }
  }));
  const me = await QO.session();
  if (me?.role === 'customer') {
    try { for (const p of await QO.api('GET', 'payments/mine')) by.set(p.id, {...by.get(p.id), ...p}); } catch {}
  }
  for (const p of by.values()) {
    if (p.state === 'PAID' && p.order) {
      QO.addOrder({id: p.order.id, token: p.token || '', shop_id: p.shop_id, shop_name: p.shop_name, payment_id: p.id});
      QO.forgetPendingPayment(p.id);
    }
  }
  const rows = [...by.values()];
  if (!rows.length) return;
  const labels = {WAITING: 'Chờ thanh toán', EXPIRED: 'Đã hết hạn', REVIEW: 'Cần đối soát', PAID: 'Đã thanh toán', UNKNOWN: 'Chưa tải được'};
  root.hidden = false;
  root.innerHTML = '<h2>Phiếu chuyển khoản</h2><p class="meta">Phiếu chờ thanh toán chưa phải đơn đã gửi cho quán.</p>' + rows.map(p =>
    `<article class="card" style="margin-top:10px"><div class="row"><b>${QO.esc(p.shop_name || 'Quán')}</b><span class="tag">${labels[p.state] || ''}</span></div><p>${p.amount ? QO.money(p.amount) : ''} ${QO.esc(p.transfer_code || '')}</p><a class="btn ghost sm" href="${QO.esc(QO.paymentUrl(p.id, p.token || ''))}">${p.state === 'WAITING' ? 'Tiếp tục thanh toán' : 'Xem kết quả'}</a></article>`).join('');
})();
