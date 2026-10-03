import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, type WebApi } from './api';
import { AlertConditionsPanel } from './components/AlertConditionsPanel';
import { NotificationConnectionPanel } from './components/NotificationConnectionPanel';
import { WatchlistPanel } from './components/WatchlistPanel';

afterEach(() => window.history.replaceState({}, '', '/'));

describe('reusable beta panels', () => {
  it('searches only the watchlist and adds an unsuffixed code as .KS', async () => {
    const onAdd = vi.fn().mockResolvedValue(true);
    render(<WatchlistPanel items={[{ id: 1, symbol: '005930.KS', created_at: '' }, { id: 2, symbol: 'AAPL', created_at: '' }]}
      selectedSymbol={null} loading={false} adding={false} removing={null} onAdd={onAdd} onSelect={vi.fn()} onRemove={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('관심 종목 검색'), { target: { value: '005' } });
    expect(screen.getByRole('button', { name: '005930.KS 선택' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'AAPL 선택' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('관심 종목 코드'), { target: { value: '000660' } });
    fireEvent.click(screen.getByRole('button', { name: '종목 추가' }));
    await waitFor(() => expect(onAdd).toHaveBeenCalledWith('000660.KS'));
  });

  it('shows validation guidance and manages only the signed-in account conditions', async () => {
    const api = {
      alertConditions: vi.fn().mockResolvedValue([{ id: 1, symbol: 'MSFT', name: 'MSFT', user_rule: '5% 상승', validation_summary: '유효', enabled: true }]),
      addAlertCondition: vi.fn().mockRejectedValueOnce(new ApiError(422, { validation_summary: '모호한 기준', rewrite_guidance: '수치를 적어 주세요' }))
        .mockResolvedValueOnce({ id: 2, symbol: 'MSFT', name: 'MSFT', user_rule: '5% 이상 상승', validation_summary: '검증 완료', enabled: true }),
      removeAlertCondition: vi.fn().mockResolvedValue(undefined),
    } as unknown as WebApi;
    render(<AlertConditionsPanel api={api} selectedSymbol="MSFT" onSessionExpired={vi.fn()} />);
    expect(await screen.findByText('5% 상승')).toBeVisible();
    fireEvent.change(screen.getByLabelText('알림 조건'), { target: { value: '5% 이상 상승' } });
    fireEvent.click(screen.getByRole('button', { name: '조건 등록' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('모호한 기준 · 수치를 적어 주세요');
    fireEvent.click(screen.getByRole('button', { name: '조건 등록' }));
    expect(await screen.findByRole('status')).toHaveTextContent('검증 완료');
    fireEvent.click(screen.getByRole('button', { name: 'MSFT 조건 1 삭제' }));
    await waitFor(() => expect(api.removeAlertCondition).toHaveBeenCalledWith(1));
  });

  it('trusts a fresh connection status after callback and starts consent in the same tab', async () => {
    window.history.replaceState({}, '', '/app?notification_connection=connected');
    const api = {
      notificationConnection: vi.fn().mockResolvedValue({ connected: false, connection_id: null }),
      authorizeNotification: vi.fn().mockResolvedValue('https://kauth.kakao.com/oauth/authorize'),
      disconnectNotification: vi.fn(),
    } as unknown as WebApi;
    const navigateTo = vi.fn();
    render(<NotificationConnectionPanel api={api} onSessionExpired={vi.fn()} navigateTo={navigateTo} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('연결 상태를 확인하지 못했습니다');
    fireEvent.click(screen.getByRole('button', { name: '카카오 알림 연결' }));
    await waitFor(() => expect(navigateTo).toHaveBeenCalledWith('https://kauth.kakao.com/oauth/authorize'));
  });

  it('disconnects the saved Kakao connection', async () => {
    const api = {
      notificationConnection: vi.fn().mockResolvedValue({ connected: true, connection_id: 7 }),
      disconnectNotification: vi.fn().mockResolvedValue(undefined),
    } as unknown as WebApi;
    render(<NotificationConnectionPanel api={api} onSessionExpired={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: '연결 해제' }));
    await waitFor(() => expect(api.disconnectNotification).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('카카오 알림 연결 안 됨')).toBeVisible();
  });
});
