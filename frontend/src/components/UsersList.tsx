import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  ApiResponseError,
  AuthSessionUnavailableError,
  fetchUsers,
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

export function UsersList() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchMode, setSearchMode] = useState<SearchMode>('name')
  const [searchValue, setSearchValue] = useState('')
  const [role, setRole] = useState<UserRoleFilter>('ALL')
  const [status, setStatus] = useState<UserStatusFilter>('ALL')
  const [appliedQuery, setAppliedQuery] = useState<UsersQuery>(DEFAULT_QUERY)
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

  return (
    <section className="users-directory" aria-label="Diretório de usuários">
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
            </li>
          ))}
        </ul>
      ) : null}
      {nextCursor && !error ? (
        <Button type="button" variant="outline" disabled={isLoading} onClick={loadNextPage}>
          {isLoading ? 'Carregando…' : 'Carregar mais'}
        </Button>
      ) : null}
    </section>
  )
}
