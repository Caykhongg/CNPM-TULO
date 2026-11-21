(async () => {
  const button = document.getElementById('load-receipts'), root = document.getElementById('payment-receipts');
  const u = await QO.requireOwner();
  if (!u) return;
  const load = async () => {
    button.disabled = true;
    try {
      const shop = await QO.myShop();
      if (!shop) { root.textContent = 'Lưu thông tin quán trước.'; return; }
      const rows = await QO.api('GET', 'shops/' + shop.id + '/payment-receipts');
      root.innerHTML = rows.length ? rows.map(r => `<article style="border-top:1px solid var(--line);padding:12px 0"><b>${QO.esc(r.transfer_code)}</b><p>Đã nhận ${QO.money(r.amount)} · Cần trả ${QO.money(r.expected_amount)}</p><p class="meta">Giao dịch: ${QO.esc(r.transaction_id)}</p><p>${QO.esc(r.review_reason)}</p>${r.resolved_note ? '<p><b>Đã xử lý:</b> ' + QO.esc(r.resolved_note) + '</p>' : `<button class="btn ghost sm" data-resolve="${r.id}" data-shop="${shop.id}">Ghi nhận đã xử lý</button>`}</article>`).join('') : 'Chưa có giao dịch cần đối soát.';
    } catch (e) { root.textContent = e.message; }
    finally { button.disabled = false; }
  };
  button.onclick = load;
  root.onclick = async e => {
    const b = e.target.closest('[data-resolve]'); if (!b) return;
    const note = prompt('Ghi rõ đã liên hệ khách/hoàn tiền thủ công như thế nào. Thao tác này chỉ lưu ghi chú, không chuyển tiền.');
    if (!note) return;
    b.disabled = true;
    try { await QO.api('PUT', `shops/${b.dataset.shop}/payment-receipts/${b.dataset.resolve}/resolve`, {note}); await load(); }
    catch (e) { QO.toast(e.message); b.disabled = false; }
  };
  await load();
})();
