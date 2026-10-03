import { useEffect, useRef, useState } from 'react';
import { ApiError, type AnalysisHistoryItem, type AnalysisResult, type Session, type WatchlistItem, type WebApi } from './api';
import { WatchlistPanel } from './components/WatchlistPanel';
import { AnalysisPanel, AnalysisHistoryPanel } from './components/AnalysisPanels';
import { AlertConditionsPanel } from './components/AlertConditionsPanel';
import { NotificationConnectionPanel } from './components/NotificationConnectionPanel';

interface Props {
  api: WebApi;
  session: Session;
  onLogout: () => void | Promise<void>;
  onSessionExpired: () => void;
}

export function BetaAppPage({ api, session, onLogout, onSessionExpired }: Props) {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [history, setHistory] = useState<AnalysisHistoryItem[]>([]);
  const [hasMoreHistory, setHasMoreHistory] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [detail, setDetail] = useState<AnalysisResult | null>(null);
  const [detailLoading, setDetailLoading] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [historyWarning, setHistoryWarning] = useState<string | null>(null);
  const [conditionRevision, setConditionRevision] = useState(0);
  const selectedSymbolRef = useRef<string | null>(null);
  const detailRequestRef = useRef(0);
  const runningRef = useRef(false);

  function handleError(error: unknown, fallback: string) {
    if (error instanceof ApiError && error.status === 401) { onSessionExpired(); return; }
    setMessage(error instanceof ApiError && error.status === 403 ? '이 기능에는 베타 이용 권한이 필요합니다.' : fallback);
  }

  function chooseSymbol(symbol: string | null) {
    selectedSymbolRef.current = symbol;
    detailRequestRef.current += 1;
    setSelectedSymbol(symbol);
    setDetail(null);
    setDetailLoading(null);
    setHistory([]);
    setHasMoreHistory(false);
    setMessage(null);
    setHistoryWarning(null);
  }

  useEffect(() => {
    let active = true;
    api.watchlist().then(rows => {
      if (!active) return;
      setItems(rows);
      chooseSymbol(rows[0]?.symbol ?? null);
    }, error => { if (active) handleError(error, '관심 종목을 불러오지 못했습니다.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [api]);

  useEffect(() => {
    if (!selectedSymbol) { setHistoryLoading(false); return; }
    let active = true;
    const target = selectedSymbol;
    setHistoryLoading(true);
    setHistory([]);
    setDetail(null);
    setHasMoreHistory(false);
    api.analysisHistory(target).then(async rows => {
      if (!active || selectedSymbolRef.current !== target) return;
      setHistory(rows);
      setHasMoreHistory(rows.length === 20);
      if (rows.length) {
        const requestId = ++detailRequestRef.current;
        setDetailLoading(rows[0].id);
        try {
          const result = await api.analysisDetail(target, rows[0].id);
          if (active && selectedSymbolRef.current === target && detailRequestRef.current === requestId) setDetail(result);
        } catch (error) {
          if (active && selectedSymbolRef.current === target && detailRequestRef.current === requestId) handleError(error, '최신 분석 상세를 불러오지 못했습니다.');
        } finally {
          if (active && detailRequestRef.current === requestId) setDetailLoading(null);
        }
      }
    }, error => {
      if (active && selectedSymbolRef.current === target) handleError(error, '저장된 분석 이력을 불러오지 못했습니다.');
    }).finally(() => { if (active && selectedSymbolRef.current === target) setHistoryLoading(false); });
    return () => { active = false; };
  }, [api, selectedSymbol]);

  async function loadMoreHistory() {
    if (!selectedSymbol || historyLoading) return;
    const target = selectedSymbol;
    setHistoryLoading(true);
    try {
      const rows = await api.analysisHistory(target, history.length);
      if (selectedSymbolRef.current === target) {
        setHistory(current => [...current, ...rows]);
        setHasMoreHistory(rows.length === 20);
      }
    } catch (error) {
      if (selectedSymbolRef.current === target) handleError(error, '저장된 분석 이력을 불러오지 못했습니다.');
    } finally { if (selectedSymbolRef.current === target) setHistoryLoading(false); }
  }

  async function showDetail(item: AnalysisHistoryItem) {
    if (!selectedSymbol) return;
    const target = selectedSymbol;
    const requestId = ++detailRequestRef.current;
    setDetailLoading(item.id);
    setMessage(null);
    try {
      const result = await api.analysisDetail(target, item.id);
      if (selectedSymbolRef.current === target && detailRequestRef.current === requestId) setDetail(result);
    } catch (error) {
      if (selectedSymbolRef.current === target && detailRequestRef.current === requestId) handleError(error, '분석 상세를 불러오지 못했습니다.');
    } finally { if (detailRequestRef.current === requestId) setDetailLoading(null); }
  }

  async function runAnalysis() {
    if (!selectedSymbol || runningRef.current) return;
    const target = selectedSymbol;
    runningRef.current = true;
    setRunning(true);
    setMessage(null);
    setHistoryWarning(null);
    let result: AnalysisResult;
    try {
      result = await api.runAnalysis(target);
    } catch (error) {
      if (selectedSymbolRef.current === target) handleError(error, '수동 분석을 완료하지 못했습니다.');
      runningRef.current = false; setRunning(false);
      return;
    }
    if (selectedSymbolRef.current === target) {
      detailRequestRef.current += 1;
      setDetail(result);
      setDetailLoading(null);
      setHistory(current => [result, ...current.filter(item => item.id !== result.id)]);
      setMessage(`${target} 공통 분석이 저장되었습니다.`);
    }
    try {
      const rows = await api.analysisHistory(target);
      if (selectedSymbolRef.current === target) {
        setHistory(rows.length ? rows : [result]);
        setHasMoreHistory(rows.length === 20);
      }
    } catch (error) {
      if (selectedSymbolRef.current === target) {
        if (error instanceof ApiError && error.status === 401) onSessionExpired();
        else setHistoryWarning('분석 이력을 갱신하지 못했습니다. 현재 결과는 저장되었습니다.');
      }
    } finally { runningRef.current = false; setRunning(false); }
  }

  async function addWatchlist(symbol: string) {
    if (adding || loading) return false;
    setAdding(true); setMessage(null);
    try {
      const added = await api.addWatchlist(symbol);
      setItems(current => current.some(item => item.id === added.id) ? current : [...current, added]);
      chooseSymbol(added.symbol);
      return true;
    } catch (error) { handleError(error, '관심 종목을 추가하지 못했습니다.'); return false; }
    finally { setAdding(false); }
  }

  async function removeWatchlist(item: WatchlistItem) {
    if (removing) return;
    setRemoving(item.symbol); setMessage(null);
    try {
      await api.removeWatchlist(item.symbol);
      const remaining = items.filter(candidate => candidate.id !== item.id);
      setItems(remaining);
      if (selectedSymbolRef.current === item.symbol) chooseSymbol(remaining[0]?.symbol ?? null);
      setConditionRevision(current => current + 1);
    } catch (error) { handleError(error, '관심 종목을 삭제하지 못했습니다.'); }
    finally { setRemoving(null); }
  }

  return <main className="page-shell beta-page">
    <section className="service-intro" aria-labelledby="service-title"><div><p className="eyebrow">PRIVATE BETA</p><h1 id="service-title">내 관심 종목</h1>
      <p className="lead">관심 종목의 공통 분석과 알림 조건을 확인하세요.</p></div>
      <div className="account-card"><span>내 계정</span><strong>{session.id}</strong><button className="text-button" type="button" onClick={onLogout}>로그아웃</button></div></section>
    <nav className="beta-nav" aria-label="서비스 화면"><a href="#watchlist-area">관심 종목</a><a href="#analysis-area">공통 분석</a><a href="#history-area">분석 이력</a><a href="#conditions-area">알림 조건</a><a href="#notification-area">카카오 알림</a></nav>
    {message && <p className={message.includes('저장되었습니다') ? 'notice' : 'notice error'} role={message.includes('저장되었습니다') ? 'status' : 'alert'}>{message}</p>}
    {historyWarning && <p className="notice error" role="alert">{historyWarning}</p>}
    <div id="watchlist-area"><WatchlistPanel items={items} selectedSymbol={selectedSymbol} loading={loading} adding={adding} removing={removing} onAdd={addWatchlist} onSelect={chooseSymbol} onRemove={removeWatchlist} /></div>
    <div id="analysis-area"><AnalysisPanel symbol={selectedSymbol} detail={detail} latestId={history[0]?.id ?? null} loading={historyLoading || detailLoading !== null} running={running} onRun={runAnalysis} /></div>
    <div id="history-area"><AnalysisHistoryPanel symbol={selectedSymbol} items={history} selectedId={detail?.id ?? null} loading={historyLoading} detailLoading={detailLoading} hasMore={hasMoreHistory} onSelect={showDetail} onLatest={() => { if (history[0]) showDetail(history[0]); }} onMore={loadMoreHistory} /></div>
    <div id="conditions-area"><AlertConditionsPanel key={conditionRevision} api={api} selectedSymbol={selectedSymbol} onSessionExpired={onSessionExpired} /></div>
    <div id="notification-area"><NotificationConnectionPanel api={api} onSessionExpired={onSessionExpired} /></div>
  </main>;
}
