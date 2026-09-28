import { describe, it, expect, vi } from 'vitest';
import { ApiError, createApi } from './api';

const session = { id: 'operator', login_provider: 'kakao', is_operator: true, has_beta_access: false };
const response = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

describe('HTTP boundary', () => {
  it('sends same-origin credentials and surfaces status without leaking server details', async () => {
    const request = vi.fn().mockResolvedValue(response(500, { detail: 'secret internal trace' }));
    const api = createApi({ request });
    await expect(api.issue()).rejects.toMatchObject({ status: 500 });
    expect(request).toHaveBeenCalledWith('/admin/invitations', expect.objectContaining({ method: 'POST', credentials: 'same-origin' }));
    expect(request).toHaveBeenCalledTimes(1);
    expect(new ApiError(500).message).not.toContain('secret');
  });

  it('supports no-content logout and session read', async () => {
    const request = vi.fn().mockResolvedValueOnce(response(200, session)).mockResolvedValueOnce(response(204));
    const api = createApi({ request });
    expect(await api.session()).toEqual(session);
    await expect(api.logout()).resolves.toBeUndefined();
  });

  it('uses cookie credentials for invitation redemption and stored analysis reads', async () => {
    const request = vi.fn()
      .mockResolvedValueOnce(response(200, { ...session, has_beta_access: true }))
      .mockResolvedValueOnce(response(200, []));
    const api = createApi({ request });
    await expect(api.redeem('invite-code')).resolves.toMatchObject({ has_beta_access: true });
    await expect(api.analysisHistory('MSFT', 20)).resolves.toEqual([]);
    expect(request.mock.calls[0][0]).toBe('/auth/web/invitations/redeem');
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ code: 'invite-code' });
    expect(request.mock.calls[1][0]).toBe('/stocks/MSFT/analysis?limit=20&offset=20');
    expect(request.mock.calls[1][1]).toEqual({ credentials: 'same-origin' });
  });
});

describe('browser login', () => {
  function setup(request: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>, clock = () => 0) {
    const popup = { closed: false, location: { href: '' }, close: vi.fn(), opener: {} };
    const api = createApi({ request, openWindow: () => popup as unknown as Window, now: clock, wait: async () => {}, makeProof: async () => ({ verifier: 'private-proof', challenge: 'public-challenge' }) });
    return { api, popup };
  }

  it('uses challenge then verifier and polls pending until completion', async () => {
    const request = vi.fn()
      .mockResolvedValueOnce(response(201, { attempt_id: 'a', authorization_url: 'https://kauth.kakao.com/login', expires_at: '2030-01-01T00:00:00Z' }))
      .mockResolvedValueOnce(response(202))
      .mockResolvedValueOnce(response(200, session));
    const { api, popup } = setup(request);
    expect(await api.login()).toEqual(session);
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ verifier_challenge: 'public-challenge' });
    expect(JSON.parse(request.mock.calls[1][1].body)).toEqual({ verifier: 'private-proof' });
    expect(request.mock.calls[1][0]).toBe('/auth/web/login-attempts/a/exchange');
    expect(popup.opener).toBeNull();
    expect(popup.close).toHaveBeenCalled();
  });

  it('accepts a completed exchange after the provider popup closes', async () => {
    const request = vi.fn()
      .mockResolvedValueOnce(response(201, { attempt_id: 'a', authorization_url: 'https://kauth.kakao.com/login', expires_at: '2030-01-01T00:00:00Z' }))
      .mockResolvedValueOnce(response(200, session));
    const { api, popup } = setup(request);
    popup.closed = true;

    await expect(api.login()).resolves.toEqual(session);
    expect(request).toHaveBeenCalledTimes(2);
  });

  it('stops polling when a pending exchange is followed by a closed popup', async () => {
    const request = vi.fn()
      .mockResolvedValueOnce(response(201, { attempt_id: 'a', authorization_url: 'https://kauth.kakao.com/login', expires_at: '2030-01-01T00:00:00Z' }))
      .mockResolvedValueOnce(response(202));
    const { api, popup } = setup(request);
    popup.closed = true;

    await expect(api.login()).rejects.toThrow('팝업');
    expect(request).toHaveBeenCalledTimes(2);
  });

  it('expires locally without an exchange or automatic restart', async () => {
    const request = vi.fn().mockResolvedValueOnce(response(201, { attempt_id: 'a', authorization_url: 'https://kauth.kakao.com/login', expires_at: '2000-01-01T00:00:00Z' }));
    const { api } = setup(request, () => Date.now());
    await expect(api.login()).rejects.toThrow('만료');
    expect(request).toHaveBeenCalledTimes(1);
  });

  it('reports blocked popups before creating a login attempt', async () => {
    const request = vi.fn();
    const api = createApi({ request, openWindow: () => null });
    await expect(api.login()).rejects.toThrow('팝업');
    expect(request).not.toHaveBeenCalled();
  });

  it.each([401, 410])('does not retry rejected exchanges (%s)', async status => {
    const request = vi.fn()
      .mockResolvedValueOnce(response(201, { attempt_id: 'a', authorization_url: 'https://kauth.kakao.com/login', expires_at: '2030-01-01T00:00:00Z' }))
      .mockResolvedValueOnce(response(status));
    const { api, popup } = setup(request);
    await expect(api.login()).rejects.toMatchObject({ status });
    expect(request).toHaveBeenCalledTimes(2);
    expect(popup.close).toHaveBeenCalled();
  });

  it('cancels polling and closes the popup when the caller aborts', async () => {
    const controller = new AbortController();
    const request = vi.fn()
      .mockResolvedValueOnce(response(201, { attempt_id: 'a', authorization_url: 'https://kauth.kakao.com/login', expires_at: '2030-01-01T00:00:00Z' }))
      .mockResolvedValueOnce(response(202));
    const popup = { closed: false, location: { href: '' }, close: vi.fn(), opener: {} };
    const api = createApi({
      request,
      openWindow: () => popup as unknown as Window,
      now: () => 0,
      makeProof: async () => ({ verifier: 'private-proof', challenge: 'public-challenge' }),
      wait: async (_milliseconds, signal) => {
        controller.abort();
        throw signal?.reason ?? new DOMException('cancelled', 'AbortError');
      },
    });

    await expect(api.login(controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    expect(request).toHaveBeenCalledTimes(2);
    expect(popup.close).toHaveBeenCalledTimes(1);
  });
});
