import { useState } from 'react'
import { Calculator, CheckCircle2, XCircle, Info, AlertTriangle, ArrowRightLeft } from 'lucide-react'
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

interface ReverseResult {
  nonPriceScore: number        // creditScore + tax + safety + regional (합산)
  expScoreNeeded: number       // 65 - nonPriceScore (시공실적으로 채워야 할 점수)
  impossible: boolean          // expScoreNeeded > 30 → 아무리 해도 불가
  noExpNeeded: boolean         // expScoreNeeded <= 0 → 실적 없어도 통과
  expRequired: number          // 만점 기준 요구실적 (억원)
  minExpBillion: number | null // 통과에 필요한 최소 시공실적 (억원)
  minRate: number              // 신용등급 기준 최소 투찰률
  minAmount: number            // 최소 투찰금액 (원)
  currentExpScore: number | null  // 입력한 보유실적의 시공실적 점수
  wouldPass: boolean | null    // 보유실적 기준 통과 여부
  totalWithCurrent: number | null // 보유실적 반영 합산 점수
  expGap: number | null        // 보유 - 최소필요 (억원, 양수=초과, 음수=부족)
}

type CategoryKey = 'A' | 'B' | 'C' | 'D'

const CATEGORY_MIN: Record<CategoryKey, number> = { A: 88, B: 87, C: 86, D: 85 }

const creditMap: Record<string, number> = {
  AAA: 30, AA: 27, A: 24, BBB: 21, BB: 15, B: 10, CCC: 5, CC: 3, C: 1,
}
const CREDIT_GRADES = ['AAA','AA+','AA','AA-','A+','A','A-','BBB+','BBB','BBB-','BB+','BB','BB-','B+','B','B-','CCC','CC','C']

function getCreditBase(grade: string) { return creditMap[grade.replace(/[+-]/g, '')] ?? 10 }
function getCatKey(grade: string): CategoryKey {
  const base = grade.replace(/[+-]/g, '')
  return (base.startsWith('A') ? 'A' : base.startsWith('B') ? 'B' : base.startsWith('C') ? 'C' : 'D') as CategoryKey
}
function fmtBillion(v: number) { return v.toFixed(2) + '억원' }
function fmtPct(v: number) { return (v * 100).toFixed(3) + '%' }
function fmtAmountKrw(v: number) {
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '억원'
  return (v / 1e4).toFixed(0) + '만원'
}

