import { type FormEvent, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  ApiResponseError,
  AuthSessionUnavailableError,
  createUser,
  type CreatedAdminUser,
  type CreateUserRequest,
} from '@/lib/api'

const empty: CreateUserRequest = { fullName: '', email: '', role: 'OPERATOR' }
const CONTROL_CHARACTER = /\p{C}/u

function normalize(fields: CreateUserRequest): CreateUserRequest {
  return {
    fullName: fields.fullName.normalize('NFKC').trim().replace(/\s+/gu, ' '),
    email: fields.email.trim().toLowerCase(),
    role: fields.role,
  }
}

function validate(raw: CreateUserRequest, value: CreateUserRequest): string | null {
  const fullNameLength = Array.from(value.fullName).length
  if (CONTROL_CHARACTER.test(raw.fullName) || fullNameLength < 2 || fullNameLength > 150) {
    return 'Informe um nome entre 2 e 150 caracteres, sem caracteres de controle.'
  }
  if (!value.email || Array.from(value.email).length > 254 || /\s/u.test(value.email) ||
      CONTROL_CHARACTER.test(value.email) || value.email.split('@').length !== 2) {
    return 'Informe um e-mail válido com até 254 caracteres.'
  }
  const [local, domain] = value.email.split('@')
  if (!local || !domain || !domain.includes('.') || domain.startsWith('.') ||
      domain.endsWith('.')) {
    return 'Informe um e-mail válido com até 254 caracteres.'
  }
  return null
}

function messageFor(error: unknown): string {
  if (error instanceof AuthSessionUnavailableError ||
      (error instanceof ApiResponseError && error.status === 401)) {
    return 'Sua sessão está inválida ou expirou. Saia e entre novamente.'
  }
  if (error instanceof ApiResponseError) {
    if (error.status === 400) return 'Revise os dados informados.'
    if (error.status === 403) return 'Seu usuário não está autorizado a criar usuários.'
    if (error.status === 409) {
      switch (error.code) {
        case 'EMAIL_ALREADY_EXISTS': return 'E-mail já cadastrado.'
        case 'IDEMPOTENCY_KEY_REUSED':
          return 'Esta tentativa é incompatível com os dados enviados. Revise os dados ou inicie uma nova tentativa.'
        case 'OPERATION_IN_PROGRESS':
          return 'A solicitação está em andamento. Aguarde e tente novamente.'
      }
    }
    if (error.status === 503 && error.code === 'INVITATION_DELIVERY_FAILED') {
      return 'Não foi possível entregar o convite. Tente novamente para retomar a mesma operação.'
    }
    if (error.status === 503 && error.code === 'INVITATION_DELIVERY_UNCERTAIN') {
      return 'A entrega do convite ficou incerta e a operação pode ter sido concluída. Atualize a lista antes de iniciar uma nova intenção.'
    }
  }
  return 'Não foi possível confirmar a criação. Tente novamente com os mesmos dados.'
}

function isUncertain(error: unknown): boolean {
  return error instanceof ApiResponseError && error.status === 503 &&
    error.code === 'INVITATION_DELIVERY_UNCERTAIN'
}

function shouldEndAttempt(error: unknown): boolean {
  return error instanceof AuthSessionUnavailableError ||
    (error instanceof ApiResponseError && error.status >= 400 && error.status < 500 &&
      !(error.status === 409 && error.code === 'OPERATION_IN_PROGRESS'))
}

type Props = {
  onCreated: (user: CreatedAdminUser) => void
  onCancel: () => void
  disabled?: boolean
}

export function CreateUserForm({ onCreated, onCancel, disabled = false }: Props) {
  const [fields, setFields] = useState<CreateUserRequest>(empty)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deliveryUncertain, setDeliveryUncertain] = useState(false)
  const attempt = useRef<{ snapshot: string; key: string } | null>(null)
  const inFlight = useRef(false)
  const current = useRef(false)

  useEffect(() => {
    current.current = true
    return () => { current.current = false }
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (inFlight.current || disabled || deliveryUncertain) return
    const payload = normalize(fields)
    const invalid = validate(fields, payload)
    if (invalid) { setError(invalid); return }
    const snapshot = JSON.stringify(payload)
    if (attempt.current?.snapshot !== snapshot) {
      attempt.current = { snapshot, key: crypto.randomUUID() }
    }
    inFlight.current = true
    setLoading(true)
    setError(null)
    try {
      const user = await createUser(payload, attempt.current.key)
      if (!current.current) return
      attempt.current = null
      onCreated(user)
    } catch (failure) {
      if (!current.current) return
      setError(messageFor(failure))
      if (isUncertain(failure)) setDeliveryUncertain(true)
      else if (shouldEndAttempt(failure)) attempt.current = null
    } finally {
      inFlight.current = false
      if (current.current) setLoading(false)
    }
  }

  function cancel() {
    attempt.current = null
    onCancel()
  }

  function startNewIntent() {
    attempt.current = null
    setDeliveryUncertain(false)
    setError(null)
  }

  return (
    <form className="auth-form" aria-label="Novo usuário" onSubmit={submit} noValidate>
      <h2>Novo usuário</h2>
      <div className="form-field">
        <label htmlFor="create-user-fullName">Nome completo</label>
        <input id="create-user-fullName" value={fields.fullName} required
          disabled={loading || disabled}
          onChange={(event) => setFields((old) => ({ ...old, fullName: event.target.value }))} />
      </div>
      <div className="form-field">
        <label htmlFor="create-user-email">E-mail</label>
        <input id="create-user-email" type="email" inputMode="email" value={fields.email}
          required disabled={loading || disabled}
          onChange={(event) => setFields((old) => ({ ...old, email: event.target.value }))} />
      </div>
      <div className="form-field">
        <label htmlFor="create-user-role">Perfil</label>
        <select id="create-user-role" value={fields.role} disabled={loading || disabled}
          onChange={(event) => setFields((old) => ({
            ...old, role: event.target.value as CreateUserRequest['role'],
          }))}>
          <option value="OPERATOR">OPERATOR</option>
          <option value="ADMIN">ADMIN</option>
        </select>
      </div>
      {error ? <p className="auth-error" role="alert">{error}</p> : null}
      {loading ? <p className="auth-notice" role="status">Criando usuário e enviando convite…</p> : null}
      <Button type="submit" disabled={loading || disabled || deliveryUncertain}>
        Criar e convidar
      </Button>
      {deliveryUncertain ? (
        <Button type="button" variant="outline" disabled={loading || disabled}
          onClick={startNewIntent}>Iniciar nova intenção</Button>
      ) : null}
      <Button type="button" variant="outline" disabled={loading || disabled}
        onClick={cancel}>Cancelar</Button>
    </form>
  )
}
