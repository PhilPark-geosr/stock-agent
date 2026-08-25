function createSessionStore({ safeStorage, files, tokenPath }) {
  let token = null;

  async function save(value) {
    if (!safeStorage.isEncryptionAvailable()) {
      token = value;
      return false;
    }
    const encrypted = safeStorage.encryptString(value);
    await files.writeFile(tokenPath, encrypted);
    token = value;
    return true;
  }

  async function restore() {
    if (!safeStorage.isEncryptionAvailable()) return null;
    try {
      const encrypted = await files.readFile(tokenPath);
      token = safeStorage.decryptString(encrypted);
      return token;
    } catch {
      token = null;
      return null;
    }
  }

  async function clear() {
    token = null;
    try {
      await files.unlink(tokenPath);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
  }

  return { save, restore, clear, current: () => token };
}

function parsePayload(text) {
  if (!text) return null;
  try { return JSON.parse(text); } catch { return text; }
}

function createAuthenticatedRequester({ fetchImpl, getToken, clearToken, onExpired }) {
  return async function request(url, { method = "GET", body, timeout = 120000 } = {}) {
    const token = getToken();
    const headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetchImpl(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(timeout)
    });
    const payload = parsePayload(await response.text());
    if (response.status === 401 && token) {
      await clearToken();
      onExpired();
    }
    if (!response.ok) {
      const detail = typeof payload?.detail === "string" ? payload.detail : JSON.stringify(payload?.detail || payload);
      throw new Error(detail || `Backend request failed (${response.status})`);
    }
    return { status: response.status, payload };
  };
}

module.exports = { createSessionStore, createAuthenticatedRequester };
