import { useState } from 'react'
import { Calculator, CheckCircle2, XCircle, Info } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

/*
 * 적격심사 계산기 (간이 계산식)
 * 기준: 추정금액 100억 미만 지방자치단체 공사 기준 적격심사 세부기준 (행안부 고시)
 * ─ 실제 심사기준서에 따라 산식이 달라지므로 참고용으로만 사용.
 */

interface CalcResult {
  pass: boolean
  totalScore: number
  minScore: number
  breakdown: { label: string; score: number; max: number; note?: string }[]
  optimalRate: number | null
  minRate: number | null
}

type CategoryKey = 'A' | 'B' | 'C' | 'D'

const CATEGORY_MIN: Record<CategoryKey, number> = { A: 88, B: 87, C: 86, D: 85 }

function calcQualification(params: {
  baseAmount: number
  ownShare: number           // 자사 지분율 (%)
  constructionExperience: number // 시공실적 (억원)
  creditGrade: string        // 신용등급 (A ~ D)
  safetyScore: number        // 산업재해예방활동 점수 (0~10)
  isRegional: boolean        // 지역업체 여부
}): CalcResult {
  const { baseAmount, ownShare, constructionExperience, creditGrade, safetyScore, isRegional } = params
  const amtBillion = baseAmount / 1e8

  // 1. 시공능력 평가 (최대 30점)
  const expRequired = amtBillion * (ownShare / 100) * 0.7
  const expRatio = constructionExperience > 0 ? Math.min(constructionExperience / Math.max(expRequired, 0.01), 1) : 0
  const expScore = +(expRatio * 30).toFixed(2)

  // 2. 경영상태 (신용평가) - 최대 30점
  const creditMap: Record<string, number> = { AAA: 30, AA: 27, A: 24, BBB: 21, BB: 15, B: 10, CCC: 5, CC: 3, C: 1 }
  const creditScore = creditMap[creditGrade] ?? 10

  // 3. 납세실적 (단순화 — 최대 20점, 이행 시 20점)
  const taxScore = 20

  // 4. 산업재해 (최대 10점)
  const safeScore = Math.min(safetyScore, 10)

  // 5. 지역업체 가산 (최대 2점)
  const regionalBonus = isRegional ? 2 : 0

  const total = expScore + creditScore + taxScore + safeScore + regionalBonus
  const minScore = 65

  // 최소 투찰률 산정 (단순화)
  const cat = (creditGrade.startsWith('A') ? 'A' : creditGrade.startsWith('B') ? 'B' : creditGrade.startsWith('C') ? 'C' : 'D') as CategoryKey
  const minPct = CATEGORY_MIN[cat]
  const minRate = minPct / 100
  const optimalRate = minRate + 0.01

  return {
    pass: total >= minScore,
    totalScore: +total.toFixed(2),
    minScore,
    breakdown: [
      { label: '시공실적', score: expScore, max: 30, note: `요구실적 ${expRequired.toFixed(1)}억 · 보유 ${constructionExperience.toFixed(1)}억` },
      { label: '경영상태 (신용)', score: creditScore, max: 30, note: creditGrade },
      { label: '납세실적', score: taxScore, max: 20, note: '이행 시 만점' },
      { label: '산업재해예방', score: safeScore, max: 10 },
      { label: '지역업체 가산', score: regionalBonus, max: 2 },
    ],
    minRate,
    optimalRate,
  }
}

const CREDIT_GRADES = ['AAA','AA+','AA','AA-','A+','A','A-','BBB+','BBB','BBB-','BB+','BB','BB-','B+','B','B-','CCC','CC','C']

