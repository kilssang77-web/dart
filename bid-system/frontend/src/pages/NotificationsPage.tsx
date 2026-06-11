import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Bell, CheckCheck, ExternalLink, Loader2, Tag, AlertTriangle, Info, BellOff } from 'lucide-react'
import { notificationsApi } from '@/api'
import type { Notification } from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

const NTYPE_CONFIG: Record<string, {
  label: string
  icon: React.ElementType
  iconBg: string
  iconColor: string
  badgeCls: string
  rowCls: string
}> = {
  keyword_match: {
    label: '키워드',
    icon: Tag,
    iconBg: 'bg-blue-50',
    iconColor: 'text-blue-600',
    badgeCls: 'bg-blue-50 text-blue-700 border-blue-200',
    rowCls: 'bg-blue-50/30',
  },
  srate_spike: {
    label: '사정율 급변',
    icon: AlertTriangle,
    iconBg: 'bg-amber-50',
    iconColor: 'text-amber-600',
    badgeCls: 'bg-amber-50 text-amber-700 border-amber-200',
    rowCls: 'bg-amber-50/20',
  },
  system: {
    label: '시스템',
    icon: Info,
    iconBg: 'bg-slate-100',
    iconColor: 'text-slate-500',
    badgeCls: 'bg-slate-100 text-slate-600 border-slate-200',
    rowCls: 'bg-white',
  },
}

function NotificationRow({
  item,
  onRead,
}: {
  item: Notification
  onRead: (id: number) => void
}) {
  const navigate = useNavigate()
  const conf = NTYPE_CONFIG[item.ntype] ?? NTYPE_CONFIG.system
  const IconComp = conf.icon

  const handleClick = () => {
    if (!item.is_read) onRead(item.id)
    if (item.link) navigate(item.link)
  }

  return (
    <div
      onClick={handleClick}
      className={cn(
        'flex items-start gap-4 px-5 py-4 border-b border-slate-100 last:border-0 transition-colors',
        item.is_read
          ? 'bg-white opacity-60'
          : cn(conf.rowCls, 'cursor-pointer hover:brightness-95'),
        item.link && !item.is_read && 'cursor-pointer',
      )}
    >
      {/* 타입 아이콘 */}
      <div className={cn('h-9 w-9 rounded-full flex items-center justify-center shrink-0', conf.iconBg)}>
        <IconComp className={cn('h-4 w-4', conf.iconColor)} />
      </div>

      {/* 본문 */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap mb-0.5">
          <span className={cn('text-xs font-semibold px-2 py-0.5 rounded-full border', conf.badgeCls)}>
            {conf.label}
          </span>
          <span className="text-xs text-slate-500">
            {new Date(item.created_at).toLocaleDateString('ko-KR', {
              month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
            })}
          </span>
        </div>
        <p className="text-sm font-semibold text-slate-800 leading-snug">{item.title}</p>
        {item.body && <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{item.body}</p>}
      </div>

      {/* 오른쪽 인디케이터 */}
      <div className="flex flex-col items-end gap-1.5 shrink-0">
        {!item.is_read && (
          <div className="h-2 w-2 rounded-full bg-blue-500" />
        )}
        {item.link && (
          <ExternalLink className={cn('h-3.5 w-3.5', item.is_read ? 'text-slate-300' : 'text-slate-500')} />
        )}
      </div>
    </div>
  )
}

export default function NotificationsPage() {
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => notificationsApi.list({ limit: 50 }),
  })

  const markRead = useMutation({
    mutationFn: notificationsApi.markRead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] })
      qc.invalidateQueries({ queryKey: ['notifications', 'unread-count'] })
    },
  })

  const markAllRead = useMutation({
    mutationFn: notificationsApi.markAllRead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] })
      qc.invalidateQueries({ queryKey: ['notifications', 'unread-count'] })
    },
  })

  const unreadCount = data?.unread_count ?? 0

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Sticky Header */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-2xl mx-auto">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <Bell className="h-5 w-5 text-blue-600" />알림
              {unreadCount > 0 && (
                <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-blue-600 text-white ml-1">
                  {unreadCount}
                </span>
              )}
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              {unreadCount > 0 ? `읽지 않은 알림 ${unreadCount}개` : '모든 알림을 확인했습니다'}
            </p>
          </div>
          {unreadCount > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => markAllRead.mutate()}
              disabled={markAllRead.isPending}
              className="gap-2 border-slate-200 text-slate-600 hover:bg-slate-50"
            >
              {markAllRead.isPending
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <CheckCheck className="h-3.5 w-3.5" />}
              전체 읽음
            </Button>
          )}
        </div>
      </div>

      <div className="max-w-2xl mx-auto p-6">
        <Card className="bg-white border-slate-200 shadow-sm overflow-hidden">
          <CardContent className="p-0">
            {isLoading ? (
              <div className="p-5 space-y-3">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="flex items-start gap-4">
                    <Skeleton className="h-9 w-9 rounded-full shrink-0" />
                    <div className="flex-1 space-y-1.5">
                      <Skeleton className="h-3 w-24" />
                      <Skeleton className="h-4 w-3/4" />
                      <Skeleton className="h-3 w-1/2" />
                    </div>
                  </div>
                ))}
              </div>
            ) : !data?.items.length ? (
              <div className="flex flex-col items-center justify-center py-20 text-slate-500 gap-3">
                <div className="h-16 w-16 rounded-full bg-slate-50 flex items-center justify-center">
                  <BellOff className="h-7 w-7 text-slate-300" />
                </div>
                <div className="text-center">
                  <p className="text-sm font-medium text-slate-500">알림이 없습니다</p>
                  <p className="text-xs text-slate-500 mt-1">새 공고나 시스템 알림이 여기에 표시됩니다</p>
                </div>
              </div>
            ) : (
              <>
                {/* 읽지 않은 알림 구분 헤더 */}
                {unreadCount > 0 && (
                  <div className="px-5 py-2.5 bg-slate-50 border-b border-slate-100">
                    <p className="text-xs font-semibold text-slate-500">읽지 않음 ({unreadCount})</p>
                  </div>
                )}
                {data.items.map((item) => (
                  <NotificationRow
                    key={item.id}
                    item={item}
                    onRead={(id) => markRead.mutate(id)}
                  />
                ))}
              </>
            )}
          </CardContent>
        </Card>

        {/* 알림 타입 범례 */}
        {data && data.items.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-3">
            {Object.entries(NTYPE_CONFIG).map(([key, conf]) => {
              const IconComp = conf.icon
              return (
                <div key={key} className="flex items-center gap-1.5 text-xs text-slate-500">
                  <div className={cn('h-5 w-5 rounded-full flex items-center justify-center', conf.iconBg)}>
                    <IconComp className={cn('h-3 w-3', conf.iconColor)} />
                  </div>
                  {conf.label}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
