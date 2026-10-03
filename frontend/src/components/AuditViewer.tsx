import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  ApiResponseError,
  AuthSessionUnavailableError,
  fetchAuditEvents,
  type AuditEvent,
  type AuditQuery,
} from '@/lib/api'

type DraftFilters = {
  from: string
  to: string
  resourceType: '' | 'STUDENT' | 'USER'
  resourceId: string
  eventType: string
  actorId: string
  result: '' | 'SUCCESS' | 'FAILURE'
  correlationId: string
  limit: string
}

type Attempt = { query: AuditQuery; append: boolean }
type ViewerError = { message: string; action: 'retry' | 'reapply' | null }

const INITIAL_FILTERS: DraftFilters = {
  from: '',
  to: '',
  resourceType: '',
  resourceId: '',
  eventType: '',
  actorId: '',
  result: '',
  correlationId: '',
  limit: '50',
}

function validExactFilter(value: string): boolean {
  return value.length > 0 && value === value.trim() &&
    new TextEncoder().encode(value).length <= 512 && !/\p{C}/u.test(value)
}

function toAuditQuery(filters: DraftFilters): AuditQuery {
  if (!filters.from || !filters.to) throw new TypeError('Missing audit date range')
  const fromDate = new Date(filters.from)
  const toDate = new Date(filters.to)
  if (!Number.isFinite(fromDate.getTime()) || !Number.isFinite(toDate.getTime())) {
    throw new TypeError('Invalid audit date range')
  }
  const from = fromDate.toISOString()
  const to = toDate.toISOString()
  if (fromDate > toDate || toDate.getTime() - fromDate.getTime() > 366 * 24 * 60 * 60 * 1000) {
    throw new TypeError('Invalid audit date range')
  }
  const limit = Number(filters.limit)
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new TypeError('Invalid audit limit')
  }
  if (filters.resourceId && !filters.resourceType) {
    throw new TypeError('Audit resource ID requires resource type')
  }
  for (const value of [
    filters.resourceId, filters.eventType, filters.actorId, filters.correlationId,
  ]) {
    if (value && !validExactFilter(value)) throw new TypeError('Invalid exact audit filter')
  }
  return {
    from,
    to,
    ...(filters.resourceType ? { resourceType: filters.resourceType } : {}),
    ...(filters.resourceId ? { resourceId: filters.resourceId } : {}),
    ...(filters.eventType ? { eventType: filters.eventType } : {}),
    ...(filters.actorId ? { actorId: filters.actorId } : {}),
    ...(filters.result ? { result: filters.result } : {}),
    ...(filters.correlationId ? { correlationId: filters.correlationId } : {}),
    limit,
  }
}

function auditError(error: unknown): ViewerError {
  if (error instanceof AuthSessionUnavailableError ||
      (error instanceof ApiResponseError && error.status === 401)) {
    return { message: 'Sua sessão expirou. Entre novamente.', action: null }
  }
  if (error instanceof ApiResponseError) {
    if (error.status === 400 && error.code === 'INVALID_CURSOR') {
      return {
        message: 'A paginação expirou ou não corresponde mais aos filtros aplicados.',
        action: 'reapply',
      }
    }
    if (error.status === 400) {
      return { message: 'A consulta é inválida. Revise os filtros informados.', action: null }
    }
    if (error.status === 403) {
      return { message: 'Você não tem permissão para consultar a auditoria.', action: null }
    }
    if (error.status >= 500) {
      return { message: 'Não foi possível carregar a auditoria. Tente novamente.', action: 'retry' }
    }
  }
  return { message: 'Não foi possível carregar a auditoria. Tente novamente.', action: 'retry' }
}

function formatOccurredAt(value: string): string {
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'medium',
  }).format(new Date(value))
}

