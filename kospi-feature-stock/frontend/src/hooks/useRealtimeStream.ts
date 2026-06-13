import { useEffect, useRef, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useRealtimeStore } from '@/store/realtime'

export interface StreamFeature {
  code:          string
  detected_at:   string
  event_type:    string
  price?:        number
  change_rate?:  number
  volume?:       number
  volume_ratio?: number
  amount?:       number
  signal_score?: number
  risk_score?:   number
  signal_data?:  Record<string, unknown>
}

export interface StreamRecommendation {
  code:               string
  created_at:         string
  action:             'BUY' | 'WAIT' | 'SKIP'
  entry_price:        number
  entry_price_low?:   number
  entry_price_high?:  number
  target_price:       number
  stop_loss_price:    number
  expected_hold_days: number
  success_prob:       number
  expected_return:    number
  risk_score:         number
  risk_reward_ratio:  number
  rationale:          Record<string, unknown>
  similar_cases:      unknown[]
}

interface Options {
  onFeature?:         (ev: StreamFeature) => void
  onRecommendation?:  (rec: StreamRecommendation) => void
  enabled?:           boolean
  invalidateQueries?: boolean
}

const RETRY_DELAYS = [1_000, 2_000, 5_000, 10_000, 30_000]

function wsBase() {
  return `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
}

export function useRealtimeStream({
  onFeature,
  onRecommendation,
  enabled = true,
  invalidateQueries = true,
}: Options = {}) {
  const queryClient  = useQueryClient()
  const setConnected = useRealtimeStore((s) => s.setConnected)
  const wsRef        = useRef<WebSocket | null>(null)
  const retryRef     = useRef(0)
  const timerRef     = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef   = useRef(true)
  const onFeatureRef    = useRef(onFeature)
  const onRecommendRef  = useRef(onRecommendation)
  onFeatureRef.current  = onFeature
  onRecommendRef.current = onRecommendation

  const connect = useCallback(() => {
    if (!mountedRef.current || !enabled) return

    const ws = new WebSocket(`${wsBase()}/ws/realtime`)
    ws.binaryType = 'arraybuffer'
    wsRef.current  = ws

    ws.onopen = () => {
      retryRef.current = 0
      setConnected(true)
    }

    ws.onmessage = (ev) => {
      try {
        const raw = ev.data instanceof ArrayBuffer
          ? new TextDecoder().decode(ev.data)
          : (ev.data as string)
        const msg = JSON.parse(raw)
        if (!msg || typeof msg !== 'object') return

        if ('event_type' in msg) {
          onFeatureRef.current?.(msg as StreamFeature)
          if (invalidateQueries) {
            queryClient.invalidateQueries({ queryKey: ['features'] })
            queryClient.invalidateQueries({ queryKey: ['features-recent'] })
            queryClient.invalidateQueries({ queryKey: ['today-summary'] })
          }
        } else if ('action' in msg) {
          onRecommendRef.current?.(msg as StreamRecommendation)
          if (invalidateQueries) {
            queryClient.invalidateQueries({ queryKey: ['top-recs'] })
            queryClient.invalidateQueries({ queryKey: ['recommendations'] })
          }
        }
      } catch {
        // ignore malformed
      }
    }

    ws.onclose = () => {
      setConnected(false)
      if (!mountedRef.current) return
      const delay = RETRY_DELAYS[Math.min(retryRef.current, RETRY_DELAYS.length - 1)]
      retryRef.current += 1
      timerRef.current = setTimeout(connect, delay)
    }

    ws.onerror = () => ws.close()
  }, [enabled, invalidateQueries, queryClient, setConnected])

  useEffect(() => {
    mountedRef.current = true
    if (enabled) connect()
    return () => {
      mountedRef.current = false
      setConnected(false)
      if (timerRef.current) clearTimeout(timerRef.current)
      wsRef.current?.close()
    }
  }, [connect, enabled, setConnected])

  return {
    isConnected: useRealtimeStore.getState().isConnected,
  }
}