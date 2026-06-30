import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'

/**
 * 페이지 이동 시 상단에 얇은 진행 바를 표시.
 * useLocation 변화를 감지 → 짧은 애니메이션 후 사라짐.
 */
export function TopLoadingBar() {
  const location = useLocation()
  const [progress, setProgress] = useState(0)
  const [visible, setVisible] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const animRef  = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    // 이전 타이머 정리
    if (timerRef.current) clearTimeout(timerRef.current)
    if (animRef.current)  clearTimeout(animRef.current)

    // 시작: 즉시 30%까지 빠르게 채우기
    setVisible(true)
    setProgress(30)

    // 70%까지 점진 진행
    timerRef.current = setTimeout(() => setProgress(70), 150)

    // 90%에서 잠시 멈춤 (데이터 로딩 대기 효과)
    animRef.current = setTimeout(() => {
      setProgress(95)
      // 완료: 100%로 채운 뒤 숨김
      timerRef.current = setTimeout(() => {
        setProgress(100)
        animRef.current = setTimeout(() => {
          setVisible(false)
          setProgress(0)
        }, 300)
      }, 200)
    }, 400)

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      if (animRef.current)  clearTimeout(animRef.current)
    }
  }, [location.pathname, location.search])

  if (!visible && progress === 0) return null

  return (
    <div
      className="fixed top-0 left-0 right-0 z-[9999] pointer-events-none"
      style={{ height: 3 }}
    >
      <div
        style={{
          height: '100%',
          width: `${progress}%`,
          background: 'linear-gradient(90deg, #22d3ee 0%, #818cf8 60%, #a78bfa 100%)',
          boxShadow: '0 0 8px rgba(34,211,238,0.6)',
          transition: progress === 100
            ? 'width 0.15s ease-out, opacity 0.3s ease-out'
            : 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          opacity: progress === 100 ? 0 : 1,
        }}
      />
    </div>
  )
}