export function AuditViewer() {
  const [draft, setDraft] = useState<DraftFilters>(INITIAL_FILTERS)
  const [appliedQuery, setAppliedQuery] = useState<AuditQuery | null>(null)
  const [items, setItems] = useState<AuditEvent[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<ViewerError | null>(null)
  const requestGeneration = useRef(0)
  const mounted = useRef(true)
  const appendInFlight = useRef(false)
  const lastAttempt = useRef<Attempt | null>(null)

  useEffect(() => {
    const generationRef = requestGeneration
    mounted.current = true
    return () => {
      mounted.current = false
      ++generationRef.current
    }
  }, [])

  const load = useCallback(async (query: AuditQuery, append: boolean) => {
    const generation = ++requestGeneration.current
    lastAttempt.current = { query, append }
    if (append) appendInFlight.current = true
    setIsLoading(true)
    setError(null)
    try {
      const page = await fetchAuditEvents(query)
      if (!mounted.current || generation !== requestGeneration.current) return
      setItems((current) => append ? [...current, ...page.items] : page.items)
      setNextCursor(page.nextCursor)
    } catch (failure) {
      if (!mounted.current || generation !== requestGeneration.current) return
      setError(auditError(failure))
    } finally {
      if (append) appendInFlight.current = false
      if (mounted.current && generation === requestGeneration.current) setIsLoading(false)
    }
  }, [])

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    let query: AuditQuery
    try {
      query = toAuditQuery(draft)
    } catch {
      ++requestGeneration.current
      appendInFlight.current = false
      setItems([])
      setNextCursor(null)
      setAppliedQuery(null)
      setIsLoading(false)
      setError({
        message: 'Revise o período, os filtros e o limite informados.',
        action: null,
      })
      return
    }
    appendInFlight.current = false
    setAppliedQuery(query)
    setItems([])
    setNextCursor(null)
    void load(query, false)
  }

  function loadMore() {
    if (!appliedQuery || !nextCursor || isLoading || appendInFlight.current) return
    void load({ ...appliedQuery, cursor: nextCursor }, true)
  }

  function retry() {
    const attempt = lastAttempt.current
    if (!attempt || isLoading) return
    void load(attempt.query, attempt.append)
  }

  function reapplyFilters() {
    if (!appliedQuery || isLoading) return
    setItems([])
    setNextCursor(null)
    void load(appliedQuery, false)
  }

  return (
    <section className="audit-viewer" aria-labelledby="audit-viewer-title">
      <div>
        <h2 id="audit-viewer-title">Auditoria</h2>
        <p className="field-guidance">Consulte eventos administrativos por período e filtros exatos.</p>
      </div>

      <form className="audit-filters" onSubmit={applyFilters}>
        <label>Início
          <input type="datetime-local" value={draft.from}
            onChange={(event) => setDraft({ ...draft, from: event.target.value })} />
        </label>
        <label>Fim
          <input type="datetime-local" value={draft.to}
            onChange={(event) => setDraft({ ...draft, to: event.target.value })} />
        </label>
        <label>Tipo de recurso
          <select value={draft.resourceType} onChange={(event) => setDraft({
            ...draft,
            resourceType: event.target.value as DraftFilters['resourceType'],
            ...(event.target.value ? {} : { resourceId: '' }),
          })}>
            <option value="">Todos</option>
            <option value="STUDENT">Aluno</option>
            <option value="USER">Usuário</option>
          </select>
        </label>
        <label>ID do recurso
          <input value={draft.resourceId} disabled={!draft.resourceType}
            onChange={(event) => setDraft({ ...draft, resourceId: event.target.value })} />
        </label>
        <label>Tipo do evento
          <input value={draft.eventType}
            onChange={(event) => setDraft({ ...draft, eventType: event.target.value })} />
        </label>
        <label>ID do ator
          <input value={draft.actorId}
            onChange={(event) => setDraft({ ...draft, actorId: event.target.value })} />
        </label>
        <label>Resultado
          <select value={draft.result} onChange={(event) => setDraft({
            ...draft, result: event.target.value as DraftFilters['result'],
          })}>
            <option value="">Todos</option>
            <option value="SUCCESS">Sucesso</option>
            <option value="FAILURE">Falha</option>
          </select>
        </label>
        <label>ID de correlação
          <input value={draft.correlationId}
            onChange={(event) => setDraft({ ...draft, correlationId: event.target.value })} />
        </label>
        <label>Itens por página
          <input type="number" min="1" max="100" value={draft.limit}
            onChange={(event) => setDraft({ ...draft, limit: event.target.value })} />
        </label>
        <Button type="submit">Aplicar filtros</Button>
      </form>

      {isLoading && items.length === 0 ? (
        <p className="auth-notice" role="status">Carregando auditoria…</p>
      ) : null}
      {error ? (
        <div className="students-feedback">
          <p className="auth-error" role="alert">{error.message}</p>
          {error.action === 'retry' ? (
            <Button type="button" disabled={isLoading} onClick={retry}>Tentar novamente</Button>
          ) : null}
          {error.action === 'reapply' ? (
            <Button type="button" disabled={isLoading} onClick={reapplyFilters}>Reaplicar filtros</Button>
          ) : null}
        </div>
      ) : null}
      {appliedQuery && !isLoading && !error && items.length === 0 ? (
        <p className="students-empty">Nenhum evento encontrado.</p>
      ) : null}
      {items.length > 0 ? (
        <ul className="audit-events">
          {items.map((item) => (
            <li className="audit-event-card" key={item.eventId}>
              <div className="audit-event-heading">
                <strong>{item.eventType}</strong>
                <span className="user-badge">{item.result}</span>
              </div>
              <dl>
                <div><dt>Data</dt><dd><time dateTime={item.occurredAt}>{formatOccurredAt(item.occurredAt)}</time></dd></div>
                <div><dt>Recurso</dt><dd>{item.resourceType} · {item.resourceId}</dd></div>
                <div><dt>Ator</dt><dd>{item.actorId}</dd></div>
                <div><dt>Correlação</dt><dd>{item.correlationId}</dd></div>
                <div><dt>Evento</dt><dd>{item.eventId}</dd></div>
              </dl>
            </li>
          ))}
        </ul>
      ) : null}
      {nextCursor && !error ? (
        <Button type="button" variant="outline" disabled={isLoading} onClick={loadMore}>
          {isLoading ? 'Carregando…' : 'Carregar mais'}
        </Button>
      ) : null}
    </section>
  )
}
