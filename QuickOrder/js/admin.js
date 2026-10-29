/* Đăng nhập và điều hướng dùng chung cho Admin. */
const Admin = (() => {
  const $ = id => document.getElementById(id);

  const roles = {
    admin: 'Quản trị viên',
    owner: 'Chủ quán',
    customer: 'Khách hàng'
  };

  const error = err => {
    QO.toast(err.message || 'Có lỗi xảy ra. Vui lòng thử lại.');
  };

  const start = async load => {
    document.body.insertAdjacentHTML('afterbegin', `
      <header class="topbar">
        <div class="in">
          <span class="logo">Quick<b>Order</b> Admin</span>

          <nav class="nav" id="admin-nav" hidden>
            <a href="dashboard.html">Thống kê</a>
            <a href="shops.html">Quản lý quán</a>
            <a href="users.html">Người dùng</a>
            <a href="categories.html">Danh mục</a>
            <button type="button" id="admin-logout">
              Đăng xuất
            </button>
          </nav>
        </div>
      </header>
    `);

    const root = document.querySelector('.wrap');

    root.insertAdjacentHTML('afterbegin', `
      <form class="card" id="admin-login"
            hidden style="max-width:440px;margin-bottom:24px">
        <h2>Đăng nhập quản trị</h2>

        <label class="field">
          <span>Email quản trị</span>
          <input name="email" type="email"
                 required autocomplete="username">
        </label>

        <label class="field">
          <span>Mật khẩu</span>
          <input name="password" type="password"
                 required autocomplete="current-password">
        </label>

        <p class="err" id="admin-login-error"
           role="alert"></p>

        <button class="btn">Đăng nhập</button>
      </form>

      <p class="err" id="admin-page-error"
         role="alert"></p>
    `);

    const form = $('admin-login');
    const panel = $('app');

    const showApp = async user => {
      form.hidden = true;
      panel.hidden = false;
      $('admin-nav').hidden = false;
      $('admin-page-error').textContent = '';

      try {
        await load(user);
      } catch (err) {
        $('admin-page-error').textContent = err.message;
      }
    };

    $('admin-logout').onclick = async () => {
      try {
        await QO.api('POST', 'logout');
        location.reload();
      } catch (err) {
        error(err);
      }
    };

    form.onsubmit = async event => {
      event.preventDefault();

      const button = form.querySelector('button');
      button.disabled = true;
      $('admin-login-error').textContent = '';

      try {
        const data = Object.fromEntries(new FormData(form));

        const user = await QO.api('POST', 'login', {
          email: data.email.trim(),
          password: data.password
        });

        if (user.role !== 'admin') {
          await QO.api('POST', 'logout');
          throw new Error(
            'Tài khoản này không có quyền quản trị.'
          );
        }

        form.reset();
        await showApp(user);
      } catch (err) {
        $('admin-login-error').textContent = err.message;
      } finally {
        button.disabled = false;
      }
    };

    const user = await QO.session();

    if (user && user.role === 'admin') {
      await showApp(user);
    } else {
      form.hidden = false;
      panel.hidden = true;
    }
  };

  return {$, roles, error, start};
})();