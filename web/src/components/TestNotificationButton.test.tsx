import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api';
import { TestNotificationButton } from './TestNotificationButton';

describe('independent test notification button', () => {
  it('blocks duplicate clicks and reports acceptance without claiming device receipt', async () => {
    let finish!: () => void;
    const sendTestNotification = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
    const onPendingChange = vi.fn();
    render(<TestNotificationButton api={{ sendTestNotification }} onSessionExpired={vi.fn()} onPendingChange={onPendingChange} />);
    const button = screen.getByRole('button', { name: '테스트 알림 보내기' });
    fireEvent.click(button); fireEvent.click(button);
    expect(sendTestNotification).toHaveBeenCalledTimes(1);
    expect(button).toBeDisabled();
    finish();
    expect(await screen.findByRole('status')).toHaveTextContent('발송을 접수했습니다');
    expect(screen.getByRole('status')).toHaveTextContent('수신을 확인해 주세요');
    expect(onPendingChange.mock.calls).toEqual([[true], [false]]);
  });

  it.each([
    [new ApiError(409), '연결이 필요합니다'],
    [new ApiError(503), '서버 설정'],
    [new ApiError(403), '이용 권한과 접속 주소'],
    [new ApiError(502), '수신함과 연결 상태'],
    [new TypeError('offline'), '수신함과 연결 상태'],
  ])('shows a safe failure and does not retry (%s)', async (error, message) => {
    const sendTestNotification = vi.fn().mockRejectedValue(error);
    render(<TestNotificationButton api={{ sendTestNotification }} onSessionExpired={vi.fn()} />);
    fireEvent.click(screen.getByRole('button'));
    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(sendTestNotification).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('passes session expiry to its host', async () => {
    const onSessionExpired = vi.fn();
    render(<TestNotificationButton api={{ sendTestNotification: vi.fn().mockRejectedValue(new ApiError(401)) }} onSessionExpired={onSessionExpired} />);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(onSessionExpired).toHaveBeenCalledOnce());
  });
});
