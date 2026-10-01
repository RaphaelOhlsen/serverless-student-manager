import { useEffect, useRef, useState } from 'react'

import { RoleChangeDialog } from '@/components/RoleChangeDialog'
import { Button } from '@/components/ui/button'
import {
  ApiResponseError,
  AuthSessionUnavailableError,
  fetchUser,
  type AdminUser,
} from '@/lib/api'

type Props = {
  userId: string
  currentUserId: string
  onClose: () => void
  onRoleChanged: (message: string) => void
}

function detailErrorMessage(error: unknown): string {
  if (error instanceof AuthSessionUnavailableError ||
      (error instanceof ApiResponseError && error.status === 401)) {
    return 'Sua sessão expirou. Entre novamente.'
  }
  if (error instanceof ApiResponseError) {
    if (error.status === 403) return 'Você não tem permissão para consultar este usuário.'
    if (error.status === 404) return 'O usuário não foi encontrado.'
  }
  return 'Não foi possível carregar os detalhes do usuário. Tente novamente.'
}

export function UserDetailDialog({ userId, currentUserId, onClose, onRoleChanged }: Props) {
  const [result, setResult] = useState<{
    userId: string
    user: AdminUser | null
    error: string | null
  }>({ userId, user: null, error: null })
  const [refreshGeneration, setRefreshGeneration] = useState(0)
  const [roleChangeUserId, setRoleChangeUserId] = useState<string | null>(null)
  const close = useRef(onClose)
  const closeButton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    close.current = onClose
  }, [onClose])

  useEffect(() => {
    let active = true
    void fetchUser(userId).then((detail) => {
      if (!active) return
      setResult({ userId, user: detail, error: null })
    }).catch((failure: unknown) => {
      if (!active) return
      setResult({ userId, user: null, error: detailErrorMessage(failure) })
    })
    return () => { active = false }
  }, [userId, refreshGeneration])

  useEffect(() => {
    closeButton.current?.focus()
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape' && roleChangeUserId !== userId) close.current()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [roleChangeUserId, userId])

  function reconcileAfterRoleChange(message: string) {
    setRoleChangeUserId(null)
    setResult({ userId, user: null, error: null })
    setRefreshGeneration((generation) => generation + 1)
    onRoleChanged(message)
  }

  const isCurrent = result.userId === userId
  const user = isCurrent ? result.user : null
  const error = isCurrent ? result.error : null
  const loading = !isCurrent || (user === null && error === null)

  return (
    <div className="dialog-backdrop">
      <section
        className="lifecycle-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="user-detail-dialog-title"
      >
        <h2 id="user-detail-dialog-title">Detalhes do usuário</h2>
        {loading ? <p className="auth-notice" role="status">Carregando detalhes…</p> : null}
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        {user ? (
          <>
            <dl className="student-readonly-fields">
              <div><dt>Nome</dt><dd>{user.fullName}</dd></div>
              <div><dt>E-mail</dt><dd>{user.email}</dd></div>
              <div><dt>Role</dt><dd>{user.role}</dd></div>
              <div><dt>Status</dt><dd>{user.status}</dd></div>
              <div><dt>Versão</dt><dd>{user.version}</dd></div>
              <div><dt>Criado em</dt><dd><time dateTime={user.createdAt}>{user.createdAt}</time></dd></div>
              <div><dt>Atualizado em</dt><dd><time dateTime={user.updatedAt}>{user.updatedAt}</time></dd></div>
            </dl>
            {user.userId !== currentUserId ? (
              <Button type="button" onClick={() => {
                setRoleChangeUserId(user.userId)
              }}>Alterar role</Button>
            ) : null}
          </>
        ) : null}
        <div className="dialog-actions">
          <Button ref={closeButton} type="button" variant="outline"
            disabled={roleChangeUserId === userId} onClick={onClose}>
            Fechar
          </Button>
        </div>
        {roleChangeUserId === userId && user ? (
          <RoleChangeDialog
            key={`${user.userId}-${user.version}`}
            user={user}
            onCompleted={reconcileAfterRoleChange}
            onInvalidated={reconcileAfterRoleChange}
            onCancel={() => setRoleChangeUserId(null)}
          />
        ) : null}
      </section>
    </div>
  )
}