export default function QualificationPage() {
  const [baseAmount, setBaseAmount]   = useState('')
  const [ownShare, setOwnShare]       = useState('100')
  const [expAmt, setExpAmt]           = useState('')
  const [credit, setCredit]           = useState('A')
  const [safety, setSafety]           = useState('8')
  const [regional, setRegional]       = useState(false)
  const [result, setResult]           = useState<CalcResult | null>(null)

  const handleCalc = () => {
    const base = Number(baseAmount.replace(/,/g,''))
    if (!base || base <= 0) return
    const r = calcQualification({
      baseAmount: base,
      ownShare: Number(ownShare) || 100,
      constructionExperience: Number(expAmt.replace(/,/g,'')) / 1e8,
      creditGrade: credit.replace(/[+-]/g,''),
      safetyScore: Number(safety) || 0,
      isRegional: regional,
    })
    setResult(r)
  }

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      {/* 헤더 */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Calculator className="h-5 w-5 text-primary" />
          적격심사 계산기
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          추정금액 100억 미만 공사 기준 간이 적격심사 통과 여부 및 최소 투찰금액 산출
        </p>
        <div className="flex items-center gap-1.5 mt-2 text-xs text-yellow-700 bg-yellow-50 border border-yellow-200 rounded-md px-3 py-2">
          <Info className="h-3.5 w-3.5 shrink-0" />
          본 계산기는 참고용입니다. 실제 심사기준서(행안부 고시)를 반드시 확인하세요.
        </div>
      </div>

      {/* 입력 폼 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">심사 정보 입력</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label>발주금액 (원) *</Label>
              <Input placeholder="예: 3000000000" value={baseAmount}
                onChange={(e) => setBaseAmount(e.target.value)} />
              {baseAmount && Number(baseAmount.replace(/,/g,'')) > 0 && (
                <p className="text-xs text-muted-foreground">
                  {(Number(baseAmount.replace(/,/g,'')) / 1e8).toFixed(1)}억원
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label>자사 지분율 (%)</Label>
              <Input type="number" min="1" max="100" value={ownShare}
                onChange={(e) => setOwnShare(e.target.value)} />
            </div>

            <div className="space-y-2">
              <Label>시공실적 (원) *</Label>
              <Input placeholder="예: 2000000000" value={expAmt}
                onChange={(e) => setExpAmt(e.target.value)} />
              {expAmt && Number(expAmt.replace(/,/g,'')) > 0 && (
                <p className="text-xs text-muted-foreground">
                  {(Number(expAmt.replace(/,/g,'')) / 1e8).toFixed(1)}억원
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label>신용등급</Label>
              <Select value={credit} onValueChange={setCredit}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CREDIT_GRADES.map((g) => <SelectItem key={g} value={g}>{g}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>산업재해예방 점수 (0~10)</Label>
              <Input type="number" min="0" max="10" step="0.5" value={safety}
                onChange={(e) => setSafety(e.target.value)} />
            </div>

            <div className="space-y-2">
              <Label>지역업체 해당 여부</Label>
              <div className="flex items-center gap-3 h-10">
                <button
                  className={cn('px-4 py-1.5 rounded-md text-sm border transition-colors',
                    regional ? 'bg-primary text-primary-foreground border-primary' : 'bg-background hover:bg-accent')}
                  onClick={() => setRegional(true)}>해당</button>
                <button
                  className={cn('px-4 py-1.5 rounded-md text-sm border transition-colors',
                    !regional ? 'bg-primary text-primary-foreground border-primary' : 'bg-background hover:bg-accent')}
                  onClick={() => setRegional(false)}>미해당</button>
              </div>
            </div>
          </div>

          <Button onClick={handleCalc} disabled={!baseAmount || !expAmt} className="gap-2">
            <Calculator className="h-4 w-4" /> 심사 계산
          </Button>
        </CardContent>
      </Card>

      {/* 결과 */}
      {result && (
        <div className="space-y-4">
          {/* 합격/불합격 */}
          <Card className={cn('border-2', result.pass ? 'border-green-400 bg-green-50/30' : 'border-red-400 bg-red-50/30')}>
            <CardContent className="pt-5">
              <div className="flex items-center gap-3 mb-4">
                {result.pass
                  ? <CheckCircle2 className="h-8 w-8 text-green-600" />
                  : <XCircle className="h-8 w-8 text-red-500" />}
                <div>
                  <p className={cn('text-2xl font-bold', result.pass ? 'text-green-700' : 'text-red-600')}>
                    적격심사 {result.pass ? '통과 예상' : '미달 예상'}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    총점 {result.totalScore}점 / 기준 {result.minScore}점
                    <span className={cn('ml-2 font-semibold', result.pass ? 'text-green-600' : 'text-red-500')}>
                      ({result.pass ? '+' : ''}{(result.totalScore - result.minScore).toFixed(2)}점)
                    </span>
                  </p>
                </div>
              </div>

              {/* 점수 진행 바 */}
              <div className="w-full bg-muted rounded-full h-3 overflow-hidden mb-4">
                <div
                  className={cn('h-3 rounded-full transition-all', result.pass ? 'bg-green-500' : 'bg-red-400')}
                  style={{ width: `${Math.min(result.totalScore, 100)}%` }}
                />
              </div>

              {/* 투찰금액 */}
              {result.minRate != null && Number(baseAmount.replace(/,/g,'')) > 0 && (
                <div className="grid grid-cols-2 gap-3 mt-2">
                  <div className="bg-white/70 rounded-md p-3 border">
                    <p className="text-xs text-muted-foreground">최소 투찰금액</p>
                    <p className="text-lg font-bold font-mono text-primary">
                      {((Number(baseAmount.replace(/,/g,'')) * (result.minRate)) / 1e8).toFixed(2)}억원
                    </p>
                    <p className="text-xs text-muted-foreground">{(result.minRate * 100).toFixed(3)}%</p>
                  </div>
                  {result.optimalRate != null && (
                    <div className="bg-white/70 rounded-md p-3 border border-primary/30">
                      <p className="text-xs text-muted-foreground">권장 최적 투찰금액</p>
                      <p className="text-lg font-bold font-mono text-primary">
                        {((Number(baseAmount.replace(/,/g,'')) * (result.optimalRate)) / 1e8).toFixed(2)}억원
                      </p>
                      <p className="text-xs text-muted-foreground">{(result.optimalRate * 100).toFixed(3)}%</p>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* 항목별 점수 */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">심사 항목별 점수</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {result.breakdown.map((item) => (
                <div key={item.label}>
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span className="font-medium">{item.label}</span>
                    <div className="flex items-center gap-2">
                      {item.note && <span className="text-xs text-muted-foreground">{item.note}</span>}
                      <Badge variant={item.score >= item.max * 0.7 ? 'success' : item.score >= item.max * 0.4 ? 'warning' : 'destructive'}>
                        {item.score} / {item.max}점
                      </Badge>
                    </div>
                  </div>
                  <div className="w-full bg-muted rounded-full h-2">
                    <div className={cn('h-2 rounded-full', item.score >= item.max * 0.7 ? 'bg-green-500' : item.score >= item.max * 0.4 ? 'bg-orange-400' : 'bg-red-400')}
                      style={{ width: `${(item.score / item.max) * 100}%` }} />
                  </div>
                </div>
              ))}
              <div className="border-t pt-2 flex items-center justify-between text-sm font-semibold">
                <span>합계</span>
                <span className={cn(result.pass ? 'text-green-700' : 'text-red-600')}>
                  {result.totalScore}점 (기준 {result.minScore}점)
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
