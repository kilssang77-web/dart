import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import {
  UserCircle2, KeyRound, Eye, EyeOff, CheckCircle, XCircle,
  UserPlus, Pencil, Trash2, ShieldCheck, ShieldOff, RotateCcw, X,
} from 'lucide-react'
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import { useAuthStore } from '@/store/auth'
import {
  apiChangePassword, apiListUsers, apiCreateUser, apiUpdateUser, apiDeleteUser,
} from '@/api/auth'
import type { UserOut } from '@/api/auth'

// ── 비밀번호 변경 ─────────────────────────────────────────────────────────────
function ChangePasswordCard() {
  const token = useAuthStore((s) => s.token)
  const user  = useAuthStore((s) => s.user)
  const [cur,     setCur]     = useState('')
  const [next,    setNext]    = useState('')
  const [confirm, setConfirm] = useState('')
  const [showCur,  setShowCur]  = useState(false)
  const [showNext, setShowNext] = useState(false)
  const [status,  setStatus]  = useState<'idle' | 'ok' | 'err'>('idle')
  const [errMsg,  setErrMsg]  = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setStatus('idle')
    if (next.length < 8)    { setStatus('err'); setErrMsg('새 비밀번호는 8자 이상이어야 합니다'); return }
    if (next !== confirm)   { setStatus('err'); setErrMsg('새 비밀번호와 확인이 일치하지 않습니다'); return }
    if (!token) return
    setLoading(true)
    try {
      await apiChangePassword(token, cur, next)
      setStatus('ok')
      setCur(''); setNext(''); setConfirm('')
    } catch (err: unknown) {
      setStatus('err')
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErrMsg(msg ?? '비밀번호 변경에 실패했습니다')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <UserCircle2 size={15} className="text-cyan-400" />
          <CardTitle>내 계정</CardTitle>
        </div>
        <div className="text-xs text-[var(--muted)] mt-0.5">
          로그인 아이디: <code className="text-cyan-400">{user?.username}</code>
          &nbsp;·&nbsp;표시이름: <span className="text-[var(--fg)]">{user?.display_name}</span>
        </div>
      </CardHeader>
      <CardBody className="pt-3">
        <div className="flex items-center gap-2 mb-4">
          <KeyRound size={14} className="text-[var(--muted)]" />
          <span className="text-sm font-semibold text-[var(--fg)]">비밀번호 변경</span>
        </div>
        <form onSubmit={handleSubmit} className="space-y-3 max-w-sm">
          <div>
            <label className="text-xs text-[var(--muted)] mb-1 block">현재 비밀번호</label>
            <div className="relative">
              <input
                type={showCur ? 'text' : 'password'}
                value={cur} onChange={(e) => setCur(e.target.value)} required
                placeholder="현재 비밀번호 입력"
                className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-xl px-3 py-2.5 pr-9 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500"
              />
              <button type="button" onClick={() => setShowCur(!showCur)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--muted)] hover:text-[var(--fg)]">
                {showCur ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>
          <div>
            <label className="text-xs text-[var(--muted)] mb-1 block">새 비밀번호 <span className="opacity-60">(8자 이상)</span></label>
            <div className="relative">
              <input
                type={showNext ? 'text' : 'password'}
                value={next} onChange={(e) => setNext(e.target.value)} required
                placeholder="새 비밀번호 입력"
                className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-xl px-3 py-2.5 pr-9 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500"
              />
              <button type="button" onClick={() => setShowNext(!showNext)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--muted)] hover:text-[var(--fg)]">
                {showNext ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>
          <div>
            <label className="text-xs text-[var(--muted)] mb-1 block">새 비밀번호 확인</label>
            <input
              type="password"
              value={confirm} onChange={(e) => setConfirm(e.target.value)} required
              placeholder="새 비밀번호 재입력"
              className={clsx(
                'w-full bg-[var(--bg)] border rounded-xl px-3 py-2.5 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none',
                confirm && next !== confirm
                  ? 'border-red-500/60 focus:border-red-500'
                  : 'border-[var(--border)] focus:border-cyan-500',
              )}
            />
            {confirm && next !== confirm && (
              <p className="text-xs text-red-400 mt-1">비밀번호가 일치하지 않습니다</p>
            )}
          </div>
          {status === 'ok' && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-green-500/10 border border-green-500/25 text-green-400 text-sm">
              <CheckCircle size={14} /> 비밀번호가 변경되었습니다
            </div>
          )}
          {status === 'err' && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-red-500/10 border border-red-500/25 text-red-400 text-sm">
              <XCircle size={14} /> {errMsg}
            </div>
          )}
          <button
            type="submit"
            disabled={loading || !cur || !next || !confirm}
            className="w-full py-2.5 rounded-xl text-sm font-semibold transition-colors bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/20 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? '변경 중…' : '비밀번호 변경'}
          </button>
        </form>
      </CardBody>
    </Card>
  )
}

// ── 사용자 추가/수정 모달 ─────────────────────────────────────────────────────
interface UserModalProps {
  mode: 'add' | 'edit'
  target?: UserOut
  onClose: () => void
  onDone: () => void
}

