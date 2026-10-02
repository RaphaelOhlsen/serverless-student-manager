import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react'

import { CreateUserForm } from '@/components/CreateUserForm'
import { UserDetailDialog } from '@/components/UserDetailDialog'
import { Button } from '@/components/ui/button'
import {
  ApiResponseError,
  AuthSessionUnavailableError,
  fetchUsers,
  resendUserInvitation,
  type AdminUser,
  type UserRoleFilter,
  type UsersQuery,
  type UserStatusFilter,
} from '@/lib/api'

type SearchMode = 'name' | 'email'

const DEFAULT_QUERY: UsersQuery = { limit: 20, role: 'ALL', status: 'ALL' }

type Attempt = {
  query: UsersQuery
  append: boolean
}

function safeErrorMessage(error: unknown): string {
  if (error instanceof AuthSessionUnavailableError ||
      (error instanceof ApiResponseError && error.status === 401)) {
    return 'Sua sessão expirou. Entre novamente.'
  }
  if (error instanceof ApiResponseError) {
    if (error.status === 400) return 'A busca informada é inválida. Revise os filtros.'
    if (error.status === 403) return 'Você não tem permissão para consultar usuários.'
  }
  return 'Não foi possível carregar os usuários. Tente novamente.'
}

function resendErrorMessage(error: unknown): string {
  if (error instanceof AuthSessionUnavailableError ||
      (error instanceof ApiResponseError && error.status === 401)) {
    return 'Sua sessão expirou. Entre novamente.'
  }
  if (error instanceof ApiResponseError) {
    if (error.status === 400) return 'A solicitação de reenvio é inválida.'
    if (error.status === 403) return 'Você não tem permissão para reenviar convites.'
    if (error.status === 404 && error.code === 'USER_NOT_FOUND') {
      return 'O usuário não foi encontrado. A lista será atualizada.'
    }
    if (error.status === 409) {
      switch (error.code) {
        case 'USER_VERSION_CONFLICT':
          return 'O usuário foi alterado. A lista será atualizada.'
        case 'USER_STATE_CONFLICT':
          return 'O usuário não está mais aguardando convite. A lista será atualizada.'
        case 'IDEMPOTENCY_KEY_REUSED':
          return 'Esta tentativa é incompatível com a solicitação anterior.'
        case 'OPERATION_IN_PROGRESS':
          return 'O reenvio está em andamento. Aguarde e tente novamente.'
      }
    }
    if (error.status === 503 && error.code === 'INVITATION_DELIVERY_FAILED') {
      return 'O convite não foi entregue. Tente novamente para retomar a mesma operação.'
    }
    if (error.status === 503 && error.code === 'INVITATION_DELIVERY_UNCERTAIN') {
      return 'O resultado do reenvio é incerto e o convite pode ter sido enviado. Atualize a lista antes de iniciar uma nova intenção.'
    }
  }
  return 'Não foi possível confirmar o reenvio. Tente novamente com a mesma solicitação.'
}

function isDeliveryUncertain(error: unknown): boolean {
  return error instanceof ApiResponseError && error.status === 503 &&
    error.code === 'INVITATION_DELIVERY_UNCERTAIN'
}

function isUserConflict(error: unknown): boolean {
  return error instanceof ApiResponseError &&
    ((error.status === 404 && error.code === 'USER_NOT_FOUND') ||
      (error.status === 409 &&
        (error.code === 'USER_VERSION_CONFLICT' || error.code === 'USER_STATE_CONFLICT')))
}

type ResendInvitationControlProps = {
  user: AdminUser
  disabled: boolean
  onSuccess: () => void
  onConflict: (message: string) => void
  onRefresh: () => void
}