function calcQualification(params: {
  baseAmount: number
  ownShare: number
  constructionExperience: number
  creditGrade: string
  safetyScore: number
  isRegional: boolean
}): CalcResult {
  const { baseAmount, ownShare, constructionExperience, creditGrade, safetyScore, isRegional } = params
  const amtBillion = baseAmount / 1e8

  const expRequired = amtBillion * (ownShare / 100) * 0.7
  const expRatio = constructionExperience > 0 ? Math.min(constructionExperience / Math.max(expRequired, 0.01), 1) : 0
  const expScore = +(expRatio * 30).toFixed(2)

  const creditScore = getCreditBase(creditGrade)
  const taxScore = 20
  const safeScore = Math.min(safetyScore, 10)
  const regionalBonus = isRegional ? 2 : 0

  const total = expScore + creditScore + taxScore + safeScore + regionalBonus
  const cat = getCatKey(creditGrade)
  const minRate = CATEGORY_MIN[cat] / 100
  const optimalRate = minRate + 0.01

  return {
    pass: total >= 65,
    totalScore: +total.toFixed(2),
    minScore: 65,
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

function calcReverse(params: {
  baseAmount: number
  ownShare: number
  creditGrade: string
  safetyScore: number
  isRegional: boolean
  currentExpBillion: number | null
}): ReverseResult {
  const { baseAmount, ownShare, creditGrade, safetyScore, isRegional, currentExpBillion } = params
  const amtBillion = baseAmount / 1e8

  const creditScore = getCreditBase(creditGrade)
  const taxScore = 20
  const safeScore = Math.min(safetyScore, 10)
  const regionalBonus = isRegional ? 2 : 0
  const nonPriceScore = creditScore + taxScore + safeScore + regionalBonus

  const expScoreNeeded = 65 - nonPriceScore
  const expRequired = amtBillion * (ownShare / 100) * 0.7

  let minExpBillion: number | null = null
  if (expScoreNeeded <= 0) {
    minExpBillion = 0
  } else if (expScoreNeeded <= 30) {
    minExpBillion = expRequired * (expScoreNeeded / 30)
  }

  const cat = getCatKey(creditGrade)
  const minRate = CATEGORY_MIN[cat] / 100
  const minAmount = baseAmount * minRate

  let currentExpScore: number | null = null
  let wouldPass: boolean | null = null
  let totalWithCurrent: number | null = null
  let expGap: number | null = null

  if (currentExpBillion !== null && currentExpBillion >= 0) {
    const expRatio = currentExpBillion > 0 ? Math.min(currentExpBillion / Math.max(expRequired, 0.01), 1) : 0
    currentExpScore = +(expRatio * 30).toFixed(2)
    totalWithCurrent = +(currentExpScore + nonPriceScore).toFixed(2)
    wouldPass = totalWithCurrent >= 65
    expGap = minExpBillion !== null ? +(currentExpBillion - minExpBillion).toFixed(2) : null
  }

  return {
    nonPriceScore: +nonPriceScore.toFixed(2),
    expScoreNeeded: +Math.max(0, expScoreNeeded).toFixed(2),
    impossible: expScoreNeeded > 30,
    noExpNeeded: expScoreNeeded <= 0,
    expRequired: +expRequired.toFixed(2),
    minExpBillion,
    minRate,
    minAmount,
    currentExpScore,
    wouldPass,
    totalWithCurrent,
    expGap,
  }
}

function parseWon(s: string) { return Number(s.replace(/,/g, '')) }

export default function QualificationPage() {
  const [mode, setMode] = useState<'forward' | 'reverse'>('forward')

  // shared inputs
  const [baseAmount, setBaseAmount] = useState('')
  const [ownShare, setOwnShare]     = useState('100')
  const [credit, setCredit]         = useState('A')
  const [safety, setSafety]         = useState('8')
  const [regional, setRegional]     = useState(false)

  // forward-only
  const [expAmt, setExpAmt]         = useState('')
  const [result, setResult]         = useState<CalcResult | null>(null)

  // reverse
  const [revExpAmt, setRevExpAmt]   = useState('')  // optional: 보유실적
  const [revResult, setRevResult]   = useState<ReverseResult | null>(null)

  const handleCalc = () => {
    const base = parseWon(baseAmount)
    if (!base || base <= 0) return
    setResult(calcQualification({
      baseAmount: base,
      ownShare: Number(ownShare) || 100,
      constructionExperience: parseWon(expAmt) / 1e8,
      creditGrade: credit,
      safetyScore: Number(safety) || 0,
      isRegional: regional,
    }))
  }

  const handleReverse = () => {
    const base = parseWon(baseAmount)
    if (!base || base <= 0) return
    const currentExpRaw = parseWon(revExpAmt)
    setRevResult(calcReverse({
      baseAmount: base,
      ownShare: Number(ownShare) || 100,
      creditGrade: credit,
      safetyScore: Number(safety) || 0,
      isRegional: regional,
      currentExpBillion: revExpAmt ? currentExpRaw / 1e8 : null,
    }))
  }

  const base = parseWon(baseAmount)

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

      {/* 모드 탭 */}
      <div className="flex gap-2 border-b pb-0">
        <button
          onClick={() => setMode('forward')}
          className={cn(
            'px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px',
            mode === 'forward'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground',
          )}
        >
          정산 계산 — 심사 통과 여부
        </button>
        <button
          onClick={() => setMode('reverse')}
          className={cn(
            'px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px flex items-center gap-1.5',
            mode === 'reverse'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground',
          )}
        >
          <ArrowRightLeft className="h-3.5 w-3.5" />
          역산 계산 — 최소 시공실적·투찰금액
        </button>
      </div>

      {/* 공통 입력 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">기본 정보 입력</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label>발주금액 (원) *</Label>
              <Input placeholder="예: 3000000000" value={baseAmount}
                onChange={(e) => setBaseAmount(e.target.value)} />
              {base > 0 && (
                <p className="text-xs text-muted-foreground">{(base / 1e8).toFixed(1)}억원</p>
              )}
            </div>

            <div className="space-y-2">
              <Label>자사 지분율 (%)</Label>
              <Input type="number" min="1" max="100" value={ownShare}
                onChange={(e) => setOwnShare(e.target.value)} />
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

            {/* 모드별 추가 입력 */}
            {mode === 'forward' && (
              <div className="space-y-2">
                <Label>시공실적 (원) *</Label>
                <Input placeholder="예: 2000000000" value={expAmt}
                  onChange={(e) => setExpAmt(e.target.value)} />
                {expAmt && parseWon(expAmt) > 0 && (
                  <p className="text-xs text-muted-foreground">{(parseWon(expAmt) / 1e8).toFixed(1)}억원</p>
                )}
              </div>
            )}

            {mode === 'reverse' && (
              <div className="space-y-2">
                <Label>보유 시공실적 (원, 선택)</Label>
                <Input placeholder="입력 시 통과 여부 비교" value={revExpAmt}
                  onChange={(e) => setRevExpAmt(e.target.value)} />
                {revExpAmt && parseWon(revExpAmt) > 0 && (
                  <p className="text-xs text-muted-foreground">{(parseWon(revExpAmt) / 1e8).toFixed(1)}억원</p>
                )}
              </div>
            )}
          </div>

          {mode === 'forward' ? (
            <Button onClick={handleCalc} disabled={!baseAmount || !expAmt} className="gap-2">
              <Calculator className="h-4 w-4" /> 심사 계산
            </Button>
          ) : (
            <Button onClick={handleReverse} disabled={!baseAmount} className="gap-2">
              <ArrowRightLeft className="h-4 w-4" /> 역산 계산
            </Button>
          )}
        </CardContent>
      </Card>

      {/* ── 정산 결과 ── */}
      {mode === 'forward' && result && (
        <div className="space-y-4">
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

              <div className="w-full bg-muted rounded-full h-3 overflow-hidden mb-4">
                <div
                  className={cn('h-3 rounded-full transition-all', result.pass ? 'bg-green-500' : 'bg-red-400')}
                  style={{ width: `${Math.min(result.totalScore, 100)}%` }}
                />
              </div>

              {result.minRate != null && base > 0 && (
                <div className="grid grid-cols-2 gap-3 mt-2">
                  <div className="bg-white/70 rounded-md p-3 border">
                    <p className="text-xs text-muted-foreground">최소 투찰금액 (신용등급 기준)</p>
                    <p className="text-lg font-bold font-mono text-primary">
                      {fmtAmountKrw(base * result.minRate)}
                    </p>
                    <p className="text-xs text-muted-foreground">{fmtPct(result.minRate)}</p>
                  </div>
                  {result.optimalRate != null && (
                    <div className="bg-white/70 rounded-md p-3 border border-primary/30">
                      <p className="text-xs text-muted-foreground">권장 투찰금액</p>
                      <p className="text-lg font-bold font-mono text-primary">
                        {fmtAmountKrw(base * result.optimalRate)}
                      </p>
                      <p className="text-xs text-muted-foreground">{fmtPct(result.optimalRate)}</p>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

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

      {/* ── 역산 결과 ── */}
      {mode === 'reverse' && revResult && (
        <div className="space-y-4">
          {/* 결론 카드 */}
          {revResult.impossible ? (
            <Card className="border-2 border-red-400 bg-red-50/30">
              <CardContent className="pt-5">
                <div className="flex items-center gap-3">
                  <XCircle className="h-8 w-8 text-red-500" />
                  <div>
                    <p className="text-xl font-bold text-red-600">이 입찰 적격심사 통과 불가</p>
                    <p className="text-sm text-muted-foreground mt-0.5">
                      비가격 점수 합계 {revResult.nonPriceScore}점 + 시공실적 최대 30점 = 최대 {(revResult.nonPriceScore + 30).toFixed(0)}점 &lt; 65점
                    </p>
                  </div>
                </div>
                <div className="mt-4 p-3 bg-red-100/60 rounded-md text-sm text-red-700">
                  <strong>대응 방안:</strong> 신용등급 개선, 지역업체 요건 확인, 산업재해예방 점수 향상으로 비가격 점수를 높이세요.
                </div>
              </CardContent>
            </Card>
          ) : revResult.noExpNeeded ? (
            <Card className="border-2 border-green-400 bg-green-50/30">
              <CardContent className="pt-5">
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="h-8 w-8 text-green-600" />
                  <div>
                    <p className="text-xl font-bold text-green-700">시공실적 없이도 통과 가능</p>
                    <p className="text-sm text-muted-foreground mt-0.5">
                      비가격 점수 합계 {revResult.nonPriceScore}점 ≥ 65점 (기준)
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card className="border-2 border-blue-400 bg-blue-50/20">
              <CardContent className="pt-5">
                <div className="flex items-center gap-3 mb-4">
                  <Calculator className="h-8 w-8 text-blue-600" />
                  <div>
                    <p className="text-xl font-bold text-blue-700">통과 가능 — 최소 시공실적 필요</p>
                    <p className="text-sm text-muted-foreground mt-0.5">
                      비가격 {revResult.nonPriceScore}점 + 시공실적 {revResult.expScoreNeeded}점 이상 필요
                    </p>
                  </div>
                </div>

                {/* 핵심 결과: 최소 시공실적 */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div className="col-span-2 bg-white/80 rounded-lg p-4 border border-blue-200">
                    <p className="text-xs text-muted-foreground mb-1">최소 필요 시공실적</p>
                    <p className="text-3xl font-bold font-mono text-blue-700">
                      {revResult.minExpBillion !== null ? fmtBillion(revResult.minExpBillion) : '계산 불가'}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      만점 기준 요구실적 {fmtBillion(revResult.expRequired)} 중 {((revResult.expScoreNeeded / 30) * 100).toFixed(0)}% 이상
                    </p>
                  </div>
                  <div className="bg-white/80 rounded-lg p-4 border border-blue-200">
                    <p className="text-xs text-muted-foreground mb-1">필요 시공실적 점수</p>
                    <p className="text-2xl font-bold font-mono text-blue-700">
                      {revResult.expScoreNeeded}점
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">/ 30점 만점</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* 최소 투찰금액 */}
          {base > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">신용등급 기준 최소 투찰금액</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-muted/40 rounded-lg p-4 border">
                    <p className="text-xs text-muted-foreground mb-1">최소 투찰금액</p>
                    <p className="text-2xl font-bold font-mono text-primary">
                      {fmtAmountKrw(revResult.minAmount)}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      투찰률 {fmtPct(revResult.minRate)} ({credit.replace(/[+-]/g,'')}등급 기준)
                    </p>
                  </div>
                  <div className="bg-muted/40 rounded-lg p-4 border border-primary/20">
                    <p className="text-xs text-muted-foreground mb-1">발주금액</p>
                    <p className="text-2xl font-bold font-mono">{(base / 1e8).toFixed(2)}억원</p>
                    <p className="text-xs text-muted-foreground mt-1">기초금액 기준</p>
                  </div>
                </div>
                <div className="mt-3 text-xs text-muted-foreground flex items-start gap-1.5">
                  <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  <span>
                    신용등급 {credit.replace(/[+-]/g,'')}: 최소 투찰률 {revResult.minRate * 100}% (A등급 88%, B등급 87%, C등급 86%, D등급 85%)
                  </span>
                </div>
              </CardContent>
            </Card>
          )}

          {/* 비가격 점수 분해 */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">비가격 점수 구성 (고정 항목)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {[
                { label: '경영상태 (신용등급)', score: getCreditBase(credit), max: 30, note: credit },
                { label: '납세실적', score: 20, max: 20, note: '이행 시 만점' },
                { label: '산업재해예방', score: Math.min(Number(safety) || 0, 10), max: 10 },
                { label: '지역업체 가산', score: regional ? 2 : 0, max: 2 },
              ].map((item) => (
                <div key={item.label}>
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span className="text-muted-foreground">{item.label}</span>
                    <div className="flex items-center gap-2">
                      {item.note && <span className="text-xs text-muted-foreground">{item.note}</span>}
                      <Badge variant={item.score >= item.max * 0.7 ? 'success' : item.score >= item.max * 0.4 ? 'warning' : 'destructive'}>
                        {item.score} / {item.max}점
                      </Badge>
                    </div>
                  </div>
                  <div className="w-full bg-muted rounded-full h-1.5">
                    <div className={cn('h-1.5 rounded-full', item.score >= item.max * 0.7 ? 'bg-green-500' : item.score >= item.max * 0.4 ? 'bg-orange-400' : 'bg-red-400')}
                      style={{ width: `${(item.score / item.max) * 100}%` }} />
                  </div>
                </div>
              ))}
              <div className="border-t pt-2 flex items-center justify-between text-sm font-semibold">
                <span>비가격 소계</span>
                <span>{revResult.nonPriceScore}점</span>
              </div>
              {!revResult.impossible && !revResult.noExpNeeded && (
                <div className="flex items-center justify-between text-sm text-blue-700 font-semibold">
                  <span>시공실적 필요 점수</span>
                  <span>+ {revResult.expScoreNeeded}점</span>
                </div>
              )}
              <div className="flex items-center justify-between text-sm font-bold border-t pt-2">
                <span>목표 합계</span>
                <span className="text-primary">65점</span>
              </div>
            </CardContent>
          </Card>

          {/* 보유 실적 비교 (선택 입력 시) */}
          {revResult.wouldPass !== null && revResult.totalWithCurrent !== null && (
            <Card className={cn('border-2', revResult.wouldPass ? 'border-green-400 bg-green-50/20' : 'border-orange-400 bg-orange-50/20')}>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  {revResult.wouldPass
                    ? <CheckCircle2 className="h-4 w-4 text-green-600" />
                    : <AlertTriangle className="h-4 w-4 text-orange-500" />}
                  보유 실적 기준 통과 여부
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-3 gap-3 text-center text-sm">
                  <div className="bg-white/60 rounded-md p-3 border">
                    <p className="text-xs text-muted-foreground">보유 시공실적 점수</p>
                    <p className="text-xl font-bold font-mono">{revResult.currentExpScore}점</p>
                    <p className="text-xs text-muted-foreground">/ 30점</p>
                  </div>
                  <div className="bg-white/60 rounded-md p-3 border">
                    <p className="text-xs text-muted-foreground">예상 합산 점수</p>
                    <p className={cn('text-xl font-bold font-mono', revResult.wouldPass ? 'text-green-700' : 'text-orange-600')}>
                      {revResult.totalWithCurrent}점
                    </p>
                    <p className="text-xs text-muted-foreground">기준 65점</p>
                  </div>
                  <div className="bg-white/60 rounded-md p-3 border">
                    <p className="text-xs text-muted-foreground">
                      {revResult.expGap !== null && revResult.expGap >= 0 ? '실적 여유' : '실적 부족'}
                    </p>
                    <p className={cn('text-xl font-bold font-mono', revResult.expGap !== null && revResult.expGap >= 0 ? 'text-green-700' : 'text-orange-600')}>
                      {revResult.expGap !== null ? `${revResult.expGap >= 0 ? '+' : ''}${revResult.expGap.toFixed(2)}억` : '-'}
                    </p>
                    <p className="text-xs text-muted-foreground">최소실적 대비</p>
                  </div>
                </div>

                {!revResult.wouldPass && revResult.expGap !== null && (
                  <div className="flex items-start gap-2 text-sm text-orange-700 bg-orange-50 border border-orange-200 rounded-md p-3">
                    <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                    <span>
                      현재 시공실적이 <strong>{Math.abs(revResult.expGap).toFixed(2)}억원 부족</strong>합니다.
                      {revResult.minExpBillion !== null
                        ? ` 최소 ${fmtBillion(revResult.minExpBillion)} 이상의 시공실적이 필요합니다.`
                        : ''}
                    </span>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
