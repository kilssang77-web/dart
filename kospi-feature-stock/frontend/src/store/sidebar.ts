import { create } from 'zustand'

interface SidebarState {
  collapsed:    boolean
  mobileOpen:   boolean
  toggle:       () => void
  openMobile:   () => void
  closeMobile:  () => void
}

export const useSidebarStore = create<SidebarState>()((set) => ({
  collapsed:   false,
  mobileOpen:  false,
  toggle:      () => set((s) => ({ collapsed: !s.collapsed })),
  openMobile:  () => set({ mobileOpen: true }),
  closeMobile: () => set({ mobileOpen: false }),
}))
