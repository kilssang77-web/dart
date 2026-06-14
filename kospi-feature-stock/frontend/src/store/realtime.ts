import { create } from 'zustand'

interface RealtimeState {
  isConnected: boolean
  setConnected: (v: boolean) => void
}

export const useRealtimeStore = create<RealtimeState>((set) => ({
  isConnected: false,
  setConnected: (v) => set({ isConnected: v }),
}))