import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useIsFetching } from '@tanstack/react-query'

/**
 * 페이지 이동 + API 초기 로딩 시 상단에 얇은 진행 바를 표시.
 * - 네비게이션: 700ms 후 자동 완료
 * - API 초기 로딩(status=pending): 데이터 도착까지 유지
 */
export function TopLoadingBar() {
  const location = useLocation()
  // 데이터 없이 처음 로딩 중인 쿼리만 집계 (background refetch 제외)
  const isFetching = useIsFetching({
    predicate: (query) => query.state.status === 'pending',
  })

  const [width,   setWidth]   = useState(0)
  const [visible, setVisible] = useState(false)
  const timers = useRef<ReturnType<typeof setTimeout>[]>([])

  const clearAll = () => {
    timers.current.forEach(clearTimeout)
    timers.current = []
  }

  const after = (fn: () => void, ms: number) => {
    const t = setTimeout(fn, ms)
    timers.current.push(t)
  }

  const startBar = () => {
    clearAll()
    setVisible(true)
    setWidth(20)
    after(() => setWidth(50), 120)
    after(() => setWidth(78), 350)
  }

  const finishBar = () => {
    clearAll()
    setWidth(100)
    after(() => { setVisible(false); setWidth(0) }, 380)
  }

  // 네비게이션 → 시작 후 700ms 자동 완료 (API 로딩 없을 때)
  useEffect(() => {
    startBar()
    after(finishBar, 700)
    return clearAll
  }, [location.pathname, location.search])

  // API 초기 로딩 → 로딩 시작 시 바 유지, 완료 시 종료
  const prevFetch = useRef(0)
  useEffect(() => {
    const was = prevFetch.current
    prevFetch.current = isFetching
    if (isFetching > 0 && was === 0) {
      startBar()           // 새 로딩 시작: 타이머 재설정 (nav auto-finish 취소)
    } else if (isFetching === 0 && was > 0) {
      finishBar()          // 모든 초기 로딩 완료
    }
  }, [isFetching])

  if (!visible) return null

  return (
    <div
      className="fixed top-0 left-0 right-0 z-[9999] pointer-events-none"
      style={{ height: 3 }}
    >
      <div
        style={{
          height: '100%',
          width: `${width}%`,
          background: 'linear-gradient(90deg, #22d3ee 0%, #818cf8 60%, #a78bfa 100%)',
          boxShadow: '0 0 10px rgba(34,211,238,0.55)',
          opacity: width === 100 ? 0 : 1,
          transition: width === 100
            ? 'width 0.15s ease-out, opacity 0.35s ease-out'
            : 'width 0.38s cubic-bezier(0.4,0,0.2,1)',
        }}
      />
    </div>
  )
}