function ResendInvitationControl({
  user,
  disabled,
  onSuccess,
  onConflict,
  onRefresh,
}: ResendInvitationControlProps) {
  const [confirming, setConfirming] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deliveryUncertain, setDeliveryUncertain] = useState(false)
  const idempotencyKey = useRef<string | null>(null)
  const inFlight = useRef(false)
  const current = useRef(false)

  useEffect(() => {
    current.current = true
    return () => { current.current = false }
  }, [])

  async function confirm() {
    if (inFlight.current || disabled || deliveryUncertain) return
    idempotencyKey.current ??= crypto.randomUUID()
    inFlight.current = true
    setLoading(true)
    setError(null)
    try {
      await resendUserInvitation(
        user.userId,
        { expectedVersion: user.version },
        idempotencyKey.current,
      )
      if (!current.current) return
      idempotencyKey.current = null
      setConfirming(false)
      onSuccess()
    } catch (failure) {
      if (!current.current) return
      const message = resendErrorMessage(failure)
      setError(message)
      if (isDeliveryUncertain(failure)) {
        setDeliveryUncertain(true)
      } else if (isUserConflict(failure)) {
        idempotencyKey.current = null
        setConfirming(false)
        onConflict(message)
      }
    } finally {
      inFlight.current = false
      if (current.current) setLoading(false)
    }
  }

  function cancel() {
    if (loading || disabled) return
    idempotencyKey.current = null
    setError(null)
    setConfirming(false)
  }

  function startNewIntent() {
    idempotencyKey.current = null
    setDeliveryUncertain(false)
    setError(null)
  }

  if (!confirming) {
    return (
      <Button type="button" variant="outline" disabled={disabled}
        onClick={() => { setError(null); setConfirming(true) }}>
        Reenviar convite
      </Button>
    )
  }

  return (
    <div className="students-feedback" aria-label={`Reenviar convite para ${user.fullName}`}>
      <p>Confirmar reenvio do convite para {user.fullName}?</p>
      {error ? <p className="auth-error" role="alert">{error}</p> : null}
      {loading ? <p className="auth-notice" role="status">Reenviando convite…</p> : null}
      <Button type="button" disabled={loading || disabled || deliveryUncertain}
        onClick={() => { void confirm() }}>
        {error && !deliveryUncertain ? 'Tentar novamente' : 'Confirmar reenvio'}
      </Button>
      {deliveryUncertain ? (
        <>
          <Button type="button" variant="outline" disabled={loading || disabled}
            onClick={onRefresh}>Atualizar lista</Button>
          <Button type="button" variant="outline" disabled={loading || disabled}
            onClick={startNewIntent}>Iniciar nova intenção</Button>
        </>
      ) : null}
      <Button type="button" variant="outline" disabled={loading || disabled}
        onClick={cancel}>Cancelar</Button>
    </div>
  )
}

type UsersListProps = {
  currentUserId: string
}

