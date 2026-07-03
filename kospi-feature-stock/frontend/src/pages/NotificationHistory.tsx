import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Send, CheckCircle, XCircle, TrendingUp, FileText, RefreshCw, ChevronLeft, ChevronRight, MessageSquare, RotateCcw } from 'lucide-react'
import { notificationsApi } from '@/api/notifications'
import { fmt } from '@/lib/utils'
import type { TelegramLog } from '@/types'

function decodeTelegramHtml(html: string): string {
  return html
    .replace(/<b>(.*?)<\/b>/gs, '$1')
    .replace(/<code>(.*?)<\/code>/gs, '$1')
    .replace(/<i>(.*?)<\/i>/gs, '$1')
    .replace(/<a[^>]*>(.*?)<\/a>/gs, '$1')
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')
}

function friendlyError(msg: string | null | undefined): string {
  if (!msg) return ''
  if (msg.includes('Errno -3') || msg.includes('name resolution') || msg.includes('getaddrinfo failed')) {
    return 'DNS 조회 실패 — 컨테이너가 외부 인터넷에 접근하지 못했습니다. 네트워크/DNS 설정을 확인하세요.'
  }
  if (msg.includes('Errno 111') || msg.includes('Connection refused')) {
    return '연결 거부됨 — Telegram API 서버가 접속을 거부했습니다. 방화벽 또는 프록시 설정을 확인하세요.'
  }
  if (msg.includes('Errno 110') || msg.includes('timed out') || msg.includes('TimeoutError') || msg.includes('timeout')) {
    return '연결 시간 초과 — Telegram 서버에 응답이 없었습니다. 네트워크 상태를 확인하세요.'
  }
  if (msg.includes('401') || msg.toLowerCase().includes('unauthorized')) {
    return '인증 실패 (401) — 봇 토큰(TELEGRAM_BOT_TOKEN)이 잘못되었거나 만료되었습니다.'
  }
  if (msg.toLowerCase().includes('chat not found') || msg.includes('400')) {
    return '채팅 ID 오류 (400) — TELEGRAM_CHAT_ID가 잘못되었습니다. 올바른 채팅 ID를 설정하세요.'
  }
  if (msg.includes('429') || msg.toLowerCase().includes('too many requests')) {
    return '전송 한도 초과 (429) — Telegram API 호출 빈도가 너무 높습니다. 잠시 후 재시도하세요.'
  }
  if (msg.toLowerCase().includes('ssl') || msg.toLowerCase().includes('certificate')) {
    return 'SSL/TLS 인증 오류 — 인증서 검증에 실패했습니다. 시스템 시간 또는 CA 인증서를 확인하세요.'
  }
  if (msg.includes('ConnectError') || msg.includes('ConnectionError') || msg.includes('ECONNRESET') || msg.includes('RemoteProtocolError')) {
    return '네트워크 연결 오류 — Telegram 서버와의 연결이 끊어졌습니다. 인터넷 연결을 확인하세요.'
  }
  if (msg.toLowerCase().includes('not configured') || msg.includes('BOT_TOKEN') || msg.includes('CHAT_ID')) {
    return 'Telegram 설정 누락 — .env 파일에 TELEGRAM_BOT_TOKEN과 TELEGRAM_CHAT_ID를 설정하세요.'
  }
  return msg
}

const PAGE_SIZE = 50

function StatCard({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-5">
      <div className="text-sm text-[var(--muted)] mb-1">{label}</div>
      <div className={clsx('text-2xl font-extrabold tabular', color ?? 'text-[var(--fg)]')}>{value}</div>
      {sub && <div className="text-xs text-[var(--muted)] mt-1">{sub}</div>}
    </div>
  )
}

function TypeBadge({ type }: { type: string }) {
  if (type === 'signal') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-green-500/15 text-green-400 border border-green-500/30">
        <TrendingUp size={11} /> 매수신호
      </span>
    )
  }
  if (type === 'disclosure') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-500/15 text-blue-400 border border-blue-500/30">
        <FileText size={11} /> 공시
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-[var(--border)] text-[var(--muted)]">
      {type}
    </span>
  )
}

