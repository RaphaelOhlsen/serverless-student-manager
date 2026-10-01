import { type FormEvent, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  ApiResponseError,
  AuthSessionUnavailableError,
  changeUserRole,
  type AdminUser,
} from '@/lib/api'

type Props = {
  user: AdminUser
  onCompleted: (message: string) => void
  onInvalidated: (message: string) => void
  onCancel: () => void
}

function roleChangeErrorMessage(error: unknown): string {
  if (error instanceof AuthSessionUnavailableError ||
      (error instanceof ApiResponseError && error.status === 401)) {
    return 'Sua sessão expirou. Entre novamente.'
  }
  if (error instanceof ApiResponseError) {
    if (error.status === 400) return 'A solicitação de alteração de role é inválida.'
    if (error.status === 403) return 'Você não tem permissão para alterar a role deste usuário.'
    if (error.status === 404 && error.code === 'USER_NOT_FOUND') {
      return 'O usuário não foi encontrado. Os dados serão atualizados.'
    }
    if (error.status === 409) {
      switch (error.code) {
        case 'USER_VERSION_CONFLICT':
          return 'O usuário foi alterado por outra operação. Os dados serão atualizados.'
        case 'LAST_ACTIVE_ADMIN_CONFLICT':
          return 'A role não pode ser alterada porque o sistema precisa manter ao menos um administrador ativo.'
        case 'IDEMPOTENCY_KEY_REUSED':
          return 'Esta tentativa é incompatível com a solicitação anterior. Inicie uma nova ação.'
        case 'OPERATION_IN_PROGRESS':
          return 'A alteração está em andamento. Aguarde e tente novamente.'
      }
    }
  }
  return 'Não foi possível confirmar a alteração. Tente novamente com a mesma solicitação.'
}

function requiresRefresh(error: unknown): boolean {
  return error instanceof ApiResponseError &&
    ((error.status === 404 && error.code === 'USER_NOT_FOUND') ||
      (error.status === 409 && error.code === 'USER_VERSION_CONFLICT'))
}

function endsAttempt(error: unknown): boolean {
  return error instanceof AuthSessionUnavailableError ||
    (error instanceof ApiResponseError && error.status >= 400 && error.status < 500 &&
      !(error.status === 409 && error.code === 'OPERATION_IN_PROGRESS'))
}

export function RoleChangeDialog({ user, onCompleted, onInvalidated, onCancel }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const attempt = useRef<{ snapshot: string; key: string } | null>(null)
  const inFlight = useRef(false)
  const current = useRef(false)
  const cancel = useRef(onCancel)
  const confirmButton = useRef<HTMLButtonElement>(null)
  const targetRole: AdminUser['role'] = user.role === 'ADMIN' ? 'OPERATOR' : 'ADMIN'

  useEffect(() => {
    cancel.current = onCancel
  }, [onCancel])

  useEffect(() => {
    current.current = true
    confirmButton.current?.focus()
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape' && !inFlight.current) cancel.current()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      current.current = false
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (inFlight.current) return
    const body = { expectedVersion: user.version, role: targetRole }
    const snapshot = JSON.stringify({ userId: user.userId, ...body })
    if (attempt.current?.snapshot !== snapshot) {
      attempt.current = { snapshot, key: crypto.randomUUID() }
    }
    inFlight.current = true
    setLoading(true)
    setError(null)
    try {
      await changeUserRole(user.userId, body, attempt.current.key)
      if (!current.current) return
      attempt.current = null
      onCompleted(`Role de ${user.fullName} alterada para ${targetRole}.`)
    } catch (failure) {
      if (!current.current) return
      const message = roleChangeErrorMessage(failure)
      if (endsAttempt(failure)) attempt.current = null
      if (requiresRefresh(failure)) onInvalidated(message)
      else setError(message)
    } finally {
      inFlight.current = false
      if (current.current) setLoading(false)
    }
  }

  return (
    <div className="dialog-backdrop">
      <section
        className="lifecycle-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="role-change-dialog-title"
      >
        <form className="auth-form" aria-label="Alterar role" onSubmit={submit} noValidate>
          <h2 id="role-change-dialog-title">Alterar role</h2>
          <p className="auth-description">
            Confirme a alteração de {user.fullName} de {user.role} para {targetRole}.
          </p>
          <dl className="student-readonly-fields">
            <div><dt>Role atual</dt><dd>{user.role}</dd></div>
            <div><dt>Nova role</dt><dd>{targetRole}</dd></div>
          </dl>
          {error ? <p className="auth-error" role="alert">{error}</p> : null}
          {loading ? <p className="auth-notice" role="status">Alterando role…</p> : null}
          <div className="dialog-actions">
            <Button ref={confirmButton} type="submit" disabled={loading}>
              {loading ? 'Alterando…' : 'Confirmar alteração'}
            </Button>
            <Button type="button" variant="outline" disabled={loading} onClick={onCancel}>
              Cancelar
            </Button>
          </div>
        </form>
      </section>
    </div>
  )
}
