import { useEffect, useState } from 'react';
import { ApiError, type NotificationConnection, type WebApi } from '../api';

interface Props {
  api: WebApi;
  onSessionExpired: () => void;
  navigateTo?: (url: string) => void;
}

export function NotificationConnectionPanel({ api, onSessionExpired, navigateTo = url => window.location.assign(url) }: Props) {
  const [connection, setConnection] = useState<NotificationConnection | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const returned = new URLSearchParams(window.location.search).get('notification_connection');

  function failure(error: unknown, fallback: string) {
    if (error instanceof ApiError && error.status === 401) { onSessionExpired(); return; }
    setMessage(error instanceof ApiError && error.status === 503 ? '카카오 알림 연결을 사용할 수 없습니다. 서버 설정을 확인해 주세요.' : fallback);
  }

  useEffect(() => {
    let active = true;
    if (returned) {
      const url = new URL(window.location.href);
      url.searchParams.delete('notification_connection');
      window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
    }
    api.notificationConnection().then(status => {
      if (!active) return;
      setConnection(status);
      if (returned === 'failed') setMessage('카카오 알림 연결이 완료되지 않았습니다. 다시 시도해 주세요.');
      else if (returned === 'connected' && !status.connected) setMessage('카카오 알림 연결 상태를 확인하지 못했습니다. 다시 확인해 주세요.');
    }, error => { if (active) failure(error, '카카오 알림 연결 상태를 확인하지 못했습니다.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [api, onSessionExpired]);

  async function refresh() {
    setLoading(true); setMessage(null);
    try { setConnection(await api.notificationConnection()); }
    catch (error) { failure(error, '카카오 알림 연결 상태를 확인하지 못했습니다.'); }
    finally { setLoading(false); }
  }

  async function connect() {
    if (pending) return;
    setPending(true); setMessage(null);
    try { navigateTo(await api.authorizeNotification()); }
    catch (error) { failure(error, '카카오 알림 연결을 시작하지 못했습니다.'); setPending(false); }
  }

  async function disconnect() {
    if (pending) return;
    setPending(true); setMessage(null);
    try {
      await api.disconnectNotification();
      setConnection({ connected: false, connection_id: null });
    } catch (error) { failure(error, '카카오 알림 연결을 해제하지 못했습니다.'); }
    finally { setPending(false); }
  }

  return <section className="notification-panel" aria-labelledby="notification-title">
    <div className="panel-heading"><div><p className="step-label">KAKAO NOTIFICATIONS</p><h2 id="notification-title">카카오 알림 연결</h2></div></div>
    <p>로그인과 별개로 알림 수신을 연결합니다. 연결해도 과거 알림은 다시 보내지지 않습니다.</p>
    {loading ? <p className="loading" role="status">연결 상태 확인 중…</p> : <p className="connection-state">{connection?.connected ? '카카오 알림 연결됨' : '카카오 알림 연결 안 됨'}</p>}
    {message && <p className="notice error" role="alert">{message}</p>}
    <div className="connection-actions">
      {connection?.connected ? <button className="secondary-button" type="button" disabled={pending || loading} onClick={disconnect}>연결 해제</button> : <button className="primary-button" type="button" disabled={pending || loading} onClick={connect}>카카오 알림 연결</button>}
      <button className="text-button" type="button" disabled={loading} onClick={refresh}>상태 다시 확인</button>
    </div>
  </section>;
}
