import { useEffect, useRef, useState } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { AdminPage } from './AdminPage';
import { ApiError, type Session, type WebApi } from './api';

type SessionState =
  | { status: 'loading' }
  | { status: 'anonymous' }
  | { status: 'authenticated'; session: Session }
  | { status: 'error'; message: string };

interface AppProps {
  api: WebApi;
}

function Header() {
  return (
    <header className="site-header">
      <a className="brand" href="/login" aria-label="Stock Agent 홈">
        <span className="brand-mark" aria-hidden="true">S</span>
        <span><strong>Stock Agent</strong><small>PRIVATE BETA</small></span>
      </a>
      <span className="secure-label"><i aria-hidden="true" /> 운영자 콘솔</span>
    </header>
  );
}

function LoginPage({ api, onLogin }: { api: WebApi; onLogin: (session: Session) => void }) {
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  async function login() {
    if (pending) return;
    const nextController = new AbortController();
    controller.current = nextController;
    setPending(true);
    setMessage(null);
    try {
      onLogin(await api.login(nextController.signal));
    } catch (error) {
      if (!nextController.signal.aborted) {
        setMessage(error instanceof Error ? error.message : '로그인을 완료하지 못했습니다. 다시 시도해 주세요.');
      }
    } finally {
      if (!nextController.signal.aborted) setPending(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-card" aria-labelledby="login-title">
        <p className="eyebrow">INVITATION CONSOLE</p>
        <h1 id="login-title">비공개 베타<br />운영 도구</h1>
        <p className="lead">운영자로 지정된 카카오 계정으로 로그인해 초대 코드를 발급하세요.</p>
        {message && <p className="notice error" role="alert">{message}</p>}
        <button className="kakao-button" type="button" onClick={login} disabled={pending}>
          <span aria-hidden="true">K</span>{pending ? '로그인 확인 중…' : '카카오로 로그인'}
        </button>
        <p className="privacy-note">로그인 후 내 서비스 계정 ID를 확인할 수 있습니다.</p>
      </section>
      <aside className="login-aside" aria-label="서비스 안내">
        <p>STOCK AGENT</p>
        <blockquote>검증된 사용자에게만<br />투자 분석 도구를 엽니다.</blockquote>
        <span>Operator access · Seoul</span>
      </aside>
    </main>
  );
}

function DeniedPage({ session, onLogout }: { session: Session; onLogout: () => void | Promise<void> }) {
  return (
    <main className="center-shell">
      <section className="state-card">
        <p className="eyebrow">ACCOUNT CHECK</p>
        <h1>운영자 권한이 필요합니다</h1>
        <p className="lead">현재 로그인한 계정은 초대 코드를 발급할 수 없습니다.</p>
        <div className="identity-row"><span>계정 ID</span><strong>{session.id}</strong></div>
        <button className="secondary-button wide" type="button" onClick={onLogout}>로그아웃</button>
      </section>
    </main>
  );
}

export function App({ api }: AppProps) {
  const [state, setState] = useState<SessionState>({ status: 'loading' });
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    let active = true;
    api.session().then(
      session => { if (active) setState({ status: 'authenticated', session }); },
      error => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) setState({ status: 'anonymous' });
        else setState({ status: 'error', message: '서버에 연결하지 못했습니다. 잠시 후 새로고침해 주세요.' });
      },
    );
    return () => { active = false; };
  }, [api]);

  useEffect(() => {
    if (state.status === 'anonymous' && location.pathname !== '/login') navigate('/login', { replace: true });
    if (state.status === 'authenticated' && state.session.is_operator && location.pathname !== '/admin') {
      navigate('/admin', { replace: true });
    }
  }, [location.pathname, navigate, state]);

  async function logout() {
    setLogoutError(null);
    try {
      await api.logout();
      setState({ status: 'anonymous' });
      navigate('/login', { replace: true });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setState({ status: 'anonymous' });
        navigate('/login', { replace: true });
        return;
      }
      setLogoutError('로그아웃하지 못했습니다. 다시 시도해 주세요.');
    }
  }

  function sessionExpired() {
    setState({ status: 'anonymous' });
    navigate('/login', { replace: true });
  }

  let content;
  if (state.status === 'loading') {
    content = <main className="center-shell"><p className="loading" role="status">세션을 확인하고 있습니다…</p></main>;
  } else if (state.status === 'error') {
    content = <main className="center-shell"><section className="state-card"><h1>연결을 확인해 주세요</h1><p className="notice error" role="alert">{state.message}</p></section></main>;
  } else if (state.status === 'anonymous') {
    content = <LoginPage api={api} onLogin={session => setState({ status: 'authenticated', session })} />;
  } else if (!state.session.is_operator) {
    content = <DeniedPage session={state.session} onLogout={logout} />;
  } else {
    content = (
      <Routes>
        <Route path="/admin" element={<AdminPage api={api} session={state.session} onLogout={logout} onSessionExpired={sessionExpired} />} />
        <Route path="*" element={<Navigate replace to="/admin" />} />
      </Routes>
    );
  }

  return (
    <div className="app-frame">
      <Header />
      {logoutError && <p className="global-error" role="alert">{logoutError}</p>}
      {content}
    </div>
  );
}
