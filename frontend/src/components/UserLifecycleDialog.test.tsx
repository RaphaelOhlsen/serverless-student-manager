/**
 * @vitest-environment jsdom
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ deactivateUser: vi.fn(), reactivateUser: vi.fn() }))

vi.mock('@/lib/api', () => ({
  deactivateUser: apiMocks.deactivateUser,
  reactivateUser: apiMocks.reactivateUser,
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

import {
  UserLifecycleDialog,
  type UserLifecycleAction,
} from '@/components/UserLifecycleDialog'
import { ApiResponseError } from '@/lib/api'

const user = {
  userId: '00000000-0000-4000-8000-000000000002',
  fullName: 'Operador Exemplo',
  email: 'operator@example.test',
  role: 'OPERATOR',
  status: 'ACTIVE',
  version: 3,
  createdAt: '2026-09-01T10:00:00.000Z',
  updatedAt: '2026-09-02T10:00:00.000Z',
} as const

function renderDialog(action: UserLifecycleAction, overrides: {
  onCompleted?: (message: string) => void
  onInvalidated?: (message: string) => void
  onCancel?: () => void
} = {}) {
  return render(<UserLifecycleDialog
    action={action}
    user={action === 'deactivate' ? user : { ...user, status: 'INACTIVE' }}
    onCompleted={overrides.onCompleted ?? vi.fn()}
    onInvalidated={overrides.onInvalidated ?? vi.fn()}
    onCancel={overrides.onCancel ?? vi.fn()}
  />)
}

function confirm(action: UserLifecycleAction) {
  fireEvent.click(screen.getByRole('button', {
    name: action === 'deactivate' ? 'Confirmar desativação' : 'Confirmar reativação',
  }))
}

describe('UserLifecycleDialog', () => {
  beforeEach(() => {
    apiMocks.deactivateUser.mockReset().mockResolvedValue({ ...user, status: 'INACTIVE' })
    apiMocks.reactivateUser.mockReset().mockResolvedValue({ ...user, status: 'ACTIVE' })
  })
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks() })

  it.each([
    ['deactivate', 'Desativar usuário', apiMocks.deactivateUser],
    ['reactivate', 'Reativar usuário', apiMocks.reactivateUser],
  ] as const)('submits %s from detail.version and completes', async (action, title, request) => {
    const onCompleted = vi.fn()
    renderDialog(action, { onCompleted })
    expect(screen.getByRole('dialog', { name: title })).toBeTruthy()

    confirm(action)

    await waitFor(() => expect(request).toHaveBeenCalledOnce())
    expect(request).toHaveBeenCalledWith(
      user.userId,
      { expectedVersion: user.version },
      expect.stringMatching(/^[0-9a-f-]{36}$/),
    )
    expect(onCompleted).toHaveBeenCalledWith(expect.stringContaining('com sucesso'))
    expect(action === 'deactivate' ? apiMocks.reactivateUser : apiMocks.deactivateUser)
      .not.toHaveBeenCalled()
  })

  it('creates the UUID only on confirmation and blocks duplicate submit, cancel and Escape', async () => {
    let resolve!: (value: object) => void
    apiMocks.deactivateUser.mockReturnValueOnce(new Promise((done) => { resolve = done }))
    const uuid = vi.spyOn(crypto, 'randomUUID')
    const onCancel = vi.fn()
    renderDialog('deactivate', { onCancel })
    expect(uuid).not.toHaveBeenCalled()

    confirm('deactivate')
    fireEvent.submit(screen.getByRole('form', { name: 'Desativar usuário' }))

    expect(apiMocks.deactivateUser).toHaveBeenCalledOnce()
    expect(uuid).toHaveBeenCalledOnce()
    expect((screen.getByRole('button', { name: 'Atualizando…' }) as HTMLButtonElement).disabled)
      .toBe(true)
    expect((screen.getByRole('button', { name: 'Cancelar' }) as HTMLButtonElement).disabled)
      .toBe(true)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onCancel).not.toHaveBeenCalled()
    await act(async () => resolve({ ...user, status: 'INACTIVE' }))
  })

  it('allows Cancel and Escape before the first confirmation', () => {
    const onCancel = vi.fn()
    renderDialog('deactivate', { onCancel })

    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    fireEvent.keyDown(document, { key: 'Escape' })

    expect(onCancel).toHaveBeenCalledTimes(2)
    expect(apiMocks.deactivateUser).not.toHaveBeenCalled()
  })

  it.each([
    ['USER_VERSION_CONFLICT', 'alterado por outra operação'],
    ['USER_STATE_CONFLICT', 'status do usuário mudou'],
    ['USER_NOT_FOUND', 'não foi encontrado'],
  ])('invalidates fresh data for deterministic conflict %s', async (code, message) => {
    const status = code === 'USER_NOT_FOUND' ? 404 : 409
    apiMocks.deactivateUser.mockRejectedValueOnce(new ApiResponseError(status, code))
    const onInvalidated = vi.fn()
    renderDialog('deactivate', { onInvalidated })
    confirm('deactivate')

    await waitFor(() => expect(onInvalidated).toHaveBeenCalledWith(
      expect.stringContaining(message),
    ))
    expect(screen.queryByText(code)).toBeNull()
  })

  it.each([
    [new ApiResponseError(409, 'LAST_ACTIVE_ADMIN_CONFLICT'), 'ao menos um administrador'],
    [new ApiResponseError(409, 'IDEMPOTENCY_KEY_REUSED'), 'incompatível'],
    [new ApiResponseError(403, 'FORBIDDEN'), 'não tem permissão'],
  ])('ends deterministic failure %o with sanitized local feedback', async (failure, message) => {
    apiMocks.deactivateUser.mockRejectedValueOnce(failure)
    const onInvalidated = vi.fn()
    renderDialog('deactivate', { onInvalidated })
    confirm('deactivate')

    expect((await screen.findByRole('alert')).textContent).toContain(message)
    expect(onInvalidated).not.toHaveBeenCalled()
    expect(screen.queryByText(failure.code ?? '')).toBeNull()
  })

  it.each([
    ['deactivate', new ApiResponseError(409, 'OPERATION_IN_PROGRESS')],
    ['deactivate', new ApiResponseError(500, 'INTERNAL_ERROR')],
    ['deactivate', new TypeError('network secret')],
    ['deactivate', new ApiResponseError(503, 'USER_DEACTIVATION_RECONCILIATION_REQUIRED')],
    ['reactivate', new ApiResponseError(503, 'USER_REACTIVATION_RECONCILIATION_REQUIRED')],
  ] as const)('retries recoverable %s failure %o with the same key', async (action, failure) => {
    const request = action === 'deactivate' ? apiMocks.deactivateUser : apiMocks.reactivateUser
    request.mockRejectedValueOnce(failure).mockResolvedValueOnce({
      ...user,
      status: action === 'deactivate' ? 'INACTIVE' : 'ACTIVE',
    })
    const onCompleted = vi.fn()
    const onInvalidated = vi.fn()
    const onCancel = vi.fn()
    renderDialog(action, { onCompleted, onInvalidated, onCancel })
    confirm(action)
    await screen.findByRole('alert')
    expect(onInvalidated).not.toHaveBeenCalled()
    expect(screen.queryByText('network secret')).toBeNull()
    expect((screen.getByRole('button', { name: 'Cancelar' }) as HTMLButtonElement).disabled)
      .toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.click(screen.getByRole('dialog').parentElement as HTMLElement)
    expect(onCancel).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))

    await waitFor(() => expect(request).toHaveBeenCalledTimes(2))
    expect(request.mock.calls[1][2]).toBe(request.mock.calls[0][2])
    expect(onCompleted).toHaveBeenCalledOnce()
    const cancel = screen.getByRole('button', { name: 'Cancelar' }) as HTMLButtonElement
    expect(cancel.disabled).toBe(false)
    fireEvent.click(cancel)
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('keeps the same key through repeated recoverable retries', async () => {
    const key = '00000000-0000-4000-8000-000000000010'
    const uuid = vi.spyOn(crypto, 'randomUUID').mockReturnValue(key)
    apiMocks.deactivateUser
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockRejectedValueOnce(new ApiResponseError(500, 'INTERNAL_ERROR'))
      .mockResolvedValueOnce({ ...user, status: 'INACTIVE' })
    renderDialog('deactivate')

    confirm('deactivate')
    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    await waitFor(() => expect(apiMocks.deactivateUser).toHaveBeenCalledTimes(2))
    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))

    await waitFor(() => expect(apiMocks.deactivateUser).toHaveBeenCalledTimes(3))
    expect(apiMocks.deactivateUser.mock.calls.map((call) => call[2]))
      .toEqual([key, key, key])
    expect(uuid).toHaveBeenCalledOnce()
  })

  it('restores normal dismissal after a deterministic terminal result', async () => {
    apiMocks.deactivateUser.mockRejectedValueOnce(
      new ApiResponseError(409, 'LAST_ACTIVE_ADMIN_CONFLICT'),
    )
    const onCancel = vi.fn()
    renderDialog('deactivate', { onCancel })
    confirm('deactivate')
    await screen.findByRole('alert')

    const cancel = screen.getByRole('button', { name: 'Cancelar' }) as HTMLButtonElement
    expect(cancel.disabled).toBe(false)
    fireEvent.click(cancel)
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('uses a new key for a new explicit dialog intent', async () => {
    const firstKey = '00000000-0000-4000-8000-000000000010'
    const secondKey = '00000000-0000-4000-8000-000000000011'
    vi.spyOn(crypto, 'randomUUID').mockReturnValueOnce(firstKey).mockReturnValueOnce(secondKey)
    apiMocks.deactivateUser
      .mockRejectedValueOnce(new ApiResponseError(409, 'LAST_ACTIVE_ADMIN_CONFLICT'))
      .mockResolvedValueOnce({ ...user, status: 'INACTIVE' })

    const first = renderDialog('deactivate')
    confirm('deactivate')
    await screen.findByRole('alert')
    first.unmount()
    renderDialog('deactivate')
    confirm('deactivate')

    await waitFor(() => expect(apiMocks.deactivateUser).toHaveBeenCalledTimes(2))
    expect(apiMocks.deactivateUser.mock.calls.map((call) => call[2]))
      .toEqual([firstKey, secondKey])
  })

  it('ignores a response that arrives after unmount', async () => {
    let resolve!: (value: object) => void
    apiMocks.reactivateUser.mockReturnValueOnce(new Promise((done) => { resolve = done }))
    const onCompleted = vi.fn()
    const view = renderDialog('reactivate', { onCompleted })
    confirm('reactivate')
    view.unmount()

    await act(async () => resolve({ ...user, status: 'ACTIVE' }))
    expect(onCompleted).not.toHaveBeenCalled()
  })
})
