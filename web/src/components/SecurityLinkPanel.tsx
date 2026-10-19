import { useEffect, useState } from 'react';
import { ApiError, type SecurityCandidate, type WatchlistItem, type WebApi } from '../api';

interface Props {
  item: WatchlistItem;
  api: WebApi;
  onLinked: (item: WatchlistItem) => void;
  onSessionExpired: () => void;
}

export function SecurityLinkPanel({ item, api, onLinked, onSessionExpired }: Props) {
  const [open, setOpen] = useState(false);
  const [candidates, setCandidates] = useState<SecurityCandidate[]>([]);
  const [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true); setError(''); setCandidates([]); setSelected('');
    api.securityCandidates(item.symbol).then(rows => {
      if (!cancelled) setCandidates(rows);
    }).catch(reason => {
      if (cancelled) return;
      if (reason instanceof ApiError && reason.status === 401) onSessionExpired();
      else setError('종목 정보를 불러오지 못했습니다. 다시 조회해 주세요.');
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [api, item.id, item.symbol, open, revision, onSessionExpired]);

  async function link() {
    if (saving || loading || !candidates.some(row => row.security_id === selected && row.selectable)) return;
    setSaving(true); setError('');
    try {
      onLinked(await api.linkWatchlist(item.id, item.symbol, selected));
      setOpen(false);
    } catch (reason) {
      setSelected('');
      if (reason instanceof ApiError && reason.status === 401) onSessionExpired();
      else setError('연결하지 못했습니다. 관심종목 또는 상장 상태가 변경됐거나 등록 이후 상장된 종목일 수 있습니다. 기존 등록은 유지됩니다. 목록을 다시 확인해 주세요.');
    } finally { setSaving(false); }
  }

  if (!open) return <button type="button" onClick={() => setOpen(true)} aria-label={`${item.symbol} 종목 정보 연결`}>종목 정보 연결</button>;
  return <section className="security-link-panel" aria-label={`${item.symbol} 기존 관심종목 연결`}>
    <p>{item.symbol}의 기존 관심종목과 같은 종목을 선택하세요. 기존 알림 조건과 과거 브리핑은 유지됩니다.</p>
    {loading && <p role="status">종목 정보 조회 중…</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && !error && candidates.length === 0 && <p>확인 가능한 종목이 없습니다. 기준정보 갱신 후 다시 조회해 주세요.</p>}
    <fieldset disabled={loading || saving}><legend>연결할 종목</legend>
      {candidates.map(row => <label key={row.security_id}>
        <input type="radio" name={`security-link-${item.id}`} value={row.security_id} checked={selected === row.security_id}
          disabled={!row.selectable} onChange={() => setSelected(row.security_id)} />
        {row.name} · {row.symbol} · {row.country} · {row.note} · 자료 기준 {row.source_date ?? '미상'}{!row.selectable && ' · 현재 연결 불가'}
      </label>)}
    </fieldset>
    <button type="button" disabled={!selected || loading || saving} onClick={link}>{saving ? '연결 중…' : '같은 종목임을 확인하고 연결'}</button>
    <button type="button" disabled={saving || loading} onClick={() => setRevision(value => value + 1)}>다시 조회</button>
    <button type="button" disabled={saving} onClick={() => setOpen(false)}>취소</button>
  </section>;
}
