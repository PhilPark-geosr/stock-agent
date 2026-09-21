export interface Session {
  id: string;
  login_provider: string;
  is_operator: boolean;
}

export interface Invitation {
  code: string;
  expires_at: string;
}

export interface WebApi {
  session(): Promise<Session>;
  login(signal?: AbortSignal): Promise<Session>;
  logout(): Promise<void>;
  issue(): Promise<Invitation>;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`요청을 처리하지 못했습니다. (${status})`);
    this.name = 'ApiError';
    this.status = status;
  }
}

interface LoginAttempt {
  attempt_id: string;
  authorization_url: string;
  expires_at: string;
}

interface Proof {
  verifier: string;
  challenge: string;
}

type RequestCallback = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

interface ApiOptions {
  request?: RequestCallback;
  openWindow?: () => Window | null;
  now?: () => number;
  wait?: (milliseconds: number, signal?: AbortSignal) => Promise<void>;
  makeProof?: () => Promise<Proof>;
}

const jsonHeaders = { 'Content-Type': 'application/json' };

function base64Url(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function defaultProof(): Promise<Proof> {
  const verifierBytes = new Uint8Array(32);
  crypto.getRandomValues(verifierBytes);
  const verifier = base64Url(verifierBytes);
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return { verifier, challenge: base64Url(new Uint8Array(digest)) };
}

function defaultWait(milliseconds: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(signal.reason ?? new DOMException('요청이 취소되었습니다.', 'AbortError'));
      return;
    }
    const finish = () => {
      signal?.removeEventListener('abort', abort);
      resolve();
    };
    const abort = () => {
      window.clearTimeout(timer);
      reject(signal?.reason ?? new DOMException('요청이 취소되었습니다.', 'AbortError'));
    };
    const timer = window.setTimeout(finish, milliseconds);
    signal?.addEventListener('abort', abort, { once: true });
  });
}

async function expectJson<T>(response: Response): Promise<T> {
  if (!response.ok) throw new ApiError(response.status);
  return response.json() as Promise<T>;
}

export function createApi(options: ApiOptions = {}): WebApi {
  const request: RequestCallback = options.request ?? fetch.bind(globalThis);
  const openWindow = options.openWindow ?? (() => window.open('', '_blank', 'popup,width=520,height=720'));
  const now = options.now ?? Date.now;
  const wait = options.wait ?? defaultWait;
  const makeProof = options.makeProof ?? defaultProof;

  return {
    async session() {
      const response = await request('/auth/web/session', { credentials: 'same-origin' });
      return expectJson<Session>(response);
    },

    async login(signal) {
      // Opening must happen in the click event before any asynchronous work, or
      // browsers may treat the provider window as an unsolicited popup.
      const popup = openWindow();
      if (!popup) throw new Error('로그인 팝업을 열 수 없습니다. 팝업 차단을 해제해 주세요.');
      popup.opener = null;

      try {
        const proof = await makeProof();
        if (signal?.aborted) throw signal.reason ?? new DOMException('요청이 취소되었습니다.', 'AbortError');

        const startResponse = await request('/auth/login-attempts', {
          method: 'POST',
          credentials: 'same-origin',
          headers: jsonHeaders,
          body: JSON.stringify({ verifier_challenge: proof.challenge }),
          signal,
        });
        const attempt = await expectJson<LoginAttempt>(startResponse);
        popup.location.href = attempt.authorization_url;
        const expiresAt = Date.parse(attempt.expires_at);

        while (now() < expiresAt) {
          if (signal?.aborted) throw signal.reason ?? new DOMException('요청이 취소되었습니다.', 'AbortError');

          const exchangeResponse = await request(`/auth/web/login-attempts/${encodeURIComponent(attempt.attempt_id)}/exchange`, {
            method: 'POST',
            credentials: 'same-origin',
            headers: jsonHeaders,
            body: JSON.stringify({ verifier: proof.verifier }),
            signal,
          });
          if (exchangeResponse.status === 202) {
            if (popup.closed) throw new Error('로그인 팝업이 닫혔습니다. 다시 시도해 주세요.');
            await wait(1000, signal);
            continue;
          }
          return await expectJson<Session>(exchangeResponse);
        }
        throw new Error('로그인 요청이 만료되었습니다. 다시 시도해 주세요.');
      } finally {
        if (!popup.closed) popup.close();
      }
    },

    async logout() {
      const response = await request('/auth/web/session', {
        method: 'DELETE',
        credentials: 'same-origin',
      });
      if (!response.ok) throw new ApiError(response.status);
    },

    async issue() {
      const response = await request('/admin/invitations', {
        method: 'POST',
        credentials: 'same-origin',
      });
      return expectJson<Invitation>(response);
    },
  };
}
