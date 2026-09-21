import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import { App } from './App';
import { ApiError, type WebApi } from './api';

const member = { id: 'my-account', login_provider: 'kakao', is_operator: false };
const operator = { ...member, is_operator: true };

function apiWith(overrides: Partial<WebApi> = {}): WebApi {
  return {
    session: vi.fn().mockResolvedValue(member),
    login: vi.fn().mockResolvedValue(operator),
    logout: vi.fn().mockResolvedValue(undefined),
    issue: vi.fn(),
    ...overrides,
  };
}

function show(api: WebApi, path = '/login') {
  render(<MemoryRouter initialEntries={[path]}><App api={api} /></MemoryRouter>);
}

describe('web session and login', () => {
  it('guides unauthenticated admin requests to login and does not issue', async () => {
    const api = apiWith({ session: vi.fn().mockRejectedValue(new ApiError(401)) });
    show(api, '/admin');
    expect(await screen.findByRole('button', { name: '카카오로 로그인' })).toBeVisible();
    expect(api.issue).not.toHaveBeenCalled();
  });

  it('shows a member their own account ID without an issuance button', async () => {
    show(apiWith(), '/admin');
    expect(await screen.findByText('운영자 권한이 필요합니다')).toBeVisible();
    expect(screen.getByText('my-account')).toBeVisible();
    expect(screen.queryByRole('button', { name: '초대 코드 발급' })).not.toBeInTheDocument();
  });

  it('does not treat a network failure as a logged-out session', async () => {
    const api = apiWith({ session: vi.fn().mockRejectedValue(new Error('offline')) });
    show(api);
    expect(await screen.findByRole('alert')).toHaveTextContent('연결');
    expect(screen.queryByRole('button', { name: '카카오로 로그인' })).not.toBeInTheDocument();
  });

  it('blocks duplicate login and transitions to the operator page', async () => {
    let finish!: (value: typeof operator) => void;
    const api = apiWith({
      session: vi.fn().mockRejectedValue(new ApiError(401)),
      login: vi.fn().mockImplementation(() => new Promise(resolve => { finish = resolve; })),
    });
    show(api);
    const login = await screen.findByRole('button', { name: '카카오로 로그인' });
    fireEvent.click(login);
    expect(login).toBeDisabled();
    fireEvent.click(login);
    expect(api.login).toHaveBeenCalledTimes(1);
    finish(operator);
    expect(await screen.findByRole('button', { name: '초대 코드 발급' })).toBeVisible();
  });

  it('reports failed login without authenticating', async () => {
    show(apiWith({
      session: vi.fn().mockRejectedValue(new ApiError(401)),
      login: vi.fn().mockRejectedValue(new Error('로그인 요청이 만료되었습니다. 다시 시도해 주세요.')),
    }));
    fireEvent.click(await screen.findByRole('button', { name: '카카오로 로그인' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('만료');
    expect(screen.queryByRole('button', { name: '초대 코드 발급' })).not.toBeInTheDocument();
  });

  it('logs out without retaining operator controls', async () => {
    const api = apiWith({ session: vi.fn().mockResolvedValue(operator) });
    show(api, '/admin');
    fireEvent.click(await screen.findByRole('button', { name: '로그아웃' }));
    await waitFor(() => expect(api.logout).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole('button', { name: '카카오로 로그인' })).toBeVisible();
  });

  it('clears local access when logout finds the server session already expired', async () => {
    const api = apiWith({
      session: vi.fn().mockResolvedValue(operator),
      logout: vi.fn().mockRejectedValue(new ApiError(401)),
    });
    show(api, '/admin');

    fireEvent.click(await screen.findByRole('button', { name: '로그아웃' }));
    expect(await screen.findByRole('button', { name: '카카오로 로그인' })).toBeVisible();
    expect(screen.queryByRole('button', { name: '초대 코드 발급' })).not.toBeInTheDocument();
  });
});
