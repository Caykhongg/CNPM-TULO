/* Foodie - shared application logic */

const CART_KEY = 'foodie_cart';

const defaultCart = [
    { title: 'Bún bò Huế đặc biệt', price: 55000, qty: 1 },
    { title: 'Trà tắc khổng lồ', price: 15000, qty: 1 }
];

function getCart() {
    try {
        const saved = localStorage.getItem(CART_KEY);
        return saved ? JSON.parse(saved) : structuredClone(defaultCart);
    } catch {
        return structuredClone(defaultCart);
    }
}

function saveCart(cart) {
    localStorage.setItem(CART_KEY, JSON.stringify(cart));
}

function navigateCustomerTab(screen) {
    const routes = {
        welcome: 'welcome.html',
        home: 'home.html',
        search: 'search.html',
        restaurant: 'restaurant.html',
        cart: 'cart.html',
        tracking: 'tracking.html',
        profile: 'profile.html'
    };
    if (routes[screen]) window.location.href = routes[screen];
}

function navigateMerchantTab(screen) {
    const routes = {
        login: 'login.html',
        dashboard: 'dashboard.html',
        menu: 'menu.html',
        orders: 'orders.html',
        analytics: 'analytics.html',
        profile: 'profile.html'
    };
    if (routes[screen]) window.location.href = routes[screen];
}

function switchRole(role) {
    if (role === 'merchant') {
        window.location.href = '../merchant/login.html';
    } else {
        window.location.href = '../customer/home.html';
    }
}

function addToCart(title, price) {
    const cart = getCart();
    const existing = cart.find(item => item.title === title);

    if (existing) {
        existing.qty += 1;
    } else {
        cart.push({ title, price, qty: 1 });
    }

    saveCart(cart);
    updateCartUI();
    showToast(`Đã thêm ${title}`, 'success');
}

function changeCartQty(title, delta) {
    const cart = getCart();
    const item = cart.find(i => i.title === title);

    if (!item) return;

    item.qty += delta;

    const newCart = cart.filter(i => i.qty > 0);
    saveCart(newCart);
    updateCartUI();
    renderCart();
}

function clearCart() {
    saveCart([]);
    updateCartUI();
    renderCart();
    showToast('Đã xóa giỏ hàng', 'info');
}

function updateCartUI() {
    const cart = getCart();
    const totalItems = cart.reduce((sum, item) => sum + item.qty, 0);
    const totalPrice = cart.reduce((sum, item) => sum + item.price * item.qty, 0);

    const countBadge = document.getElementById('cart-badge-count');
    const totalBadge = document.getElementById('cart-badge-total');

    if (countBadge) countBadge.textContent = totalItems;
    if (totalBadge) totalBadge.textContent = totalPrice.toLocaleString('vi-VN') + 'đ';
}

function renderCart() {
    const container = document.getElementById('cart-items-container');
    if (!container) return;

    const cart = getCart();

    if (!cart.length) {
        container.innerHTML = `
            <div class="bg-white p-6 rounded-2xl border border-slate-100 text-center">
                <p class="text-sm font-semibold text-slate-500">Giỏ hàng đang trống</p>
                <button onclick="navigateCustomerTab('restaurant')"
                    class="mt-3 bg-foodie-red text-white px-4 py-2 rounded-xl text-xs font-bold">
                    Chọn món
                </button>
            </div>`;
        updateCartSummary(0);
        return;
    }

    container.innerHTML = cart.map(item => `
        <div class="bg-white p-3 rounded-2xl border border-slate-100 flex items-center justify-between gap-3">
            <div class="min-w-0">
                <h5 class="font-bold text-xs text-slate-800 truncate">${item.title}</h5>
                <p class="text-xs text-foodie-red font-bold mt-0.5">
                    ${item.price.toLocaleString('vi-VN')}đ
                </p>
            </div>
            <div class="flex items-center gap-2 bg-slate-100 px-2 py-1 rounded-xl shrink-0">
                <button onclick="changeCartQty('${item.title.replace(/'/g, "\\'")}', -1)"
                    class="w-5 h-5 text-slate-600 font-bold text-xs">-</button>
                <span class="text-xs font-bold text-slate-800">${item.qty}</span>
                <button onclick="changeCartQty('${item.title.replace(/'/g, "\\'")}', 1)"
                    class="w-5 h-5 text-slate-600 font-bold text-xs">+</button>
            </div>
        </div>
    `).join('');

    const subtotal = cart.reduce((sum, item) => sum + item.price * item.qty, 0);
    updateCartSummary(subtotal);
}

function updateCartSummary(subtotal) {
    const delivery = subtotal > 0 ? 15000 : 0;
    const total = subtotal + delivery;

    const subtotalEl = document.getElementById('cart-subtotal');
    const deliveryEl = document.getElementById('cart-delivery');
    const totalEl = document.getElementById('cart-total');

    if (subtotalEl) subtotalEl.textContent = subtotal.toLocaleString('vi-VN') + 'đ';
    if (deliveryEl) deliveryEl.textContent = delivery.toLocaleString('vi-VN') + 'đ';
    if (totalEl) totalEl.textContent = total.toLocaleString('vi-VN') + 'đ';
}

function showToast(message) {
    const toast = document.getElementById('app-toast');
    const text = document.getElementById('toast-message');

    if (!toast || !text) return;

    text.textContent = message;
    toast.classList.remove('opacity-0', 'translate-y-[-10px]');
    toast.classList.add('opacity-100', 'translate-y-0');

    clearTimeout(window.__foodieToastTimer);
    window.__foodieToastTimer = setTimeout(() => {
        toast.classList.remove('opacity-100', 'translate-y-0');
        toast.classList.add('opacity-0', 'translate-y-[-10px]');
    }, 2500);
}

function setActiveNav() {
    const file = window.location.pathname.split('/').pop().replace('.html', '');

    const customerMap = {
        home: 'cust-nav-home',
        tracking: 'cust-nav-tracking',
        cart: 'cust-nav-cart',
        profile: 'cust-nav-profile'
    };

    const merchantMap = {
        dashboard: 'merch-nav-dashboard',
        orders: 'merch-nav-orders',
        menu: 'merch-nav-menu',
        profile: 'merch-nav-profile'
    };

    const activeId = customerMap[file] || merchantMap[file];

    document.querySelectorAll('nav button').forEach(btn => {
        const isCustomer = btn.id.startsWith('cust-nav-');
        const activeClass = isCustomer ? 'text-foodie-red' : 'text-foodie-green';
        btn.classList.toggle(activeClass, btn.id === activeId);
        btn.classList.toggle('text-slate-400', btn.id !== activeId);
    });
}

document.addEventListener('DOMContentLoaded', () => {
    if (window.lucide) lucide.createIcons();
    updateCartUI();
    renderCart();
    setActiveNav();
});
