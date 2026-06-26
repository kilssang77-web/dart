import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { preSpecApi } from '@/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { FileSearch, Building2, Clock, TrendingUp, Link, AlertCircle } from 'lucide-react'
import type { PreSpecNotice } from '@/types'

function fmt(n: number | null | undefined) {
  if (n == null) return '-'
  return (n / 1e8).toFixed(1) + '억'
}

function fmtDate(s: string | null | undefined) {
  if (!s) return '-'
  return s.slice(0, 10)
}

export default function PreSpecPage() {
  const [daysBack, setDaysBack] = useState(30)
  const [matchedOnly, setMatchedOnly] = useState(false)
  const [agency, setAgency] = useState('')
  const [page, setPage] = useState(1)

  const { data: summary, isLoading: sumLoading } = useQuery({
    queryKey: ['pre-spec-summary', daysBack],
    queryFn: () => preSpecApi.summary(daysBack),
  })

  const { data: list, isLoading: listLoading } = useQuery({
    queryKey: ['pre-spec-list', daysBack, matchedOnly, agency, page],
    queryFn: () => preSpecApi.list({
      days_back: daysBack,
      matched_only: matchedOnly,
      order_agency: agency || undefined,
      page,
      size: 20,
    }),
  })

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <FileSearch className="h-6 w-6 text-violet-600" />
        <div>
          <h1 className="text-xl font-bold text-gray-900">수주 예보 — 사전규격</h1>
          <p className="text-sm text-gray-500">입찰공고 前 최상위 신호 · 발주기관 사전규격 등록 현황</p>
        </div>
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {sumLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}><CardContent className="pt-4"><Skeleton className="h-10 w-full" /></CardContent></Card>
          ))
        ) : summary ? (
          <>
            <Card>
              <CardContent className="pt-4">
                <div className="text-2xl font-bold text-violet-700">{summary.total.toLocaleString()}</div>
                <div className="text-xs text-gray-500 mt-1">최근 {daysBack}일 사전규격</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <div className="text-2xl font-bold text-emerald-600">{summary.matched.toLocaleString()}</div>
                <div className="text-xs text-gray-500 mt-1">공고 매핑 완료</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <div className="text-2xl font-bold text-blue-600">{summary.agencies.toLocaleString()}</div>
                <div className="text-xs text-gray-500 mt-1">발주기관 수</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <div className="text-2xl font-bold text-amber-600">{fmt(summary.total_amount)}</div>
                <div className="text-xs text-gray-500 mt-1">총 추정금액</div>
              </CardContent>
            </Card>
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
          <option value={7}>최근 7일</option>
          <option value={14}>최근 14일</option>
          <option value={30}>최근 30일</option>
          <option value={60}>최근 60일</option>
          <option value={90}>최근 90일</option>
        </select>
        <input
          placeholder="발주기관명 검색..."
          value={agency}
          onChange={e => { setAgency(e.target.value); setPage(1) }}
          className="border rounded-md px-3 py-1.5 text-sm w-52"
        />
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={matchedOnly}
            onChange={e => { setMatchedOnly(e.target.checked); setPage(1) }}
          />
          공고 매핑된 건만
        </label>
        <span className="text-sm text-gray-400 ml-auto">
          {list ? `총 ${list.total}건` : ''}
        </span>
      </div>

      {/* 목록 */}
      {listLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : list && list.items.length > 0 ? (
        <div className="space-y-3">
          {list.items.map((item: PreSpecNotice) => (
            <Card key={item.id} className="hover:shadow-md transition-shadow">
              <CardContent className="pt-4 pb-3">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-gray-900 text-sm">{item.title || '(품명 미상)'}</span>
                      {item.is_matched ? (
                        <Badge className="bg-emerald-100 text-emerald-700 border-emerald-300 text-xs">
                          <Link className="h-3 w-3 mr-1" />공고 연결됨
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs text-gray-400">미매핑</Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-4 mt-1.5 flex-wrap text-xs text-gray-500">
                      <span className="flex items-center gap-1">
                        <Building2 className="h-3.5 w-3.5" />
                        {item.order_agency || '-'}
                      </span>
                      {item.demand_agency && item.demand_agency !== item.order_agency && (
                        <span>수요: {item.demand_agency}</span>
                      )}
                      {item.industry_name && (
                        <span className="text-violet-600">{item.industry_name}</span>
                      )}
                      <span className="flex items-center gap-1">
                        <Clock className="h-3.5 w-3.5" />
                        등록 {fmtDate(item.reg_date)}
                      </span>
                      {item.end_date && (
                        <span>마감 {fmtDate(item.end_date)}</span>
                      )}
                    </div>
                    {item.is_matched && item.bid_title && (
                      <div className="mt-1.5 text-xs text-emerald-700 bg-emerald-50 rounded px-2 py-1">
                        연결 공고: {item.bid_title}
                        {item.bid_open_date && ` · 개찰 ${fmtDate(item.bid_open_date)}`}
                      </div>
                    )}
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-sm font-semibold text-gray-800">{fmt(item.estimated_amount)}</div>
                    <div className="text-xs text-gray-400 mt-0.5">{item.pre_spec_no}</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400">
          <AlertCircle className="h-10 w-10 mb-3" />
          <p className="text-sm">해당 기간의 사전규격 데이터가 없습니다.</p>
          <p className="text-xs mt-1">매일 07:00 KST에 자동 수집됩니다.</p>
        </div>
      )}

      {/* 페이지네이션 */}
      {list && list.total > 20 && (
        <div className="flex justify-center gap-2">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 text-sm border rounded-md disabled:opacity-40"
          >
            이전
          </button>
          <span className="px-3 py-1.5 text-sm">
            {page} / {Math.ceil(list.total / 20)}
          </span>
          <button
            onClick={() => setPage(p => p + 1)}
            disabled={page >= Math.ceil(list.total / 20)}
            className="px-3 py-1.5 text-sm border rounded-md disabled:opacity-40"
          >
            다음
          </button>
        </div>
      )}
    </div>
  )
}
