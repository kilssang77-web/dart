/**
 * 원클릭 투찰 기록 모달
 * 공고 선택 + 투찰률 입력을 3초 안에 완료할 수 있는 빠른 입력 UI.
 * AppLayout FAB 또는 각 공고 행의 빠른 기록 버튼에서 호출한다.
 */
import { useState, useCallback, useEffect, useRef } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { decisionApi, journalApi } from '@/api'
import { BookOpen, Search, X, CheckCircle2, AlertCircle, Zap } from 'lucide-react'
import { cn } from '@/lib/utils'

interface Props {
  open: boolean
  onClose: () => void
  /** 이미 선택된 공고가 있으면 pre-fill */
  prefill?: {
    bid_id: number
    title: string
    announcement_no?: string
    base_amount?: number
    recommended_rate?: number
  }
}

export default function QuickJournalModal({ open, onClose, prefill }: Props) {
  const qc = useQueryClient()

  const [bidId, setBidId] = useState<number | null>(null)
  const [bidTitle, setBidTitle] = useState('')
  const [announcementNo, setAnnouncementNo] = useState('')
  const [baseAmount, setBaseAmount] = useState<number>(0)
  const [rateInput, setRateInput] = useState('')
  const [searchQ, setSearchQ] = useState('')
  const [searchResults, setSearchResults] = useState<{ id: number; title: string; announcement_no: string; base_amount: number }[]>([])
  const [searching, setSearching] = useState(false)
  const [done, setDone] = useState(false)
  const rateRef = useRef<HTMLInputElement>(null)

  // prefill 반영
  useEffect(() => {
    if (!open) {
      // 닫힐 때 초기화
      setBidId(null); setBidTitle(''); setAnnouncementNo(''); setBaseAmount(0)
      setRateInput(''); setSearchQ(''); setSearchResults([]); setDone(false)
      return
    }
    if (prefill) {
      setBidId(prefill.bid_id)
      setBidTitle(prefill.title)
      setAnnouncementNo(prefill.announcement_no ?? '')
      setBaseAmount(prefill.base_amount ?? 0)
      if (prefill.recommended_rate) {
        setRateInput((prefill.recommended_rate * 100).toFixed(4))
      }
      setTimeout(() => rateRef.current?.focus(), 100)
    }
  }, [open, prefill])

  const doSearch = useCallback(async () => {
    if (!searchQ.trim()) return
    setSearching(true)
    try {
      const data = await decisionApi.searchBids(searchQ.trim(), 8)
      setSearchResults(Array.isArray(data) ? data : data.items || [])
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }, [searchQ])

  const selectBid = (b: { id: number; title: string; announcement_no: string; base_amount: number }) => {
    setBidId(b.id); setBidTitle(b.title); setAnnouncementNo(b.announcement_no)
    setBaseAmount(b.base_amount); setSearchResults([]); setSearchQ('')
    setTimeout(() => rateRef.current?.focus(), 80)
  }

  const saveMut = useMutation({
    mutationFn: async () => {
      const rate = parseFloat(rateInput.replace(/,/g, ''))
      if (!rate || rate < 80 || rate > 105) throw new Error('투찰률을 확인하세요 (80~105%)')
      const rateDecimal = rate / 100
      return journalApi.create({
        bid_id: bidId!,
        submitted_rate: rateDecimal,
        note: announcementNo ? `공고번호: ${announcementNo}` : undefined,
      })
    },
    onSuccess: () => {
      setDone(true)
      qc.invalidateQueries({ queryKey: ['journal'] })
      qc.invalidateQueries({ queryKey: ['journal-stats'] })
      setTimeout(() => { onClose() }, 1200)
    },
  })

  const rateNum = parseFloat(rateInput.replace(/,/g, '')) || 0
  const estimatedAmt = rateNum && baseAmount ? Math.round(baseAmount * rateNum / 100) : 0

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 sm:p-0"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      {/* backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      <div className="relative z-10 w-full sm:max-w-md bg-white rounded-2xl shadow-2xl overflow-hidden">
        {/* header */}
        <div className="flex items-center justify-between px-5 py-4 bg-amber-600 text-white">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-yellow-300" />
            <span className="font-bold text-sm">원클릭 투찰 기록</span>
          </div>
          <button onClick={onClose} className="hover:bg-white/20 rounded p-1">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* 완료 메시지 */}
          {done && (
            <div className="flex items-center gap-3 bg-emerald-50 border border-emerald-200 rounded-xl p-4">
              <CheckCircle2 className="w-6 h-6 text-emerald-600 shrink-0" />
              <div>
                <p className="text-sm font-semibold text-emerald-700">투찰 기록 완료!</p>
                <p className="text-xs text-emerald-600 mt-0.5">AI 모델 학습에 활용됩니다</p>
              </div>
            </div>
          )}

          {!done && (
            <>
              {/* 공고 선택 */}
              {!bidId ? (
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-gray-600">공고 검색</label>
                  <div className="flex gap-2">
                    <input
                      value={searchQ}
                      onChange={e => setSearchQ(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && doSearch()}
                      placeholder="공고번호 또는 공고명..."
                      className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
                      autoFocus
                    />
                    <button
                      onClick={doSearch}
                      disabled={searching}
                      className="px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm disabled:opacity-50"
                    >
                      <Search className="w-4 h-4" />
                    </button>
                  </div>
                  {searchResults.length > 0 && (
                    <div className="border rounded-lg divide-y max-h-48 overflow-y-auto bg-white shadow-sm">
                      {searchResults.map(r => (
                        <button
                          key={r.id}
                          onClick={() => selectBid(r)}
                          className="w-full text-left px-3 py-2.5 hover:bg-amber-50 text-sm"
                        >
                          <div className="font-medium text-gray-800 truncate">{r.title}</div>
                          <div className="text-xs text-gray-500 flex gap-3 mt-0.5">
                            <span>{r.announcement_no}</span>
                            {r.base_amount > 0 && <span>{(r.base_amount / 1e8).toFixed(1)}억</span>}
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex items-start justify-between gap-2 bg-amber-50 border border-amber-100 rounded-lg p-3">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-amber-800 truncate">{bidTitle}</p>
                    {announcementNo && <p className="text-xs text-amber-600 font-mono mt-0.5">{announcementNo}</p>}
                  </div>
                  <button
                    onClick={() => { setBidId(null); setBidTitle(''); setAnnouncementNo(''); setBaseAmount(0); setRateInput('') }}
                    className="shrink-0 text-amber-500 hover:text-amber-700"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              )}

              {/* 투찰률 입력 */}
              {bidId && (
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-gray-600">
                    실제 투찰률 (%) <span className="text-red-500">*</span>
                  </label>
                  <input
                    ref={rateRef}
                    value={rateInput}
                    onChange={e => setRateInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && !saveMut.isPending && bidId && rateInput && saveMut.mutate()}
                    placeholder="예) 90.2345"
                    className="w-full border-2 border-amber-300 rounded-xl px-4 py-3 text-lg font-mono font-bold focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                    autoFocus
                  />
                  {estimatedAmt > 0 && (
                    <p className="text-xs text-gray-500 text-right font-mono">
                      투찰금액: {estimatedAmt.toLocaleString('ko-KR')}원
                    </p>
                  )}
                </div>
              )}

              {/* 에러 */}
              {saveMut.isError && (
                <div className="flex items-center gap-2 text-xs text-red-600 bg-red-50 rounded-lg p-2.5 border border-red-100">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                  {(saveMut.error as Error)?.message || '저장 중 오류가 발생했습니다.'}
                </div>
              )}

              {/* 저장 버튼 */}
              <button
                onClick={() => saveMut.mutate()}
                disabled={!bidId || !rateInput || saveMut.isPending}
                className={cn(
                  'w-full py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2 transition-all',
                  bidId && rateInput
                    ? 'bg-amber-600 hover:bg-amber-700 text-white shadow-md shadow-amber-200'
                    : 'bg-gray-100 text-gray-400 cursor-not-allowed',
                )}
              >
                {saveMut.isPending ? (
                  <span className="animate-pulse">기록 중...</span>
                ) : (
                  <><BookOpen className="w-4 h-4" />투찰 기록 저장 (Enter)</>
                )}
              </button>
              <p className="text-center text-xs text-gray-400">
                개찰 결과는 자동으로 수집됩니다
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
