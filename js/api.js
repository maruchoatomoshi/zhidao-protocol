function getTelegramInitData() {
  try {
    return window.Telegram?.WebApp?.initData || '';
  } catch (e) {
    return '';
  }
}

function isApiRequest(input) {
  const url = typeof input === 'string' ? input : input?.url;
  return Boolean(url && (url.startsWith(API_URL) || url.startsWith('/api/')));
}

function withTelegramAuthHeaders(input, options = {}) {
  if (!isApiRequest(input)) return options;

  const headers = new Headers(options.headers || {});
  const initData = getTelegramInitData();
  if (initData && !headers.has('X-Telegram-Init-Data')) {
    headers.set('X-Telegram-Init-Data', initData);
  }

  if (currentUserId) {
    const identityHeader = isAdmin ? 'X-Admin-Id' : 'X-Telegram-Id';
    if (!headers.has(identityHeader)) {
      headers.set(identityHeader, String(currentUserId));
    }
  }

  if (typeof getActiveCohortCode === 'function' && !headers.has('X-Cohort-Code')) {
    headers.set('X-Cohort-Code', getActiveCohortCode());
  }

  return { ...options, headers };
}

(function installTelegramAuthFetchLayer() {
  if (window.__telegramAuthFetchInstalled) return;
  window.__telegramAuthFetchInstalled = true;

  const nativeFetch = window.fetch.bind(window);
  window.fetch = function telegramAuthFetch(input, options = {}) {
    return nativeFetch(input, withTelegramAuthHeaders(input, options));
  };
})();

async function apiFetch(path, options = {}) {
  return fetch(`${API_URL}${path}`, options);
}

async function apiGetJson(path, options = {}) {
  const response = await apiFetch(path, options);
  const data = await response.json();
  return { response, data };
}

async function apiGetJsonSafe(path, options = {}) {
  const response = await apiFetch(path, options);
  let data = null;
  try {
    data = await response.json();
  } catch (e) {}
  return { response, data };
}

async function apiPostJson(path, payload, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const response = await apiFetch(path, {
    ...options,
    method: options.method || 'POST',
    headers,
    body: JSON.stringify(payload)
  });
  let data = null;
  try {
    data = await response.json();
  } catch (e) {}
  return { response, data };
}

async function apiDelete(path, options = {}) {
  return apiFetch(path, {
    ...options,
    method: options.method || 'DELETE'
  });
}
