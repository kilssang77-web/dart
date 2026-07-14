import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { contractsApi } from '@/api'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { FileText, Building2, Calendar, Users, AlertCircle } from 'lucide-react'
import type { BidContract } from '@/types'

function fmt(n: number | null | undefined) {
  if (n == null) return '-'
  return (n / 1e8).toFixed(1) + '억'
}

function fmtDate(s: string | null | undefined) {
  if (!s) return '-'
  return s.slice(0, 10)
}

function duration(start: string | null, end: string | null) {
  if (!start || !end) return null
  const diff = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 86400000)
  return diff > 0 ? `${diff}일` : null
}

export default function ContractsPage() {
  const [daysBack, setDaysBack] = useState(90)
  const [agency, setAgency] = useState('')
  const [jointOnly, setJointOnly] = useState(false)
  const [page, setPage] = useState(1)

  const { data: summary, isLoading: sumLoading } = useQuery({
    queryKey: ['contracts-summary', daysBack],
    queryFn: () => contractsApi.summary(daysBack),
  })

  const { data: list, isLoading: listLoading } = useQuery({
    queryKey: ['contracts-list', daysBack, agency, jointOnly, page],
    queryFn: () => contractsApi.list({
      days_back: daysBack,
      agency_name: agency || undefined,
      joint_only: jointOnly,
      page,
      size: 20,
    }),
  })

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <FileText className="h-6 w-6 text-blue-600" />
        <div>
          <h1 className="text-xl font-bold text-gray-900">계약 실적</h1>
          <p className="text-sm text-gray-500">나라장터 계약현황 · 착공/준공 추적 · 공동수급 현황</p>
        </div>
      </div>

      {/* 요약 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {sumLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}><CardContent className="pt-4"><Skeleton className="h-10 w-full" /></CardContent></Card>
          ))
        ) : summary ? (
          <>
            <Card><CardContent className="pt-4">
              <div className="text-2xl font-bold text-blue-700">{summary.total.toLocaleString()}</div>
              <div className="text-xs text-gray-500 mt-1">최근 {daysBack}일 계약</div>
            </CardContent></Card>
            <Card><CardContent className="pt-4">
              <div className="text-2xl font-bold text-emerald-600">{summary.matched_bids.toLocaleString()}</div>
              <div className="text-xs text-gray-500 mt-1">공고 매핑</div>
            </CardContent></Card>
            <Card><CardContent className="pt-4">
              <div className="text-2xl font-bold text-violet-600">{summary.joint_count.toLocaleString()}</div>
              <div className="text-xs text-gray-500 mt-1">공동계약</div>
            </CardContent></Card>
            <Card><CardContent className="pt-4">
              <div className="text-2xl font-bold text-amber-600">{fmt(summary.total_amount)}</div>
              <div className="text-xs text-gray-500 mt-1">총 계약금액</div>
            </CardContent></Card>
          </>
        ) : null}
      </div>

      {/* 필터 */}
      <div className="flex flex-wrap gap-3 items-center">
        <select
          value={daysBack}
          onChange={e => { setDaysBack(Number(e.target.value)); setPage(1) }}
          className="border rounded-md px-3 py-1.5 text-sm"
        >
          <option value={30}>최근 30일</option>
          <option value={60}>최근 60일</option>
          <option value={90}>최근 90일</option>
          <option value={180}>최근 180일</option>
          <option value={365}>최근 1년</option>
        </select>
        <input
          placeholder="계약기관명 검색..."
          value={agency}
          onChange={e => { setAgency(e.target.value); setPage(1) }}
          className="border rounded-md px-3 py-1.5 text-sm w-52"
        />
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={jointOnly} onChange={e => { setJointOnly(e.target.checked); setPage(1) }} />
          공동계약만
        </label>
        <span className="text-sm text-gray-400 ml-auto">{list ? `총 ${list.total}건` : ''}</span>
      </div>

      {/* 목록 */}
      {listLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}
        </div>
      ) : list && list.items.length > 0 ? (
        <div className="space-y-3">
          {list.items.map((item: BidContract) => {
            const dur = duration(item.start_date, item.completion_date)
            return (
              <Card key={item.id} className="hover:shadow-md transition-shadow">
                <CardContent className="pt-4 pb-3">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-gray-900 text-sm truncate max-w-md">
                          {item.contract_name || '(계약명 없음)'}
                        </span>
                        {item.joint_contract === 'Y' && (
                          <Badge className="bg-violet-100 text-violet-700 text-xs">공동</Badge>
                        )}
                        {item.bid_id && (
                          <Badge className="bg-emerald-100 text-emerald-700 text-xs">공고 연결</Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-4 mt-1.5 flex-wrap text-xs text-gray-500">
                        <span className="flex items-center gap-1">
                          <Building2 className="h-3.5 w-3.5" />{item.agency_name || '-'}
                        </span>
                        <span className="flex items-center gap-1">
                          <Calendar className="h-3.5 w-3.5" />체결 {fmtDate(item.contract_date)}
                        </span>
                        {item.start_date && (
                          <span>착공 {fmtDate(item.start_date)}</span>
                        )}
                        {item.completion_date && (
                          <span>준공 {fmtDate(item.completion_date)}{dur ? ` (${dur})` : ''}</span>
                        )}
                        {item.contract_method && (
                          <span className="text-blue-500">{item.contract_method}</span>
                        )}
                      </div>
                      {item.company_list && item.company_list.length > 0 && (
                        <div className="mt-1.5 text-xs text-gray-500 flex items-center gap-1">
                          <Users className="h-3.5 w-3.5" />
                          {item.company_list.map((c) => c.corpNm || c.bizRegNo || '').filter(Boolean).join(', ')}
                        </div>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-sm font-semibold text-gray-800">{fmt(item.total_amount)}</div>
                      <div className="text-xs text-gray-400 mt-0.5">{item.unty_cntrct_no}</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400">
          <AlertCircle className="h-10 w-10 mb-3" />
          <p className="text-sm">해당 기간의 계약 데이터가 없습니다.</p>
          <p className="text-xs mt-1">매일 23:00 KST에 자동 수집됩니다.</p>
        </div>
      )}

      {list && list.total > 20 && (
        <div className="flex justify-center gap-2">
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
            className="px-3 py-1.5 text-sm border rounded-md disabled:opacity-40">이전</button>
          <span className="px-3 py-1.5 text-sm">{page} / {Math.ceil(list.total / 20)}</span>
          <button onClick={() => setPage(p => p + 1)} disabled={page >= Math.ceil(list.total / 20)}
            className="px-3 py-1.5 text-sm border rounded-md disabled:opacity-40">다음</button>
        </div>
      )}
    </div>
  )
}
