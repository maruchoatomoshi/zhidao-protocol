(function () {
  let csrfToken = '';

  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body && !(options.body instanceof Blob) && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    if (csrfToken && options.method && options.method !== 'GET') {
      headers.set('X-CSRF-Token', csrfToken);
    }
    const response = await fetch(path, { credentials: 'same-origin', ...options, headers });
    let data = null;
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) {
      const error = new Error(data?.detail || `Ошибка сети (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  async function login(username, secret) {
    const data = await request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, secret })
    });
    csrfToken = data.csrf_token;
    return data.user;
  }

  async function restore() {
    const data = await request('/api/auth/me');
    csrfToken = data.csrf_token;
    return data.user;
  }

  async function logout() {
    try { await request('/api/auth/logout', { method: 'POST' }); } finally { csrfToken = ''; }
  }

  function toast(message, type = '') {
    const element = document.getElementById('toast');
    if (!element) return;
    element.textContent = message;
    element.className = `toast show ${type}`;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { element.className = 'toast'; }, 2800);
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    })[char]);
  }

  window.ZHIDAO_API = { request, login, restore, logout, toast, escapeHtml };
})();
