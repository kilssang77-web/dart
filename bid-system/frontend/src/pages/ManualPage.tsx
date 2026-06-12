import { useState, useEffect, useRef } from 'react'
import { Search, ChevronRight, ChevronDown, X, BookOpen, Menu } from 'lucide-react'
import { MANUAL_SECTIONS } from './ManualData'

/* ─────────────────────────────────────────────────
   목차 구성
───────────────────────────────────────────────── */
interface TocItem { id: string; label: string; level: 1 | 2 }

function buildToc(): TocItem[] {
  const toc: TocItem[] = []
  MANUAL_SECTIONS.forEach((s, i) => {
    if (s.type === 'h1') toc.push({ id: `sec-${i}`, label: s.text, level: 1 })
    if (s.type === 'h2') toc.push({ id: `sec-${i}`, label: s.text, level: 2 })
  })
  return toc
}

const TOC = buildToc()

/* ─────────────────────────────────────────────────
   검색 하이라이트
───────────────────────────────────────────────── */
function Highlight({ text, query }: { text: string; query: string }) {
  if (!query.trim()) return <>{text}</>
  const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'))
  return (
    <>
      {parts.map((p, i) =>
        p.toLowerCase() === query.toLowerCase()
          ? <mark key={i} className="bg-yellow-300/80 text-slate-900 rounded-sm px-0.5">{p}</mark>
          : <span key={i}>{p}</span>
      )}
    </>
  )
}

/* ─────────────────────────────────────────────────
   콘텐츠 렌더러
───────────────────────────────────────────────── */
function ManualContent({ query }: { query: string }) {
  return (
    <div className="prose prose-slate max-w-none">
      {MANUAL_SECTIONS.map((s, i) => {
        const id = `sec-${i}`
        const hl = (t: string) => <Highlight text={t} query={query} />

        if (s.type === 'h1') return (
          <h1 key={i} id={id}
            className="text-2xl font-bold text-slate-900 mt-10 mb-4 pb-3 border-b-2 border-blue-600 scroll-mt-20">
            {hl(s.text)}
          </h1>
        )
        if (s.type === 'h2') return (
          <h2 key={i} id={id}
            className="text-lg font-bold text-blue-700 mt-8 mb-3 scroll-mt-20">
            {hl(s.text)}
          </h2>
        )
        if (s.type === 'h3') return (
          <h3 key={i}
            className="text-base font-semibold text-slate-700 mt-5 mb-2">
            {hl(s.text)}
          </h3>
        )
        if (s.type === 'li') return (
          <li key={i}
            className="ml-5 text-[14px] text-slate-700 leading-relaxed list-disc marker:text-blue-400 mb-1">
            {hl(s.text)}
          </li>
        )
        // p
        const text = s.text
        // 박스 패턴 감지 (💡, ⚠️, ★, 【 로 시작)
        if (/^[💡⚠️★【]/.test(text)) return (
          <div key={i}
            className="my-3 px-4 py-3 bg-blue-50 border-l-4 border-blue-500 rounded-r-lg text-[13.5px] text-slate-700 leading-relaxed">
            {hl(text)}
          </div>
        )
        // 코드 패턴 (공백 4개 이상 들여쓰기나 명령어처럼 보이는 것)
        if (/^\s{4}|^(docker|npm|pip|git|cd|python|curl)\b/.test(text)) return (
          <pre key={i}
            className="my-2 px-4 py-3 bg-slate-800 text-emerald-300 rounded-lg text-xs font-mono leading-relaxed overflow-x-auto whitespace-pre-wrap">
            {text}
          </pre>
        )
        // 표 행 패턴 (|로 구분)
        if (/^\|.+\|$/.test(text)) return (
          <div key={i}
            className="text-[13px] font-mono text-slate-600 bg-slate-50 px-3 py-1 border-b border-slate-200">
            {text}
          </div>
        )
        // 일반 단락
        return (
          <p key={i}
            className="text-[14px] text-slate-700 leading-relaxed mb-2">
            {hl(text)}
          </p>
        )
      })}
    </div>
  )
}