export function UsersList({ currentUserId }: UsersListProps) {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchMode, setSearchMode] = useState<SearchMode>('name')
  const [searchValue, setSearchValue] = useState('')
  const [role, setRole] = useState<UserRoleFilter>('ALL')
  const [status, setStatus] = useState<UserStatusFilter>('ALL')
  const [appliedQuery, setAppliedQuery] = useState<UsersQuery>(DEFAULT_QUERY)
  const [showCreate, setShowCreate] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const [creationMessage, setCreationMessage] = useState<string | null>(null)
  const requestGeneration = useRef(0)
  const lastAttempt = useRef<Attempt>({ query: DEFAULT_QUERY, append: false })

  const load = useCallback(async (query: UsersQuery, append: boolean) => {
    const generation = ++requestGeneration.current
    lastAttempt.current = { query, append }
    setIsLoading(true)
    setError(null)
    try {
      const page = await fetchUsers(query)
      if (generation !== requestGeneration.current) return
      setUsers((current) => append ? [...current, ...page.items] : page.items)
      setNextCursor(page.nextCursor)
    } catch (failure) {
      if (generation !== requestGeneration.current) return
      setError(safeErrorMessage(failure))
      if (!append) {
        setUsers([])
        setNextCursor(null)
      }
    } finally {
      if (generation === requestGeneration.current) setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    const generationRef = requestGeneration
    async function loadInitialPage() {
      await load(DEFAULT_QUERY, false)
    }
    void loadInitialPage()
    return () => { ++generationRef.current }
  }, [load])

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const term = searchValue.trim()
    const query: UsersQuery = {
      limit: 20,
      role,
      status,
      ...(term && searchMode === 'name' ? { namePrefix: term } : {}),
      ...(term && searchMode === 'email' ? { email: term } : {}),
    }
    setAppliedQuery(query)
    setCreationMessage(null)
    setUsers([])
    setNextCursor(null)
    void load(query, false)
  }

  function loadNextPage() {
    if (!nextCursor || isLoading) return
    void load({ ...appliedQuery, cursor: nextCursor }, true)
  }

  function retry() {
    void load(lastAttempt.current.query, lastAttempt.current.append)
  }

  function userCreated() {
    setShowCreate(false)
    setCreationMessage('Usuário criado e convite solicitado com sucesso.')
    setNextCursor(null)
    void load(appliedQuery, false)
  }

  function refreshAfterResend(message: string) {
    setCreationMessage(message)
    setNextCursor(null)
    void load(appliedQuery, false)
  }

  function refreshAfterRoleChange(message: string) {
    setCreationMessage(message)
    setNextCursor(null)
    void load(appliedQuery, false)
  }

  function refreshAfterLifecycle(message: string) {
    setCreationMessage(message)
    setNextCursor(null)
    void load(appliedQuery, false)
  }

  return (
    <section className="users-directory" aria-label="Diretório de usuários">
      {showCreate ? (
        <CreateUserForm onCancel={() => setShowCreate(false)} onCreated={userCreated} />
      ) : (
        <Button type="button" onClick={() => {
          setCreationMessage(null)
          setShowCreate(true)
        }}>Novo usuário</Button>
      )}
      {creationMessage ? <p className="auth-notice" role="status">{creationMessage}</p> : null}
      <form className="users-filters" aria-label="Filtros de usuários" onSubmit={applyFilters}>
        <div className="form-field">
          <label htmlFor="user-search-mode">Buscar por</label>
          <select id="user-search-mode" value={searchMode}
            onChange={(event) => {
              setSearchMode(event.target.value as SearchMode)
              setSearchValue('')
            }}>
            <option value="name">Nome</option>
            <option value="email">E-mail</option>
          </select>
        </div>
        <div className="form-field users-search-field">
          <label htmlFor="user-search">{searchMode === 'name' ? 'Nome' : 'E-mail'}</label>
          <input id="user-search" type={searchMode === 'email' ? 'email' : 'search'}
            value={searchValue}
            onChange={(event) => setSearchValue(event.target.value)} />
        </div>
        <div className="form-field">
          <label htmlFor="user-role-filter">Role</label>
          <select id="user-role-filter" value={role}
            onChange={(event) => setRole(event.target.value as UserRoleFilter)}>
            <option value="ALL">Todas</option>
            <option value="ADMIN">ADMIN</option>
            <option value="OPERATOR">OPERATOR</option>
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="user-status-filter">Status</label>
          <select id="user-status-filter" value={status}
            onChange={(event) => setStatus(event.target.value as UserStatusFilter)}>
            <option value="ALL">Todos</option>
            <option value="INVITED">INVITED</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="INACTIVE">INACTIVE</option>
          </select>
        </div>
        <Button type="submit">Aplicar filtros</Button>
      </form>

      {isLoading && users.length === 0 ? (
        <p className="auth-notice" role="status">Carregando usuários…</p>
      ) : null}
      {error ? (
        <div className="students-feedback">
          <p className="auth-error" role="alert">{error}</p>
          <Button type="button" onClick={retry}>Tentar novamente</Button>
        </div>
      ) : null}
      {!isLoading && !error && users.length === 0 ? (
        <p className="students-empty">Nenhum usuário encontrado.</p>
      ) : null}
      {users.length > 0 ? (
        <ul className="users-list">
          {users.map((user) => (
            <li className="user-card" key={user.userId}>
              <div>
                <h2>{user.fullName}</h2>
                <p>{user.email}</p>
              </div>
              <div className="user-card-metadata">
                <span className="user-badge">{user.role}</span>
                <span className="user-badge">{user.status}</span>
              </div>
              <Button type="button" variant="outline"
                onClick={() => setSelectedUserId(user.userId)}>
                Ver detalhes
              </Button>
              {user.status === 'INVITED' ? (
                <ResendInvitationControl
                  user={user}
                  disabled={isLoading}
                  onSuccess={() => refreshAfterResend('Convite reenviado com sucesso.')}
                  onConflict={(message) => refreshAfterResend(message)}
                  onRefresh={() => refreshAfterResend(
                    'Lista atualizada. O resultado do reenvio anterior permanece incerto.',
                  )}
                />
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {nextCursor && !error ? (
        <Button type="button" variant="outline" disabled={isLoading} onClick={loadNextPage}>
          {isLoading ? 'Carregando…' : 'Carregar mais'}
        </Button>
      ) : null}
      {selectedUserId ? (
        <UserDetailDialog
          userId={selectedUserId}
          currentUserId={currentUserId}
          onClose={() => setSelectedUserId(null)}
          onRoleChanged={refreshAfterRoleChange}
          onLifecycleChanged={refreshAfterLifecycle}
        />
      ) : null}
    </section>
  )
}
