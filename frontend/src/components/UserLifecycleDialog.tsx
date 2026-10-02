import { type FormEvent, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  ApiResponseError,
  AuthSessionUnavailableError,
  deactivateUser,
  reactivateUser,
  type AdminUser,
} from '@/lib/api'

export type UserLifecycleAction = 'deactivate' | 'reactivate'

type Props = {
  action: UserLifecycleAction
  user: AdminUser
  onCompleted: (message: string) => void
  onInvalidated: (message: string) => void
  onCancel: () => void
}

function lifecycleErrorMessage(error: unknown, action: UserLifecycleAction): string {
  const operation = action === 'deactivate' ? 'desativação' : 'reativação'
  if (error instanceof AuthSessionUnavailableError ||
      (error instanceof ApiResponseError && error.status === 401)) {
    return 'Sua sessão expirou. Entre novamente.'
  }
  if (error instanceof ApiResponseError) {
    if (error.status === 400) return `A solicitação de ${operation} é inválida.`
    if (error.status === 403) return `Você não tem permissão para concluir a ${operation}.`
    if (error.status === 404 && error.code === 'USER_NOT_FOUND') {
      return 'O usuário não foi encontrado. Os dados serão atualizados.'
    }
    if (error.status === 409) {
      switch (error.code) {
        case 'USER_VERSION_CONFLICT':
          return 'O usuário foi alterado por outra operação. Os dados serão atualizados.'
        case 'USER_STATE_CONFLICT':
          return 'O status do usuário mudou. Os dados serão atualizados.'
        case 'LAST_ACTIVE_ADMIN_CONFLICT':
          return 'O usuário não pode ser desativado porque o sistema precisa manter ao menos um administrador ativo.'
        case 'IDEMPOTENCY_KEY_REUSED':
          return 'Esta tentativa é incompatível com a solicitação anterior. Inicie uma nova ação.'
        case 'OPERATION_IN_PROGRESS':
          return `A ${operation} está em andamento. Aguarde e tente novamente.`
      }
    }
    if (error.status === 503 &&
        (error.code === 'USER_DEACTIVATION_RECONCILIATION_REQUIRED' ||
          error.code === 'USER_REACTIVATION_RECONCILIATION_REQUIRED')) {
      return `O resultado da ${operation} ainda precisa ser reconciliado. Tente novamente para retomar a mesma operação.`
    }
  }
  return `Não foi possível confirmar a ${operation}. Tente novamente com a mesma solicitação.`
}

function requiresRefresh(error: unknown): boolean {
  return error instanceof ApiResponseError &&
    ((error.status === 404 && error.code === 'USER_NOT_FOUND') ||
      (error.status === 409 &&
        (error.code === 'USER_VERSION_CONFLICT' || error.code === 'USER_STATE_CONFLICT')))
}

function endsAttempt(error: unknown): boolean {
  return error instanceof AuthSessionUnavailableError ||
    (error instanceof ApiResponseError && error.status >= 400 && error.status < 500 &&
      !(error.status === 409 && error.code === 'OPERATION_IN_PROGRESS'))
}

export function UserLifecycleDialog({
  action,
  user,
  onCompleted,
  onInvalidated,
  onCancel,
}: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasPendingRecoverableIntent, setHasPendingRecoverableIntent] = useState(false)
  const attempt = useRef<{ snapshot: string; key: string } | null>(null)
  const inFlight = useRef(false)
  const current = useRef(false)
  const cancel = useRef(onCancel)
  const confirmButton = useRef<HTMLButtonElement>(null)
  const isDeactivate = action === 'deactivate'

  useEffect(() => {
    cancel.current = onCancel
  }, [onCancel])

  useEffect(() => {
    current.current = true
    confirmButton.current?.focus()
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape' && !inFlight.current && !hasPendingRecoverableIntent) {
        cancel.current()
      }
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      current.current = false
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [hasPendingRecoverableIntent])

  function requestCancel() {
    if (inFlight.current || hasPendingRecoverableIntent) return
    cancel.current()
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (inFlight.current) return
    const body = { expectedVersion: user.version }
    const snapshot = JSON.stringify({ action, userId: user.userId, ...body })
    if (attempt.current?.snapshot !== snapshot) {
      attempt.current = { snapshot, key: crypto.randomUUID() }
    }
    inFlight.current = true
    setLoading(true)
    setError(null)
    try {
      if (isDeactivate) {
        await deactivateUser(user.userId, body, attempt.current.key)
      } else {
        await reactivateUser(user.userId, body, attempt.current.key)
      }
      if (!current.current) return
      attempt.current = null
      setHasPendingRecoverableIntent(false)
      onCompleted(`${user.fullName} ${isDeactivate ? 'desativado' : 'reativado'} com sucesso.`)
    } catch (failure) {
      if (!current.current) return
      const message = lifecycleErrorMessage(failure, action)
      if (endsAttempt(failure)) {
        attempt.current = null
        setHasPendingRecoverableIntent(false)
      } else {
        setHasPendingRecoverableIntent(true)
      }
      if (requiresRefresh(failure)) onInvalidated(message)
      else setError(message)
    } finally {
      inFlight.current = false
      if (current.current) setLoading(false)
    }
  }

  const title = isDeactivate ? 'Desativar usuário' : 'Reativar usuário'
  const confirmation = isDeactivate ? 'Confirmar desativação' : 'Confirmar reativação'

  return (
    <div className="dialog-backdrop">
      <section
        className="lifecycle-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="user-lifecycle-dialog-title"
      >
        <form className="auth-form" aria-label={title} onSubmit={submit} noValidate>
          <h2 id="user-lifecycle-dialog-title">{title}</h2>
          <p className="auth-description">
            Confirme a {isDeactivate ? 'desativação' : 'reativação'} de {user.fullName}.
          </p>
          {error ? <p className="auth-error" role="alert">{error}</p> : null}
          {loading ? <p className="auth-notice" role="status">Atualizando status…</p> : null}
          <div className="dialog-actions">
            <Button ref={confirmButton} type="submit"
              variant={isDeactivate ? 'destructive' : 'default'} disabled={loading}>
              {loading ? 'Atualizando…' : hasPendingRecoverableIntent
                ? 'Tentar novamente'
                : confirmation}
            </Button>
            <Button type="button" variant="outline"
              disabled={loading || hasPendingRecoverableIntent} onClick={requestCancel}>
              Cancelar
            </Button>
          </div>
        </form>
      </section>
    </div>
  )
}
