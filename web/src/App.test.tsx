import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { ApiError, type WebApi } from './api';

const member = { id: 'my-account', login_provider: 'kakao', is_operator: false, has_beta_access: false };
const betaMember = { ...member, has_beta_access: true };
const operator = { ...member, is_operator: true };
const watchlist = [{ id: 1, symbol: 'MSFT', created_at: '2030-01-01T00:00:00Z' }];
const history = [{ id: 3, symbol: 'MSFT', analyzed_at: '2030-01-02T00:00:00Z', data_timestamp: null, overall_judgment: '매수 관망', summary: '저장된 결과', should_alert: false, triggered_alerts: [], shared_safe: true }];

function apiWith(overrides: Partial<WebApi> = {}): WebApi {
  return {
    session: vi.fn().mockResolvedValue(member),
    login: vi.fn().mockResolvedValue(member),
    logout: vi.fn().mockResolvedValue(undefined),
    issue: vi.fn(),
    redeem: vi.fn().mockResolvedValue(betaMember),
    watchlist: vi.fn().mockResolvedValue([]),
    addWatchlist: vi.fn().mockResolvedValue(watchlist[0]),
    removeWatchlist: vi.fn().mockResolvedValue(undefined),
    analysisHistory: vi.fn().mockResolvedValue([]),
    analysisDetail: vi.fn().mockResolvedValue({ ...history[0], key_reasons: ['추세 회복'], risk_factors: ['변동성'], support_levels: {}, alert_reason: null, raw_result: { internal: 'hidden' } }),
    ...overrides,
  };
}

function show(api: WebApi, path = '/login') {
  render(<MemoryRouter initialEntries={[path]}><App api={api} /></MemoryRouter>);
}

describe('beta web routes', () => {
  it('redirects an anonymous service request to login', async () => {
    show(apiWith({ session: vi.fn().mockRejectedValue(new ApiError(401)) }), '/app');
    expect(await screen.findByRole('button', { name: '카카오로 로그인' })).toBeVisible();
  });

  it('sends an authenticated account without a grant to its invitation page and displays its ID', async () => {
    show(apiWith(), '/login');
    expect(await screen.findByRole('heading', { name: '초대 코드를 등록하세요' })).toBeVisible();
    expect(screen.getByText('my-account')).toBeVisible();
  });

  it('keeps operator issuance reachable while the operator still needs a beta grant', async () => {
    show(apiWith({ session: vi.fn().mockResolvedValue(operator) }), '/invite');
    expect(await screen.findByRole('link', { name: '초대 발급' })).toBeVisible();
    fireEvent.click(screen.getByRole('link', { name: '초대 발급' }));
    expect(await screen.findByRole('button', { name: '초대 코드 발급' })).toBeVisible();
  });

  it('redeems an invitation and opens the saved-analysis service', async () => {
    const api = apiWith();
    show(api, '/invite');
    fireEvent.change(await screen.findByLabelText('초대 코드'), { target: { value: 'beta-code' } });
    fireEvent.click(screen.getByRole('button', { name: '초대 코드 등록' }));
    await waitFor(() => expect(api.redeem).toHaveBeenCalledWith('beta-code'));
    expect(await screen.findByRole('heading', { name: '내 관심 종목' })).toBeVisible();
  });

  it('reports an invalid invitation without granting access', async () => {
    show(apiWith({ redeem: vi.fn().mockRejectedValue(new ApiError(400)) }), '/invite');
    fireEvent.change(await screen.findByLabelText('초대 코드'), { target: { value: 'bad-code' } });
    fireEvent.click(screen.getByRole('button', { name: '초대 코드 등록' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('초대 코드를 확인');
    expect(screen.queryByRole('heading', { name: '내 관심 종목' })).not.toBeInTheDocument();
  });

  it('adds and removes watchlist items, then loads only saved history and its detail', async () => {
    const api = apiWith({ session: vi.fn().mockResolvedValue(betaMember), watchlist: vi.fn().mockResolvedValue(watchlist), analysisHistory: vi.fn().mockResolvedValue(history) });
    show(api, '/app');
    expect(await screen.findByRole('button', { name: 'MSFT 분석 이력' })).toBeVisible();
    expect(api.analysisHistory).toHaveBeenCalledWith('MSFT');
    fireEvent.click(screen.getByText('저장된 결과'));
    expect(await screen.findByRole('heading', { name: /MSFT · 매수 관망/ })).toBeVisible();
    expect(screen.queryByText('hidden')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('종목 코드'), { target: { value: 'AAPL' } });
    fireEvent.click(screen.getByRole('button', { name: '종목 추가' }));
    await waitFor(() => expect(api.addWatchlist).toHaveBeenCalledWith('AAPL'));
    fireEvent.click(screen.getByRole('button', { name: 'MSFT 삭제' }));
    await waitFor(() => expect(api.removeWatchlist).toHaveBeenCalledWith('MSFT'));
  });

  it('returns to login when a main-service call reports an expired session', async () => {
    show(apiWith({ session: vi.fn().mockResolvedValue(betaMember), watchlist: vi.fn().mockRejectedValue(new ApiError(401)) }), '/app');
    expect(await screen.findByRole('button', { name: '카카오로 로그인' })).toBeVisible();
  });

  it('logs out from the service without retaining beta content', async () => {
    const api = apiWith({ session: vi.fn().mockResolvedValue(betaMember) });
    show(api, '/app');
    fireEvent.click(await screen.findByRole('button', { name: '로그아웃' }));
    await waitFor(() => expect(api.logout).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole('button', { name: '카카오로 로그인' })).toBeVisible();
  });
});
