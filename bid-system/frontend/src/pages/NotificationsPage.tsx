import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Bell, CheckCheck, ExternalLink, Loader2 } from 'lucide-react'
import { notificationsApi } from '@/api'
import type { Notification } from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

const NTYPE_LABELS: Record<string, string> = {
  keyword_match: '키워드',
  srate_spike:   '사정율',
  system:        '시스템',
}

const NTYPE_COLORS: Record<string, string> = {
  keyword_match: 'bg-blue-100 text-blue-700',
  srate_spike:   'bg-orange-100 text-orange-700',
  system:        'bg-gray-100 text-gray-600',
}

function NotificationRow({
  item,
  onRead,
}: {
  item: Notification
  onRead: (id: number) => void
}) {
  const navigate = useNavigate()

  const handleClick = () => {
    if (!item.is_read) onRead(item.id)
    if (item.link) navigate(item.link)
  }

  return (
    <div
      onClick={handleClick}
      className={cn(
        'flex items-start gap-3 px-4 py-3 border-b last:border-b-0 transition-colors',
        item.is_read ? 'opacity-60' : 'bg-blue-50/40 cursor-pointer hover:bg-blue-50',
        item.link && 'cursor-pointer',
      )}
    >
      <div className={cn('mt-0.5 shrink-0 w-2 h-2 rounded-full', item.is_read ? 'bg-transparent' : 'bg-blue-500')} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="outline" className={cn('text-[10px] px-1.5 py-0 h-4', NTYPE_COLORS[item.ntype] ?? 'bg-gray-100 text-gray-600')}>
            {NTYPE_LABELS[item.ntype] ?? item.ntype}
          </Badge>
          <span className="text-xs text-muted-foreground">
            {new Date(item.created_at).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
        <p className="text-sm font-medium mt-0.5">{item.title}</p>
        {item.body && <p className="text-xs text-muted-foreground mt-0.5">{item.body}</p>}
      </div>
      {item.link && <ExternalLink className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-1" />}
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
    <div className="p-6 max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Bell className="h-5 w-5" />
          <h1 className="text-xl font-bold">알림</h1>
          {unreadCount > 0 && (
            <Badge variant="destructive" className="text-xs">{unreadCount}개 미읽음</Badge>
          )}
        </div>
        {unreadCount > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => markAllRead.mutate()}
            disabled={markAllRead.isPending}
            className="gap-1.5"
          >
            {markAllRead.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCheck className="h-3.5 w-3.5" />}
            모두 읽음
          </Button>
        )}
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
            </div>
          ) : !data?.items.length ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-2">
              <Bell className="h-10 w-10 opacity-20" />
              <p className="text-sm">알림이 없습니다</p>
            </div>
          ) : (
            data.items.map((item) => (
              <NotificationRow
                key={item.id}
                item={item}
                onRead={(id) => markRead.mutate(id)}
              />
            ))
          )}
        </CardContent>
      </Card>
    </div>
  )
}