function UserModal({ mode, target, onClose, onDone }: UserModalProps) {
  const token = useAuthStore((s) => s.token)!
  const [username,    setUsername]    = useState(target?.username ?? '')
  const [displayName, setDisplayName] = useState(target?.display_name ?? '')
  const [password,    setPassword]    = useState('')
  const [showPw,      setShowPw]      = useState(false)
  const [errMsg,      setErrMsg]      = useState('')
  const [loading,     setLoading]     = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrMsg('')
    if (mode === 'add' && password.length < 8) { setErrMsg('비밀번호는 8자 이상이어야 합니다'); return }
    if (mode === 'edit' && password && password.length < 8) { setErrMsg('새 비밀번호는 8자 이상이어야 합니다'); return }
    setLoading(true)
    try {
      if (mode === 'add') {
        await apiCreateUser(token, username.trim(), password, displayName.trim() || undefined)
      } else {
        const body: { display_name?: string; new_password?: string } = {}
        if (displayName.trim() !== (target?.display_name ?? '')) body.display_name = displayName.trim()
        if (password) body.new_password = password
        await apiUpdateUser(token, target!.username, body)
      }
      onDone()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErrMsg(msg ?? '처리에 실패했습니다')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-md bg-[var(--surface)] border border-[var(--border)] rounded-2xl shadow-2xl p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-bold text-[var(--fg)]">
            {mode === 'add' ? '사용자 추가' : '사용자 수정'}
          </h3>
          <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--fg)]"><X size={16} /></button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* 아이디 */}
          <div>
            <label className="text-xs text-[var(--muted)] mb-1 block">아이디</label>
            <input
              value={username} onChange={(e) => setUsername(e.target.value)}
              disabled={mode === 'edit'} required
              placeholder="영문/숫자 3자 이상"
              className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-xl px-3 py-2.5 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500 disabled:opacity-50"
            />
          </div>
          {/* 표시이름 */}
          <div>
            <label className="text-xs text-[var(--muted)] mb-1 block">표시이름</label>
            <input
              value={displayName} onChange={(e) => setDisplayName(e.target.value)}
              placeholder="화면에 표시될 이름"
              className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-xl px-3 py-2.5 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500"
            />
          </div>
          {/* 비밀번호 */}
          <div>
            <label className="text-xs text-[var(--muted)] mb-1 block">
              {mode === 'add' ? '비밀번호 (8자 이상)' : '새 비밀번호 (변경 시에만 입력)'}
            </label>
            <div className="relative">
              <input
                type={showPw ? 'text' : 'password'}
                value={password} onChange={(e) => setPassword(e.target.value)}
                required={mode === 'add'}
                placeholder={mode === 'add' ? '비밀번호 입력' : '변경할 경우에만 입력'}
                className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-xl px-3 py-2.5 pr-9 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500"
              />
              <button type="button" onClick={() => setShowPw(!showPw)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--muted)] hover:text-[var(--fg)]">
                {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>
          {errMsg && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-red-500/10 border border-red-500/25 text-red-400 text-sm">
              <XCircle size={14} /> {errMsg}
            </div>
          )}
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose}
              className="flex-1 py-2.5 rounded-xl text-sm font-semibold border border-[var(--border)] text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)] transition-colors">
              취소
            </button>
            <button type="submit" disabled={loading}
              className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/20 disabled:opacity-40 transition-colors">
              {loading ? '처리 중…' : mode === 'add' ? '추가' : '저장'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── 사용자 관리 테이블 ────────────────────────────────────────────────────────
function UserManagementCard() {
  const token   = useAuthStore((s) => s.token)!
  const me      = useAuthStore((s) => s.user)
  const qc      = useQueryClient()
  const [modal, setModal] = useState<{ mode: 'add' | 'edit'; target?: UserOut } | null>(null)
  const [deletingUser, setDeletingUser] = useState<string | null>(null)

  const { data: users = [], isLoading } = useQuery<UserOut[]>({
    queryKey: ['users'],
    queryFn:  () => apiListUsers(token),
  })

  const toggleMut = useMutation({
    mutationFn: ({ username, is_active }: { username: string; is_active: boolean }) =>
      apiUpdateUser(token, username, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })

  const deleteMut = useMutation({
    mutationFn: (username: string) => apiDeleteUser(token, username),
    onSuccess: () => { setDeletingUser(null); qc.invalidateQueries({ queryKey: ['users'] }) },
  })

  const handleDone = () => { setModal(null); qc.invalidateQueries({ queryKey: ['users'] }) }

  const formatDate = (iso: string | null) => {
    if (!iso) return '—'
    return new Date(iso).toLocaleString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  }

  return (
    <>
      {modal && (
        <UserModal mode={modal.mode} target={modal.target} onClose={() => setModal(null)} onDone={handleDone} />
      )}
      {deletingUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-sm bg-[var(--surface)] border border-[var(--border)] rounded-2xl shadow-2xl p-6">
            <h3 className="text-base font-bold text-[var(--fg)] mb-2">사용자 삭제</h3>
            <p className="text-sm text-[var(--muted)] mb-5">
              <code className="text-red-400">{deletingUser}</code> 계정을 삭제합니다. 이 작업은 되돌릴 수 없습니다.
            </p>
            <div className="flex gap-2">
              <button onClick={() => setDeletingUser(null)}
                className="flex-1 py-2.5 rounded-xl text-sm font-semibold border border-[var(--border)] text-[var(--muted)] hover:bg-[var(--border)] transition-colors">
                취소
              </button>
              <button onClick={() => deleteMut.mutate(deletingUser)} disabled={deleteMut.isPending}
                className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20 disabled:opacity-40 transition-colors">
                {deleteMut.isPending ? '삭제 중…' : '삭제'}
              </button>
            </div>
          </div>
        </div>
      )}

      <Card>
        <CardHeader className="flex items-center justify-between">
          <div>
            <CardTitle>사용자 관리</CardTitle>
            <div className="text-xs text-[var(--muted)] mt-0.5">로그인 계정 추가 · 수정 · 삭제</div>
          </div>
          <button
            onClick={() => setModal({ mode: 'add' })}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/20 transition-colors text-sm font-semibold"
          >
            <UserPlus size={14} /> 사용자 추가
          </button>
        </CardHeader>
        <CardBody className="pt-2 px-0 pb-0">
          {isLoading ? (
            <div className="p-5 space-y-2">
              {[1, 2].map((i) => <div key={i} className="h-10 skeleton rounded-lg" />)}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] text-[var(--muted)] bg-[var(--bg)]/40">
                    <th className="text-left py-2.5 pl-5 pr-3 text-xs font-semibold uppercase tracking-wider">아이디</th>
                    <th className="text-left py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">표시이름</th>
                    <th className="text-center py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">상태</th>
                    <th className="text-left py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider hidden md:table-cell">최종 로그인</th>
                    <th className="text-left py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider hidden lg:table-cell">생성일</th>
                    <th className="text-right py-2.5 pr-5 text-xs font-semibold uppercase tracking-wider">관리</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.username} className="border-b border-[var(--border)]/50 hover:bg-[var(--border)]/20 transition-colors">
                      <td className="py-3 pl-5 pr-3">
                        <div className="flex items-center gap-2">
                          <code className="text-sm text-[var(--fg)] font-mono">{u.username}</code>
                          {u.username === me?.username && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-400 border border-cyan-500/25">나</span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 pr-3 text-[var(--fg)]">{u.display_name || '—'}</td>
                      <td className="py-3 pr-3 text-center">
                        <button
                          onClick={() => toggleMut.mutate({ username: u.username, is_active: !u.is_active })}
                          disabled={toggleMut.isPending}
                          title={u.is_active ? '비활성화' : '활성화'}
                          className={clsx(
                            'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border transition-colors',
                            u.is_active
                              ? 'bg-green-500/10 text-green-400 border-green-500/25 hover:bg-green-500/20'
                              : 'bg-[var(--border)] text-[var(--muted)] border-[var(--border)] hover:bg-red-500/10 hover:text-red-400',
                          )}
                        >
                          {u.is_active
                            ? <><ShieldCheck size={11} /> 활성</>
                            : <><ShieldOff size={11} /> 비활성</>
                          }
                        </button>
                      </td>
                      <td className="py-3 pr-3 text-xs text-[var(--muted)] hidden md:table-cell tabular">{formatDate(u.last_login)}</td>
                      <td className="py-3 pr-3 text-xs text-[var(--muted)] hidden lg:table-cell tabular">{formatDate(u.created_at)}</td>
                      <td className="py-3 pr-5 text-right">
                        <div className="flex items-center gap-1.5 justify-end">
                          <button
                            onClick={() => setModal({ mode: 'edit', target: u })}
                            title="수정"
                            className="p-1.5 rounded-lg text-[var(--muted)] hover:text-cyan-400 hover:bg-cyan-500/10 transition-colors"
                          >
                            <Pencil size={13} />
                          </button>
                          <button
                            onClick={() => setModal({ mode: 'edit', target: u })}
                            title="비밀번호 초기화"
                            className="p-1.5 rounded-lg text-[var(--muted)] hover:text-yellow-400 hover:bg-yellow-500/10 transition-colors"
                          >
                            <RotateCcw size={13} />
                          </button>
                          <button
                            onClick={() => u.username !== me?.username && setDeletingUser(u.username)}
                            disabled={u.username === me?.username}
                            title={u.username === me?.username ? '자신의 계정은 삭제 불가' : '삭제'}
                            className="p-1.5 rounded-lg text-[var(--muted)] hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {users.length === 0 && (
                <div className="py-8 text-center text-sm text-[var(--muted)]">사용자가 없습니다.</div>
              )}
            </div>
          )}
        </CardBody>
      </Card>
    </>
  )
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────
export function AccountPage() {
  return (
    <div className="p-6 space-y-5 max-w-5xl">
      <ChangePasswordCard />
      <UserManagementCard />
    </div>
  )
}