/* ─────────────────────────────────────────────────
   메인 ManualPage
───────────────────────────────────────────────── */
export default function ManualPage() {
  const [query, setQuery]         = useState('')
  const [tocOpen, setTocOpen]     = useState(true)
  const [activeId, setActiveId]   = useState('')
  const contentRef = useRef<HTMLDivElement>(null)
  const isPopup = window.opener !== null

  /* 스크롤 감지 → 활성 목차 업데이트 */
  useEffect(() => {
    const el = contentRef.current
    if (!el) return
    const handler = () => {
      const headings = el.querySelectorAll('[id^="sec-"]')
      let cur = ''
      headings.forEach(h => {
        const rect = h.getBoundingClientRect()
        if (rect.top <= 120) cur = h.id
      })
      setActiveId(cur)
    }
    el.addEventListener('scroll', handler)
    return () => el.removeEventListener('scroll', handler)
  }, [])

  const scrollTo = (id: string) => {
    const el = contentRef.current?.querySelector(`#${id}`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  /* 검색 결과 건수 */
  const matchCount = query.trim()
    ? MANUAL_SECTIONS.filter(s => s.text.toLowerCase().includes(query.toLowerCase())).length
    : 0

  return (
    <div className="flex flex-col h-screen bg-white overflow-hidden" style={{ fontFamily: "'Pretendard', 'Noto Sans KR', sans-serif" }}>

      {/* ── 상단 헤더 ── */}
      <header className="flex items-center gap-4 px-5 h-14 border-b border-slate-200 bg-white shrink-0 shadow-sm">
        <button
          onClick={() => setTocOpen(!tocOpen)}
          className="flex items-center justify-center w-8 h-8 rounded-lg text-slate-500 hover:bg-slate-100 transition-colors"
          title="목차 토글"
        >
          <Menu className="w-4 h-4" />
        </button>
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-600">
            <BookOpen className="h-4 w-4 text-white" />
          </div>
          <div>
            <p className="text-[15px] font-bold text-slate-800 leading-none">BidAI Pro</p>
            <p className="text-[11px] text-blue-600 leading-none mt-0.5">사용자 매뉴얼 v1.0</p>
          </div>
        </div>

        {/* 검색창 */}
        <div className="flex-1 max-w-md ml-4 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="매뉴얼 검색..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-1.5 text-sm border border-slate-200 rounded-lg bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:bg-white"
          />
          {query && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2">
              <span className="text-xs text-blue-600 font-medium">{matchCount}건</span>
              <button onClick={() => setQuery('')}>
                <X className="w-3.5 h-3.5 text-slate-400 hover:text-slate-600" />
              </button>
            </div>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-slate-400">2026-06-12</span>
          {isPopup && (
            <button
              onClick={() => window.close()}
              className="flex items-center justify-center w-7 h-7 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
              title="창 닫기"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* ── 목차 사이드바 ── */}
        {tocOpen && (
          <aside className="w-64 shrink-0 border-r border-slate-200 bg-slate-50 overflow-y-auto">
            <div className="px-4 py-3 border-b border-slate-200">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">목차</p>
            </div>
            <nav className="py-2">
              {TOC.map(item => (
                <button
                  key={item.id}
                  onClick={() => scrollTo(item.id)}
                  className={`
                    w-full text-left px-4 py-1.5 text-[12.5px] leading-snug transition-colors
                    ${item.level === 1
                      ? 'font-semibold text-slate-700 hover:bg-slate-200 hover:text-blue-700'
                      : 'pl-7 font-normal text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                    }
                    ${activeId === item.id ? (item.level === 1 ? 'bg-blue-50 text-blue-700 border-r-2 border-blue-500' : 'bg-blue-50 text-blue-600') : ''}
                  `}
                >
                  {item.level === 2 && <span className="text-slate-300 mr-1.5">└</span>}
                  {item.label}
                </button>
              ))}
            </nav>
          </aside>
        )}

        {/* ── 본문 ── */}
        <div ref={contentRef} className="flex-1 overflow-y-auto">
          <div className="max-w-4xl mx-auto px-8 py-8">

            {/* 표지 영역 */}
            <div className="mb-10 p-8 bg-gradient-to-br from-blue-600 to-blue-800 rounded-2xl text-white text-center shadow-xl">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white/20 mx-auto mb-4">
                <BookOpen className="h-8 w-8 text-white" />
              </div>
              <h1 className="text-3xl font-bold">BidAI Pro</h1>
              <p className="text-blue-200 text-lg mt-1">나라장터 입찰 AI 추천 시스템</p>
              <div className="mt-4 inline-block px-5 py-2 bg-white/20 rounded-full text-sm font-medium">
                사용자 매뉴얼 v1.0 · 2026-06-12
              </div>
              <p className="text-blue-200 text-sm mt-3">26장 구성 · 부록 3개 · 전 기능 스크린샷 포함</p>
            </div>

            {/* 본문 콘텐츠 */}
            <ManualContent query={query} />

            <div className="mt-16 pt-8 border-t border-slate-200 text-center text-xs text-slate-400">
              BidAI Pro 사용자 매뉴얼 v1.0 · 2026-06-12 · © A2M
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
