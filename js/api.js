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
