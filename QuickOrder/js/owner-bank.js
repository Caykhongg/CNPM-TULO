/* Chủ quán tự lưu ngân hàng/token: không đưa thông tin bí mật vào localStorage hoặc đọc lại ra giao diện. */
(async () => {
  const $ = id => document.getElementById(id), form = $('bank-form');
  if (!form) return;
  const user = await QO.requireOwner(); if (!user) return;
  let shop, config = null, saving = false, queueBusy = false, stopped = false;
  const error = (id, text) => { $(id).textContent = text; $(id).hidden = !text; };
  const showConfig = value => {
    config = value;
    $('bank-bin').value = value.bank_bin || '';
    $('bank-number').value = value.account_number || '';
    $('bank-name').value = value.account_name || '';
    $('bank-token').value = '';
    $('bank-token').placeholder = value.has_token ? 'Đã lưu token. Để trống để giữ kết nối hiện tại.' : 'Để trống: xác nhận thủ công';
    $('bank-status').textContent = value.message;
    $('test-bank').hidden = $('manual-bank').hidden = value.mode !== 'AUTO';
  };
  const queue = async () => {
    if (!shop || queueBusy || stopped) return;
    queueBusy = true;
    try {
      const rows = await QO.api('GET', `shops/${shop.id}/payment-checkouts`);
      if (stopped) return;
      $('bank-queue').innerHTML = rows.length ? rows.map(p => `<article style="padding:14px 0;border-top:1px solid var(--line)"><div class="row"><b>${QO.esc(p.transfer_code)}</b><span class="tag wait">${p.can_confirm ? 'Quán xác nhận thủ công' : 'Tự động qua xAPI'}</span></div><p>${QO.esc(p.customer_name)} · <b class="price">${QO.money(p.amount)}</b></p><p class="meta">Tài khoản nhận: ${QO.esc(p.account_number)} · Nội dung: ${QO.esc(p.transfer_code)}</p>${p.can_confirm ? `<button type="button" class="btn sm" data-confirm-payment="${p.id}" data-code="${QO.esc(p.transfer_code)}" data-amount="${p.amount}">Đã kiểm tra và nhận đủ tiền</button>` : '<p class="meta">Chưa gửi đơn cho tới khi xAPI xác nhận giao dịch khớp.</p>'}</article>`).join('') : 'Chưa có phiếu chuyển khoản đang chờ.';
      error('bank-queue-error', '');
    } catch (e) { error('bank-queue-error', e.message); }
    finally { queueBusy = false; }
  };
  const load = async () => {
    shop = await QO.myShop();
    $('save-bank').disabled = !shop;
    if (!shop) { $('bank-status').textContent = 'Lưu thông tin quán ở phía trên trước khi thêm ngân hàng.'; return; }
    showConfig(await QO.api('GET', `shops/${shop.id}/payment-config`));
    await queue();
  };
  try {
    const data = await QO.api('GET', 'payment-banks');
    $('bank-bin').innerHTML = '<option value="">Chọn ngân hàng</option>' + data.banks.map(b => `<option value="${QO.esc(b.bin)}">${QO.esc(b.name)} — ${QO.esc(b.full_name)}</option>`).join('');
    await load();
  } catch (e) { error('bank-error', e.message); }
  const save = async forceManual => {
    if (!shop || saving) return;
    saving = true; $('save-bank').disabled = true; error('bank-error', '');
    const credential = $('bank-token').value.trim(), bank = $('bank-bin').value, account = $('bank-number').value.trim();
    const keep = config?.mode === 'AUTO' && config.bank_bin === bank && config.account_number === account;
    const mode = forceManual ? 'MANUAL' : (credential || keep ? 'AUTO' : 'MANUAL');
    $('bank-status').textContent = mode === 'AUTO' ? 'Đang kiểm tra và kết nối xAPI...' : 'Đang lưu ngân hàng...';
    try {
      const result = await QO.api('PUT', `shops/${shop.id}/payment-config`, {
        bank_bin: bank, account_number: account, account_name: $('bank-name').value.trim(), mode,
        credential: mode === 'AUTO' ? credential : '',
      });
      showConfig(result); QO.toast('Đã lưu ngân hàng · ' + (mode === 'AUTO' ? 'Xác nhận tự động' : 'Xác nhận thủ công'));
      await queue();
    } catch (e) { error('bank-error', e.message); $('bank-status').textContent = config?.message || 'Chưa lưu cấu hình ngân hàng.'; }
    finally { $('bank-token').value = ''; saving = false; $('save-bank').disabled = false; }
  };
  form.onsubmit = async e => { e.preventDefault(); await save(false); };
  $('manual-bank').onclick = () => save(true);
  $('test-bank').onclick = async () => {
    $('test-bank').disabled = true; error('bank-error', '');
    try { const r = await QO.api('POST', `shops/${shop.id}/payment-config/test`, {}); $('bank-status').textContent = r.message + ' (' + r.transaction_count + ' giao dịch)'; }
    catch (e) { error('bank-error', e.message); }
    finally { $('test-bank').disabled = false; }
  };
  $('load-bank-queue').onclick = queue;
  $('bank-queue').onclick = async e => {
    const b = e.target.closest('[data-confirm-payment]'); if (!b || !shop) return;
    const tid = prompt('Chỉ xác nhận sau khi kiểm tra TIỀN VÀO đúng ' + QO.money(b.dataset.amount) + ' và nội dung ' + b.dataset.code + '. Nhập mã giao dịch ngân hàng:');
    if (!tid) return;
    b.disabled = true; error('bank-queue-error', '');
    try {
      const p = await QO.api('POST', `shops/${shop.id}/payment-checkouts/${b.dataset.confirmPayment}/confirm`, {transaction_id: tid.trim()});
      QO.toast(p.state === 'PAID' ? 'Đã xác nhận thanh toán và gửi đơn #' + p.order_id : 'Đã ghi nhận tiền, cần kiểm tra mục đối soát.');
      await queue();
    } catch (e) { error('bank-queue-error', e.message); b.disabled = false; }
  };
  document.addEventListener('qo:shop-saved', () => load().catch(e => error('bank-error', e.message)));
  document.addEventListener('visibilitychange', () => { if (!document.hidden) queue(); });
  const timer = setInterval(() => { if (!document.hidden) queue(); }, 5000);
  window.addEventListener('pagehide', () => { stopped = true; clearInterval(timer); });
})();
