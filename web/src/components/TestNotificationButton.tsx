import { useRef, useState } from 'react';
import { ApiError, type WebApi } from '../api';

interface Props {
  api: Pick<WebApi, 'sendTestNotification'>;
  disabled?: boolean;
  onSessionExpired: () => void;
  onPendingChange?: (pending: boolean) => void;
}

export function TestNotificationButton({ api, disabled, onSessionExpired, onPendingChange }: Props) {
  const inFlight = useRef(false);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  async function send() {
    if (disabled || inFlight.current) return;
    inFlight.current = true;
    setPending(true); setResult(null); onPendingChange?.(true);
    try {
      await api.sendTestNotification();
      setResult({ ok: true, text: '카카오가 테스트 알림 발송을 접수했습니다. 카카오톡 나와의 채팅에서 수신을 확인해 주세요.' });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) { onSessionExpired(); return; }
      const text = error instanceof ApiError && error.status === 409
        ? '카카오 알림 연결이 필요합니다. 상태를 다시 확인하고 연결해 주세요.'
        : error instanceof ApiError && error.status === 503
          ? '테스트 알림을 사용할 수 없습니다. 서버 설정을 확인해 주세요.'
          : error instanceof ApiError && error.status === 403
            ? '테스트 알림 요청이 허용되지 않았습니다. 이용 권한과 접속 주소를 확인해 주세요.'
            : '테스트 알림 발송을 확인하지 못했습니다. 카카오톡 수신함과 연결 상태를 확인한 뒤 다시 시도해 주세요.';
      setResult({ ok: false, text });
    } finally {
      inFlight.current = false;
      setPending(false); onPendingChange?.(false);
    }
  }

  return <div className="test-notification">
    <button className="secondary-button" type="button" disabled={disabled || pending} onClick={send}>
      {pending ? '테스트 알림 보내는 중…' : '테스트 알림 보내기'}
    </button>
    {result && <p className={result.ok ? 'notice' : 'notice error'} role={result.ok ? 'status' : 'alert'}>{result.text}</p>}
  </div>;
}