function StatusBadge({ success }: { success: boolean }) {
  return success ? (
    <span className="inline-flex items-center gap-1 text-xs font-semibold text-green-400">
      <CheckCircle size={13} /> 성공
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-xs font-semibold text-red-400">
      <XCircle size={13} /> 실패
    </span>
  )
}

function MessageModal({
  log,
  onClose,
  onRetry,
  retrying,
  retryResult,
}: {
  log: TelegramLog
  onClose: () => void
  onRetry: () => void
  retrying: boolean
  retryResult: 'success' | 'error' | null
}) {
  const friendly = friendlyError(log.error_msg)
  const isRaw = friendly === log.error_msg

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div
        className="relative bg-[var(--card)] border border-[var(--border)] rounded-2xl w-full max-w-lg shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
          <div className="flex items-center gap-3">
            <TypeBadge type={log.msg_type} />
            <span className="font-bold text-[var(--fg)]">{log.name || log.code || '—'}</span>
          </div>
          <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--fg)] transition-colors">✕</button>
        </div>
        <div className="px-6 py-5 space-y-3">
          <div className="text-sm text-[var(--muted)]">제목</div>
          <div className="text-sm font-medium text-[var(--fg)]">{log.title || '—'}</div>
          <div className="text-sm text-[var(--muted)] mt-3">발송 메시지</div>
          <pre className="text-xs text-[var(--fg)] bg-[var(--bg)] rounded-xl p-4 whitespace-pre-wrap break-words leading-relaxed border border-[var(--border)]">
            {decodeTelegramHtml(log.message)}
          </pre>
          {log.error_msg && (
            <>
              <div className="text-sm text-red-400 mt-3">오류 원인</div>
              <div className="text-xs text-red-300 bg-red-500/10 rounded-lg p-3 leading-relaxed">{friendly}</div>
              {!isRaw && (
                <details className="mt-1">
                  <summary className="text-xs text-[var(--muted)] cursor-pointer hover:text-[var(--fg)] select-none">원본 오류 메시지 보기</summary>
                  <div className="mt-1.5 text-xs text-[var(--muted)] bg-[var(--bg)] rounded-lg p-2 font-mono break-all border border-[var(--border)]">
                    {log.error_msg}
                  </div>
                </details>
              )}
            </>
          )}
          <div className="flex items-center justify-between pt-2">
            <span className="text-xs text-[var(--muted)]">발송 시각: {fmt.dateTime(log.sent_at)}</span>
            <div className="flex items-center gap-3">
              <StatusBadge success={log.success} />
              {!log.success && (
                <button
                  onClick={onRetry}
                  disabled={retrying}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/25 disabled:opacity-50 transition-colors"
                >
                  <RotateCcw size={12} className={retrying ? 'animate-spin' : ''} />
                  {retrying ? '재발송 중…' : '재발송'}
                </button>
              )}
            </div>
          </div>
          {retryResult === 'success' && (
            <div className="flex items-center gap-1.5 text-xs text-green-400 bg-green-500/10 rounded-lg px-3 py-2">
              <CheckCircle size={13} /> 재발송 완료
            </div>
          )}
          {retryResult === 'error' && (
            <div className="flex items-center gap-1.5 text-xs text-red-400 bg-red-500/10 rounded-lg px-3 py-2">
              <XCircle size={13} /> 재발송 실패 — 설정 및 네트워크 상태를 확인하세요
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function NotificationHistory() {
  const [msgType,  setMsgType]  = useState<string>('')
  const [successF, setSuccessF] = useState<string>('')
  const [page,     setPage]     = useState(0)
  const [selected, setSelected] = useState<TelegramLog | null>(null)
  const [retryResult, setRetryResult] = useState<'success' | 'error' | null>(null)
  const [rowFlash, setRowFlash] = useState<Record<number, 'success' | 'error'>>({})

  const qc = useQueryClient()
  const offset = page * PAGE_SIZE

  const statsQ = useQuery({
    queryKey: ['telegram-stats'],
    queryFn:  notificationsApi.getStats,
    refetchInterval: 30_000,
  })

  const logsQ = useQuery({
    queryKey: ['telegram-logs', msgType, successF, offset],
    queryFn: () => notificationsApi.getLogs({
      msg_type: msgType   || undefined,
      success:  successF === '' ? undefined : successF === 'true',
      limit:    PAGE_SIZE,
      offset,
    }),
    refetchInterval: 15_000,
  })

  const retryMut = useMutation({
    mutationFn: (id: number) => notificationsApi.retryLog(id),
    onSuccess: (_, id) => {
      setRetryResult('success')
      setRowFlash((prev) => ({ ...prev, [id]: 'success' }))
      setTimeout(() => setRowFlash((prev) => { const n = { ...prev }; delete n[id]; return n }), 3000)
      qc.invalidateQueries({ queryKey: ['telegram-logs'] })
      qc.invalidateQueries({ queryKey: ['telegram-stats'] })
    },
    onError: (_, id) => {
      setRetryResult('error')
      setRowFlash((prev) => ({ ...prev, [id]: 'error' }))
      setTimeout(() => setRowFlash((prev) => { const n = { ...prev }; delete n[id]; return n }), 3000)
    },
  })

  const handleRetry = (id: number) => {
    setRetryResult(null)
    retryMut.mutate(id)
  }

  const stats = statsQ.data
  const data  = logsQ.data
  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0

  const handleFilter = (type: string, val: string, setter: (v: string) => void) => {
    setter(val)
    setPage(0)
  }

  return (
    <div className="p-6 space-y-6">

      {/* 통계 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
        <StatCard label="총 발송" value={stats?.total ?? '—'} />
        <StatCard label="성공" value={stats?.success_count ?? '—'} color="text-green-400" />
        <StatCard label="실패" value={stats?.fail_count ?? '—'} color={stats?.fail_count ? 'text-red-400' : undefined} />
        <StatCard label="매수신호" value={stats?.signal_count ?? '—'} color="text-green-400" />
        <StatCard label="공시" value={stats?.disclosure_count ?? '—'} color="text-blue-400" />
        <StatCard label="오늘" value={stats?.today_count ?? '—'} />
        <StatCard label="마지막 발송" value={stats?.last_sent_at ? fmt.dateTime(stats.last_sent_at) : '—'} />
      </div>

      {/* 필터 바 */}
      <div className="flex flex-wrap gap-3 items-center bg-[var(--card)] border border-[var(--border)] rounded-xl px-5 py-3">
        <span className="text-sm font-semibold text-[var(--muted)]">필터</span>

        <select
          value={msgType}
          onChange={(e) => handleFilter('type', e.target.value, setMsgType)}
          className="text-sm bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-[var(--fg)] focus:outline-none focus:border-cyan-500"
        >
          <option value="">전체 유형</option>
          <option value="signal">매수신호</option>
          <option value="disclosure">공시</option>
        </select>

        <select
          value={successF}
          onChange={(e) => handleFilter('success', e.target.value, setSuccessF)}
          className="text-sm bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-[var(--fg)] focus:outline-none focus:border-cyan-500"
        >
          <option value="">전체 상태</option>
          <option value="true">성공</option>
          <option value="false">실패</option>
        </select>

        <button
          onClick={() => logsQ.refetch()}
          className="ml-auto flex items-center gap-1.5 text-sm text-[var(--muted)] hover:text-[var(--fg)] transition-colors"
        >
          <RefreshCw size={13} className={logsQ.isFetching ? 'animate-spin' : ''} />
          새로고침
        </button>

        {data && (
          <span className="text-xs text-[var(--muted)]">총 {data.total.toLocaleString()}건</span>
        )}
      </div>

      {/* 테이블 */}
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden">
        {logsQ.isLoading ? (
          <table className="w-full text-sm">
            <tbody>
              {Array.from({ length: 8 }).map((_, i) => (
                <tr key={i} className="border-b border-[var(--border)]/60">
                  <td className="px-5 py-3"><div className="h-3 skeleton rounded w-28" /></td>
                  <td className="px-4 py-3"><div className="h-5 skeleton rounded-full w-16" /></td>
                  <td className="px-4 py-3">
                    <div className="h-4 skeleton rounded w-16 mb-1" />
                    <div className="h-3 skeleton rounded w-10" />
                  </td>
                  <td className="px-4 py-3"><div className="h-4 skeleton rounded w-48" /></td>
                  <td className="px-4 py-3 text-center"><div className="h-4 skeleton rounded w-10 mx-auto" /></td>
                  <td className="px-4 py-3 text-center"><div className="h-6 skeleton rounded w-14 mx-auto" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : !data?.items.length ? (
          <div className="flex flex-col items-center justify-center h-40 gap-3 text-[var(--muted)]">
            <Send size={28} className="opacity-40" />
            <span className="text-sm">발송 이력이 없습니다</span>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] text-xs text-[var(--muted)] font-semibold uppercase tracking-wide">
                <th className="text-left px-5 py-3">발송 시각</th>
                <th className="text-left px-4 py-3">유형</th>
                <th className="text-left px-4 py-3">종목</th>
                <th className="text-left px-4 py-3 max-w-xs">제목</th>
                <th className="text-center px-4 py-3">상태</th>
                <th className="text-center px-4 py-3">액션</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((log) => {
                const flash = rowFlash[log.id]
                return (
                  <tr
                    key={log.id}
                    className={clsx(
                      'border-b border-[var(--border)] transition-colors',
                      flash === 'success' ? 'bg-green-500/10' : flash === 'error' ? 'bg-red-500/10' : 'hover:bg-[var(--bg)]',
                    )}
                  >
                    <td className="px-5 py-3 tabular text-[var(--muted)] whitespace-nowrap text-xs">
                      {fmt.dateTime(log.sent_at)}
                    </td>
                    <td className="px-4 py-3">
                      <TypeBadge type={log.msg_type} />
                    </td>
                    <td className="px-4 py-3">
                      {log.code ? (
                        <span className="font-semibold text-[var(--fg)]">
                          {log.name || log.code}
                          <span className="ml-1.5 text-xs text-[var(--muted)] font-mono">{log.code}</span>
                        </span>
                      ) : <span className="text-[var(--muted)]">—</span>}
                    </td>
                    <td className="px-4 py-3 max-w-xs">
                      <span className="text-[var(--fg)] line-clamp-1">{log.title || '—'}</span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <StatusBadge success={log.success} />
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className="inline-flex items-center gap-1">
                        <button
                          onClick={() => { setSelected(log); setRetryResult(null) }}
                          className="p-1.5 rounded-lg hover:bg-[var(--border)] text-[var(--muted)] hover:text-cyan-400 transition-colors"
                          title="메시지 보기"
                        >
                          <MessageSquare size={14} />
                        </button>
                        {!log.success && (
                          <button
                            onClick={() => handleRetry(log.id)}
                            disabled={retryMut.isPending && retryMut.variables === log.id}
                            className="p-1.5 rounded-lg hover:bg-[var(--border)] text-[var(--muted)] hover:text-orange-400 disabled:opacity-40 transition-colors"
                            title="재발송"
                          >
                            <RotateCcw
                              size={14}
                              className={retryMut.isPending && retryMut.variables === log.id ? 'animate-spin' : ''}
                            />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* 페이지네이션 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="p-1.5 rounded-lg border border-[var(--border)] disabled:opacity-30 hover:bg-[var(--border)] transition-colors"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="text-sm text-[var(--muted)]">
            {page + 1} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="p-1.5 rounded-lg border border-[var(--border)] disabled:opacity-30 hover:bg-[var(--border)] transition-colors"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      )}

      {/* 메시지 상세 모달 */}
      {selected && (
        <MessageModal
          log={selected}
          onClose={() => setSelected(null)}
          onRetry={() => handleRetry(selected.id)}
          retrying={retryMut.isPending && retryMut.variables === selected.id}
          retryResult={retryResult}
        />
      )}
    </div>
  )
}
