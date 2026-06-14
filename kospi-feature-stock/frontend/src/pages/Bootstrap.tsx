import { useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import {
  CheckCircle2, Clock, Loader2, PlayCircle, Cpu,
  AlertTriangle, ChevronRight,
} from 'lucide-react'
import { adminApi, type BootstrapStep } from '@/api/admin'
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'

// steps that have a runnable action
const STEP_ACTIONS: Partial<Record<string, () => Promise<unknown>>> = {
  load_stocks:       () => adminApi.runLoadStocks(),
  fetch_bars:        () => adminApi.runFetchHistorical(),
  refresh_stats:     () => adminApi.runRefreshStats(),
  train_model:       () => adminApi.runTrainModel(),
  generate_vectors:  () => adminApi.runBackfillVectors(),
}

// prerequisite map: step id → id that must be done first
const PREREQ: Record<string, string> = {
  fetch_bars:         'load_stocks',
  compute_indicators: 'fetch_bars',
  refresh_stats:      'compute_indicators',
  backfill_events:    'refresh_stats',
  train_model:        'backfill_events',
  generate_vectors:   'train_model',
}

function pct(count: number | null, target: number | null): number {
  if (!count || !target) return 0
  return Math.min(100, Math.round((count / target) * 100))
}

// ── 단계 행 ────────────────────────────────────────────────────────────────────

function StepRow({
  step, index, allSteps,
}: {
  step: BootstrapStep
  index: number
  allSteps: BootstrapStep[]
}) {
  const qc = useQueryClient()
  const actionFn = STEP_ACTIONS[step.id]
  const prereqId = PREREQ[step.id]
  const prereqDone = prereqId
    ? (allSteps.find(s => s.id === prereqId)?.done ?? false)
    : true

  const mutation = useMutation({
    mutationFn: actionFn ?? (() => Promise.resolve()),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['bootstrap-status'] }) },
  })

  const progress = pct(step.count, step.target)

  return (
    <div className={clsx(
      'rounded-xl border p-4 space-y-2 transition-colors',
      step.done
        ? 'border-green-500/30 bg-green-500/5'
        : prereqDone
          ? 'border-[var(--border)] bg-[var(--bg)]'
          : 'border-[var(--border)] bg-[var(--bg)] opacity-50',
    )}>
      <div className="flex items-center gap-3">
        {/* 순서 배지 */}
        <div className={clsx(
          'w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0',
          step.done
            ? 'bg-green-500/20 text-green-400'
            : 'bg-[var(--border)] text-[var(--muted)]',
        )}>
          {step.done ? <CheckCircle2 size={14} /> : index + 1}
        </div>

        {/* 라벨 + 상세 */}
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-[var(--fg)] flex items-center gap-1.5">
            {step.label}
            {!prereqDone && (
              <span className="text-[10px] text-[var(--muted)] font-normal">
                (이전 단계 완료 후 활성화)
              </span>
            )}
          </div>
          <div className="text-xs text-[var(--muted)] mt-0.5">{step.detail}</div>
        </div>

        {/* 실행 버튼 */}
        <div className="shrink-0">
          {step.done ? (
            <span className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-green-500/15 text-green-400">
              완료
            </span>
          ) : mutation.isPending ? (
            <span className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-blue-500/15 text-blue-400 flex items-center gap-1.5">
              <Loader2 size={12} className="animate-spin" /> 진행 중
            </span>
          ) : actionFn ? (
            <button
              onClick={() => mutation.mutate()}
              disabled={!prereqDone || mutation.isPending}
              className={clsx(
                'flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors',
                'bg-cyan-500/15 text-cyan-400 hover:bg-cyan-500/25',
                'disabled:opacity-40 disabled:cursor-not-allowed',
              )}
            >
              <PlayCircle size={13} />
              시작
            </button>
          ) : (
            <span className="text-xs text-[var(--muted)] flex items-center gap-1">
              <Clock size={12} /> 자동
            </span>
          )}
        </div>
      </div>

      {/* 진행률 바 (target이 있고 미완료인 경우) */}
      {!step.done && step.target != null && step.count != null && (
        <div>
          <div className="flex justify-between text-[10px] text-[var(--muted)] mb-1">
            <span>{step.count.toLocaleString()} / {step.target.toLocaleString()}</span>
            <span>{progress}%</span>
          </div>
          <div className="h-1.5 rounded-full bg-[var(--border)] overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-blue-500 transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}

// ── 전체 진행률 ───────────────────────────────────────────────────────────────

function OverallProgress({ steps }: { steps: BootstrapStep[] }) {
  const done  = steps.filter(s => s.done).length
  const total = steps.length
  const p     = Math.round((done / total) * 100)
  return (
    <div>
      <div className="flex justify-between text-xs text-[var(--muted)] mb-2">
        <span>전체 진행률</span>
        <span className="font-semibold text-[var(--fg)]">{p}% ({done}/{total} 단계 완료)</span>
      </div>
      <div className="h-2.5 rounded-full bg-[var(--border)] overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-blue-500 transition-all duration-700"
          style={{ width: `${p}%` }}
        />
      </div>
    </div>
  )
}

// ── 로그 패널 ─────────────────────────────────────────────────────────────────

function LogPanel({ logs }: { logs: string[] }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight
  }, [logs])

  return (
    <div
      ref={ref}
      className="h-52 overflow-y-auto rounded-xl border border-[var(--border)] bg-black/30 p-3 font-mono text-xs text-[var(--muted)] space-y-0.5"
    >
      {logs.length === 0 ? (
        <div className="text-center py-6">로그 없음 — 단계를 시작하면 여기에 출력됩니다.</div>
      ) : (
        [...logs].reverse().map((line, i) => (
          <div
            key={i}
            className={clsx(
              'leading-relaxed whitespace-pre-wrap',
              line.includes('완료') && 'text-green-400',
              (line.includes('실패') || line.includes('오류')) && 'text-red-400',
              line.includes('시작') && 'text-blue-400',
            )}
          >
            {line}
          </div>
        ))
      )}
    </div>
  )
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────

export function Bootstrap() {
  const { data, isLoading } = useQuery({
    queryKey:        ['bootstrap-status'],
    queryFn:         adminApi.getBootstrapStatus,
    refetchInterval: 5_000,
  })

  const steps = data?.steps ?? []

  return (
    <div className="p-6 space-y-5 max-w-3xl mx-auto">
      {/* 헤더 */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-500/20 border border-cyan-500/30 flex items-center justify-center">
          <Cpu size={18} className="text-cyan-400" />
        </div>
        <div>
          <h1 className="text-lg font-bold text-[var(--fg)]">시스템 초기화 (Bootstrap)</h1>
          <p className="text-xs text-[var(--muted)]">처음 설치 시 1회 실행. 완료까지 20~60분 소요 가능.</p>
        </div>
        {data?.overall_ok && (
          <span className="ml-auto text-xs font-semibold px-3 py-1 rounded-full bg-green-500/15 text-green-400 border border-green-500/30 flex items-center gap-1">
            <CheckCircle2 size={12} /> 초기화 완료
          </span>
        )}
      </div>

      {/* 전체 진행률 */}
      {steps.length > 0 && (
        <Card>
          <CardBody>
            <OverallProgress steps={steps} />
          </CardBody>
        </Card>
      )}

      {/* 단계별 위저드 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5">
            <ChevronRight size={14} className="text-cyan-400" /> 초기화 단계 (6단계)
          </CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          {isLoading
            ? Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-16 skeleton rounded-xl" />)
            : steps.map((step, i) => (
                <StepRow key={step.id} step={step} index={i} allSteps={steps} />
              ))
          }
        </CardBody>
      </Card>

      {/* 실시간 로그 */}
      <Card>
        <CardHeader>
          <CardTitle>실시간 로그</CardTitle>
          <span className="text-xs text-[var(--muted)]">5초마다 갱신</span>
        </CardHeader>
        <CardBody>
          <LogPanel logs={data?.logs ?? []} />
        </CardBody>
      </Card>

      {/* 주의사항 */}
      <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-4 text-xs text-amber-300 space-y-1.5">
        <div className="font-semibold text-amber-400 flex items-center gap-1.5">
          <AlertTriangle size={12} /> 주의사항
        </div>
        <ul className="list-disc list-inside space-y-0.5 text-amber-300/80">
          <li>단계는 순서대로 진행하세요 — 이전 단계가 완료되어야 다음이 활성화됩니다.</li>
          <li>Step 2(일봉 수집)는 네트워크 환경에 따라 20~40분 소요될 수 있습니다.</li>
          <li>지표 계산·이벤트 역산(3~4단계)은 수집 완료 후 자동 실행됩니다.</li>
          <li>이미 완료된 단계를 다시 실행해도 기존 데이터에 영향 없습니다.</li>
        </ul>
      </div>
    </div>
  )
}
