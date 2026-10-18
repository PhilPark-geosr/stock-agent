import { useEffect, useState } from 'react';
import { ApiError, type AlertCondition, type WebApi } from '../api';

interface Props {
  api: WebApi;
  selectedSymbol: string | null;
  onSessionExpired: () => void;
}

export function AlertConditionsPanel({ api, selectedSymbol, onSessionExpired }: Props) {
  const [conditions, setConditions] = useState<AlertCondition[]>([]);
  const [symbol, setSymbol] = useState(selectedSymbol ?? '');
  const [rule, setRule] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [summary, setSummary] = useState<string | null>(null);

  useEffect(() => { setSymbol(selectedSymbol ?? ''); }, [selectedSymbol]);
  useEffect(() => {
    let active = true;
    api.alertConditions().then(rows => { if (active) setConditions(rows); }, error => {
      if (!active) return;
      if (error instanceof ApiError && error.status === 401) onSessionExpired();
      else setMessage('알림 조건을 불러오지 못했습니다.');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [api, onSessionExpired]);

  async function add(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const target = symbol.trim().toUpperCase();
    const text = rule.trim();
    if (!target || !text || saving) return;
    setSaving(true); setMessage(null); setSummary(null);
    try {
      const added = await api.addAlertCondition(target, text);
      setConditions(current => [...current, added]);
      setRule('');
      setSummary(added.validation_summary);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onSessionExpired();
      else if (error instanceof ApiError && error.status === 422 && error.validationSummary) {
        setMessage([error.validationSummary, error.rewriteGuidance].filter(Boolean).join(' · '));
      } else setMessage('알림 조건을 등록하지 못했습니다.');
    } finally { setSaving(false); }
  }

  async function remove(id: number) {
    if (deleting !== null) return;
    setDeleting(id); setMessage(null);
    try {
      await api.removeAlertCondition(id);
      setConditions(current => current.filter(item => item.id !== id));
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onSessionExpired();
      else setMessage('알림 조건을 삭제하지 못했습니다.');
    } finally { setDeleting(null); }
  }

  return <section className="conditions-panel" aria-labelledby="conditions-title">
    <div className="panel-heading"><div><p className="step-label">MY ALERT CONDITIONS</p><h2 id="conditions-title">내 알림 조건</h2></div></div>
    <p>조건은 예약된 공통 분석 이후 사용자별로 평가됩니다. 카카오 알림을 받으려면 알림 연결이 필요합니다.</p>
    <form className="condition-form" onSubmit={add}>
      <label htmlFor="condition-symbol">알림 대상 코드</label>
      <input id="condition-symbol" value={symbol} onChange={event => setSymbol(event.target.value)} required />
      <label htmlFor="condition-rule">알림 조건</label>
      <textarea id="condition-rule" value={rule} onChange={event => setRule(event.target.value)} minLength={5} maxLength={1000} placeholder="예: 주가가 5% 이상 오르면 알려줘" required />
      <button className="primary-button" type="submit" disabled={saving}>{saving ? '조건 검증 중…' : '조건 등록'}</button>
    </form>
    {message && <p className="notice error" role="alert">{message}</p>}
    {summary && <p className="notice" role="status">{summary}</p>}
    {loading ? <p className="loading" role="status">알림 조건을 불러오는 중…</p> : conditions.length === 0 ? <p className="empty-state">등록된 알림 조건이 없습니다.</p> : <ul className="condition-list" aria-label="내 알림 조건 목록">
      {conditions.map(condition => <li key={condition.id}><div><strong>{condition.symbol} · {condition.name}</strong><p>{condition.user_rule}</p><small>{condition.validation_summary}</small></div>
        <button className="remove-button" type="button" onClick={() => remove(condition.id)} disabled={deleting === condition.id} aria-label={`${condition.symbol} 조건 ${condition.id} 삭제`}>삭제</button></li>)}
    </ul>}
  </section>;
}
