/**
 * @vitest-environment jsdom
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ fetchAuditEvents: vi.fn() }))

vi.mock('@/lib/api', () => ({
  fetchAuditEvents: apiMocks.fetchAuditEvents,
  ApiResponseError: class ApiResponseError extends Error {
    status: number
    code?: string
    constructor(status: number, code?: string) {
      super(`API request failed with status ${status}`)
      this.status = status
      this.code = code
    }
  },
  AuthSessionUnavailableError: class AuthSessionUnavailableError extends Error {},
}))

import { AuditViewer } from '@/components/AuditViewer'
import { ApiResponseError } from '@/lib/api'

const eventOne = {
  eventId: 'event-1',
  eventType: 'STUDENT_UPDATED',
  resourceType: 'STUDENT' as const,
  resourceId: 'student-1',
  actorId: 'admin-1',
  occurredAt: '2026-09-01T12:00:00.000Z',
  result: 'SUCCESS' as const,
  correlationId: 'correlation-1',
}
const eventTwo = {
  ...eventOne,
  eventId: 'event-2',
  eventType: 'USER_ROLE_CHANGED',
  resourceType: 'USER' as const,
  resourceId: 'user-2',
  result: 'FAILURE' as const,
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function fillRequiredDates(
  from = '2026-09-01T09:00',
  to = '2026-09-02T09:00',
) {
  fireEvent.change(screen.getByLabelText('Início'), { target: { value: from } })
  fireEvent.change(screen.getByLabelText('Fim'), { target: { value: to } })
}

function applyFilters() {
  fireEvent.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
}

describe('AuditViewer', () => {
  beforeEach(() => {
    apiMocks.fetchAuditEvents.mockReset()
    apiMocks.fetchAuditEvents.mockResolvedValue({ items: [], nextCursor: null })
  })
  afterEach(() => { cleanup(); vi.clearAllMocks() })

  it('does not request events before filters are applied', () => {
    render(<AuditViewer />)
    expect(apiMocks.fetchAuditEvents).not.toHaveBeenCalled()
    expect(screen.queryByText('Nenhum evento encontrado.')).toBeNull()
  })

  it('converts local dates to UTC and sends the complete first-page query', async () => {
    apiMocks.fetchAuditEvents.mockResolvedValue({ items: [eventOne], nextCursor: null })
    render(<AuditViewer />)
    fillRequiredDates()
    fireEvent.change(screen.getByLabelText('Tipo de recurso'), { target: { value: 'STUDENT' } })
    fireEvent.change(screen.getByLabelText('ID do recurso'), { target: { value: 'student/1' } })
    fireEvent.change(screen.getByLabelText('Tipo do evento'), { target: { value: 'Student Updated' } })
    fireEvent.change(screen.getByLabelText('ID do ator'), { target: { value: 'admin-1' } })
    fireEvent.change(screen.getByLabelText('Resultado'), { target: { value: 'SUCCESS' } })
    fireEvent.change(screen.getByLabelText('ID de correlação'), { target: { value: 'correlation-1' } })
    fireEvent.change(screen.getByLabelText('Itens por página'), { target: { value: '25' } })
    applyFilters()

    await waitFor(() => expect(apiMocks.fetchAuditEvents).toHaveBeenCalledWith({
      from: new Date('2026-09-01T09:00').toISOString(),
      to: new Date('2026-09-02T09:00').toISOString(),
      resourceType: 'STUDENT',
      resourceId: 'student/1',
      eventType: 'Student Updated',
      actorId: 'admin-1',
      result: 'SUCCESS',
      correlationId: 'correlation-1',
      limit: 25,
    }))
    expect(await screen.findByText('STUDENT_UPDATED')).toBeTruthy()
    expect(screen.getByText(/student-1/)).toBeTruthy()
    expect(screen.getByText('admin-1')).toBeTruthy()
    expect(screen.getByText('correlation-1')).toBeTruthy()
    expect(screen.getByText('event-1')).toBeTruthy()
    expect(screen.getByRole('time').getAttribute('datetime')).toBe(eventOne.occurredAt)
  })

  it('shows loading followed by the empty state', async () => {
    const request = deferred<{ items: []; nextCursor: null }>()
    apiMocks.fetchAuditEvents.mockReturnValue(request.promise)
    render(<AuditViewer />)
    fillRequiredDates()
    applyFilters()
    expect(screen.getByRole('status').textContent).toContain('Carregando auditoria')
    await act(async () => request.resolve({ items: [], nextCursor: null }))
    expect(screen.getByText('Nenhum evento encontrado.')).toBeTruthy()
  })

  it('loads more with the exact applied filters and opaque cursor, then appends in order', async () => {
    const cursor = 'opaque+/=.payload-_'
    apiMocks.fetchAuditEvents
      .mockResolvedValueOnce({ items: [eventOne], nextCursor: cursor })
      .mockResolvedValueOnce({ items: [eventTwo], nextCursor: null })
    render(<AuditViewer />)
    fillRequiredDates()
    applyFilters()
    await screen.findByText('event-1')
    expect(screen.queryByText(cursor)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Carregar mais' }))

    await screen.findByText('event-2')
    const firstQuery = apiMocks.fetchAuditEvents.mock.calls[0]?.[0]
    expect(apiMocks.fetchAuditEvents.mock.calls[1]?.[0]).toEqual({ ...firstQuery, cursor })
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      expect.stringContaining('event-1'),
      expect.stringContaining('event-2'),
    ])
    expect(screen.queryByText(cursor)).toBeNull()
  })

  it('applying changed filters clears items and never reuses the old cursor', async () => {
    const second = deferred<{ items: (typeof eventTwo)[]; nextCursor: null }>()
    apiMocks.fetchAuditEvents
      .mockResolvedValueOnce({ items: [eventOne], nextCursor: 'old-opaque-cursor' })
      .mockReturnValueOnce(second.promise)
    render(<AuditViewer />)
    fillRequiredDates()
    applyFilters()
    await screen.findByText('event-1')
    fireEvent.change(screen.getByLabelText('ID do ator'), { target: { value: 'admin-2' } })
    applyFilters()

    expect(screen.queryByText('event-1')).toBeNull()
    expect(apiMocks.fetchAuditEvents.mock.calls[1]?.[0]).toMatchObject({ actorId: 'admin-2' })
    expect(apiMocks.fetchAuditEvents.mock.calls[1]?.[0]).not.toHaveProperty('cursor')
    await act(async () => second.resolve({ items: [eventTwo], nextCursor: null }))
    expect(screen.getByText('event-2')).toBeTruthy()
  })

  it('ignores an older response after a new filter generation succeeds', async () => {
    const oldRequest = deferred<{ items: (typeof eventOne)[]; nextCursor: null }>()
    const newRequest = deferred<{ items: (typeof eventTwo)[]; nextCursor: null }>()
    apiMocks.fetchAuditEvents
      .mockReturnValueOnce(oldRequest.promise)
      .mockReturnValueOnce(newRequest.promise)
    render(<AuditViewer />)
    fillRequiredDates()
    applyFilters()
    fireEvent.change(screen.getByLabelText('ID do ator'), { target: { value: 'admin-2' } })
    applyFilters()
    await act(async () => newRequest.resolve({ items: [eventTwo], nextCursor: null }))
    expect(screen.getByText('event-2')).toBeTruthy()
    await act(async () => oldRequest.resolve({ items: [eventOne], nextCursor: null }))
    expect(screen.queryByText('event-1')).toBeNull()
    expect(screen.getByText('event-2')).toBeTruthy()
  })

  it('ignores a response after unmount', async () => {
    const request = deferred<{ items: (typeof eventOne)[]; nextCursor: null }>()
    apiMocks.fetchAuditEvents.mockReturnValue(request.promise)
    const view = render(<AuditViewer />)
    fillRequiredDates()
    applyFilters()
    view.unmount()
    await act(async () => request.resolve({ items: [eventOne], nextCursor: null }))
    expect(apiMocks.fetchAuditEvents).toHaveBeenCalledTimes(1)
  })

  it('recovers INVALID_CURSOR only by reapplying filters without a cursor', async () => {
    const cursor = 'opaque-invalid-cursor'
    apiMocks.fetchAuditEvents
      .mockResolvedValueOnce({ items: [eventOne], nextCursor: cursor })
      .mockRejectedValueOnce(new ApiResponseError(400, 'INVALID_CURSOR'))
      .mockResolvedValueOnce({ items: [eventOne], nextCursor: null })
    render(<AuditViewer />)
    fillRequiredDates()
    applyFilters()
    await screen.findByText('event-1')
    fireEvent.click(screen.getByRole('button', { name: 'Carregar mais' }))
    expect((await screen.findByRole('alert')).textContent).toContain('paginação expirou')
    expect(screen.queryByRole('button', { name: 'Tentar novamente' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Reaplicar filtros' }))
    await waitFor(() => expect(apiMocks.fetchAuditEvents).toHaveBeenCalledTimes(3))
    expect(apiMocks.fetchAuditEvents.mock.calls[2]?.[0]).not.toHaveProperty('cursor')
  })

  it.each([
    new TypeError('network secret'),
    new ApiResponseError(500, 'INTERNAL_ERROR'),
  ])('retries recoverable failure %o with the exact last attempt', async (failure) => {
    apiMocks.fetchAuditEvents
      .mockRejectedValueOnce(failure)
      .mockResolvedValueOnce({ items: [eventOne], nextCursor: null })
    render(<AuditViewer />)
    fillRequiredDates()
    applyFilters()
    expect((await screen.findByRole('alert')).textContent).not.toContain('network secret')
    const originalQuery = apiMocks.fetchAuditEvents.mock.calls[0]?.[0]
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    await screen.findByText('event-1')
    expect(apiMocks.fetchAuditEvents.mock.calls[1]?.[0]).toEqual(originalQuery)
  })

  it.each([
    [new ApiResponseError(400, 'INVALID_REQUEST'), 'consulta é inválida'],
    [new ApiResponseError(401), 'sessão expirou'],
    [new ApiResponseError(403, 'FORBIDDEN'), 'não tem permissão'],
  ] as const)('shows a sanitized terminal error for %o', async (failure, message) => {
    apiMocks.fetchAuditEvents.mockRejectedValue(failure)
    render(<AuditViewer />)
    fillRequiredDates()
    applyFilters()
    expect((await screen.findByRole('alert')).textContent).toContain(message)
    expect(screen.queryByText('API request failed')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Tentar novamente' })).toBeNull()
  })

  it('validates date range and resource dependency without a request', () => {
    render(<AuditViewer />)
    fillRequiredDates('2026-09-02T09:00', '2026-09-01T09:00')
    applyFilters()
    expect(apiMocks.fetchAuditEvents).not.toHaveBeenCalled()
    expect(screen.getByRole('alert').textContent).toContain('Revise o período')
  })
})
