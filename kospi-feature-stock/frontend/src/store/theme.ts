import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface ThemeState {
  mode: 'dark' | 'light'
  toggle: () => void
  setMode: (mode: 'dark' | 'light') => void
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      mode: 'dark',
      toggle: () =>
        set((s) => {
          const next = s.mode === 'dark' ? 'light' : 'dark'
          applyTheme(next)
          return { mode: next }
        }),
      setMode: (mode) => {
        applyTheme(mode)
        set({ mode })
      },
    }),
    { name: 'fstock-theme' }
  )
)

function applyTheme(mode: 'dark' | 'light') {
  const root = document.documentElement
  if (mode === 'dark') {
    root.classList.add('dark')
  } else {
    root.classList.remove('dark')
  }
}

// 앱 초기화 시 저장된 테마 적용
const saved = localStorage.getItem('fstock-theme')
if (saved) {
  try {
    const { state } = JSON.parse(saved)
    applyTheme(state?.mode ?? 'dark')
  } catch {
    applyTheme('dark')
  }
} else {
  applyTheme('dark')
}
