/**
 * @vitest-environment jsdom
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ changeUserRole: vi.fn() }))

vi.mock('@/lib/api', () => ({
  changeUserRole: apiMocks.changeUserRole,
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

import { RoleChangeDialog } from '@/components/RoleChangeDialog'
import { ApiResponseError, type AdminUser } from '@/lib/api'

const admin: AdminUser = {
  userId: '00000000-0000-4000-8000-000000000001',
  fullName: 'Admin Exemplo',
  email: 'admin@example.test',
  role: 'ADMIN' as const,
  status: 'ACTIVE' as const,
  version: 3,
  createdAt: '2026-09-01T10:00:00.000Z',
  updatedAt: '2026-09-02T10:00:00.000Z',
}
const operator: AdminUser = { ...admin, role: 'OPERATOR' }

function renderDialog(user = admin, overrides: Partial<{
  onCompleted: (message: string) => void
  onInvalidated: (message: string) => void
  onCancel: () => void
}> = {}) {
  const props = {
    onCompleted: vi.fn(),
    onInvalidated: vi.fn(),
    onCancel: vi.fn(),
    ...overrides,
  }
  return { ...render(<RoleChangeDialog user={user} {...props} />), props }
}

describe('RoleChangeDialog', () => {
  beforeEach(() => {
    apiMocks.changeUserRole.mockReset()
    apiMocks.changeUserRole.mockResolvedValue({ ...admin, role: 'OPERATOR', version: 4 })
  })
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks() })

  it.each([
    [admin, 'ADMIN', 'OPERATOR'],
    [operator, 'OPERATOR', 'ADMIN'],
  ] as const)('offers the only alternative role for %s', async (user, current, target) => {
    renderDialog(user)
    expect(screen.getByText(`Confirme a alteração de ${user.fullName} de ${current} para ${target}.`))
      .toBeTruthy()
    expect(screen.getByText('Role atual').nextSibling?.textContent).toBe(current)
    expect(screen.getByText('Nova role').nextSibling?.textContent).toBe(target)
  })

  it('creates the UUID only on confirmation and sends detail.version exactly once', async () => {
    const uuid = vi.spyOn(crypto, 'randomUUID').mockReturnValue(
      '00000000-0000-4000-8000-000000000010',
    )
    const { props } = renderDialog()
    expect(uuid).not.toHaveBeenCalled()

    fireEvent.submit(screen.getByRole('form', { name: 'Alterar role' }))

    await waitFor(() => expect(props.onCompleted).toHaveBeenCalledOnce())
    expect(uuid).toHaveBeenCalledOnce()
    expect(apiMocks.changeUserRole).toHaveBeenCalledWith(
      admin.userId,
      { expectedVersion: admin.version, role: 'OPERATOR' },
      '00000000-0000-4000-8000-000000000010',
    )
  })

  it('blocks double submit, cancel and Escape while the request is pending', async () => {
    let resolve!: (value: typeof admin) => void
    apiMocks.changeUserRole.mockReturnValueOnce(new Promise((done) => { resolve = done }))
    const { props } = renderDialog()
    const confirm = screen.getByRole('button', { name: 'Confirmar alteração' })

    fireEvent.click(confirm)
    fireEvent.click(confirm)
    fireEvent.keyDown(document, { key: 'Escape' })

    expect(apiMocks.changeUserRole).toHaveBeenCalledOnce()
    expect((screen.getByRole('button', { name: 'Alterando…' }) as HTMLButtonElement).disabled)
      .toBe(true)
    expect((screen.getByRole('button', { name: 'Cancelar' }) as HTMLButtonElement).disabled)
      .toBe(true)
    expect(props.onCancel).not.toHaveBeenCalled()
    await act(async () => resolve({ ...admin, role: 'OPERATOR' }))
  })

  it.each([
    new TypeError('network secret'),
    new ApiResponseError(500, 'INTERNAL_ERROR'),
    new ApiResponseError(409, 'OPERATION_IN_PROGRESS'),
  ])('retries recoverable failure %o with the same key', async (failure) => {
    apiMocks.changeUserRole.mockRejectedValueOnce(failure).mockResolvedValueOnce({
      ...admin, role: 'OPERATOR', version: 4,
    })
    const { props } = renderDialog()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar alteração' }))
    await screen.findByRole('alert')
    const cancel = screen.getByRole('button', { name: 'Cancelar' }) as HTMLButtonElement
    expect(cancel.disabled).toBe(true)
    fireEvent.click(cancel)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(props.onCancel).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))

    await waitFor(() => expect(apiMocks.changeUserRole).toHaveBeenCalledTimes(2))
    expect(apiMocks.changeUserRole.mock.calls[1][2])
      .toBe(apiMocks.changeUserRole.mock.calls[0][2])
    expect(screen.queryByText('network secret')).toBeNull()
    expect(screen.queryByText('INTERNAL_ERROR')).toBeNull()
  })

  it('keeps the same key through repeated recoverable retries', async () => {
    const key = '00000000-0000-4000-8000-000000000010'
    const uuid = vi.spyOn(crypto, 'randomUUID').mockReturnValue(key)
    apiMocks.changeUserRole
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockRejectedValueOnce(new ApiResponseError(500, 'INTERNAL_ERROR'))
      .mockResolvedValueOnce({ ...admin, role: 'OPERATOR', version: 4 })
    renderDialog()

    fireEvent.click(screen.getByRole('button', { name: 'Confirmar alteração' }))
    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))

    await waitFor(() => expect(apiMocks.changeUserRole).toHaveBeenCalledTimes(3))
    expect(apiMocks.changeUserRole.mock.calls.map((call) => call[2])).toEqual([key, key, key])
    expect(uuid).toHaveBeenCalledOnce()
  })

  it('freezes the original role-change snapshot across a prop change', async () => {
    apiMocks.changeUserRole
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockResolvedValueOnce({ ...admin, role: 'OPERATOR', version: 4 })
    const view = renderDialog()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar alteração' }))
    await screen.findByRole('alert')
    const originalCall = apiMocks.changeUserRole.mock.calls[0]

    view.rerender(<RoleChangeDialog
      user={{ ...admin, role: 'OPERATOR', version: admin.version + 1 }}
      {...view.props}
    />)
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))

    await waitFor(() => expect(apiMocks.changeUserRole).toHaveBeenCalledTimes(2))
    expect(apiMocks.changeUserRole.mock.calls[1]).toEqual(originalCall)
  })

  it('allows Cancel and Escape before confirmation and after a terminal failure', async () => {
    const preSubmit = renderDialog()
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(preSubmit.props.onCancel).toHaveBeenCalledTimes(2)
    preSubmit.unmount()

    apiMocks.changeUserRole.mockRejectedValueOnce(
      new ApiResponseError(409, 'LAST_ACTIVE_ADMIN_CONFLICT'),
    )
    const terminal = renderDialog()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar alteração' }))
    await screen.findByRole('alert')
    const cancel = screen.getByRole('button', { name: 'Cancelar' }) as HTMLButtonElement
    expect(cancel.disabled).toBe(false)
    fireEvent.click(cancel)
    expect(terminal.props.onCancel).toHaveBeenCalledOnce()
  })

  it.each([
    [409, 'USER_VERSION_CONFLICT', 'alterado por outra operação'],
    [404, 'USER_NOT_FOUND', 'não foi encontrado'],
  ] as const)('invalidates stale detail for %s %s', async (status, code, message) => {
    apiMocks.changeUserRole.mockRejectedValueOnce(new ApiResponseError(status, code))
    const { props } = renderDialog()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar alteração' }))

    await waitFor(() => expect(props.onInvalidated).toHaveBeenCalledWith(
      expect.stringContaining(message),
    ))
    expect(props.onCompleted).not.toHaveBeenCalled()
  })

  it('shows last-active-admin feedback, avoids automatic retry and gives a new intent a new key', async () => {
    vi.spyOn(crypto, 'randomUUID')
      .mockReturnValueOnce('00000000-0000-4000-8000-000000000020')
      .mockReturnValueOnce('00000000-0000-4000-8000-000000000021')
    apiMocks.changeUserRole
      .mockRejectedValueOnce(new ApiResponseError(409, 'LAST_ACTIVE_ADMIN_CONFLICT'))
      .mockResolvedValueOnce({ ...admin, role: 'OPERATOR', version: 4 })
    renderDialog()

    fireEvent.click(screen.getByRole('button', { name: 'Confirmar alteração' }))
    expect((await screen.findByRole('alert')).textContent).toContain(
      'manter ao menos um administrador ativo',
    )
    expect(apiMocks.changeUserRole).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar alteração' }))

    await waitFor(() => expect(apiMocks.changeUserRole).toHaveBeenCalledTimes(2))
    expect(apiMocks.changeUserRole.mock.calls[1][2])
      .not.toBe(apiMocks.changeUserRole.mock.calls[0][2])
  })

  it('ends an idempotency-key-reused attempt with sanitized feedback', async () => {
    apiMocks.changeUserRole.mockRejectedValueOnce(
      new ApiResponseError(409, 'IDEMPOTENCY_KEY_REUSED'),
    )
    renderDialog()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar alteração' }))

    expect((await screen.findByRole('alert')).textContent).toContain('Inicie uma nova ação')
  })

  it('treats a valid no-op response as completion', async () => {
    apiMocks.changeUserRole.mockResolvedValueOnce(admin)
    const { props } = renderDialog()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar alteração' }))
    await waitFor(() => expect(props.onCompleted).toHaveBeenCalledOnce())
  })

  it('ignores a response that arrives after unmount', async () => {
    let resolve!: (value: typeof admin) => void
    apiMocks.changeUserRole.mockReturnValueOnce(new Promise((done) => { resolve = done }))
    const onCompleted = vi.fn()
    const view = renderDialog(admin, { onCompleted })
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar alteração' }))
    view.unmount()

    await act(async () => resolve({ ...admin, role: 'OPERATOR' }))
    expect(onCompleted).not.toHaveBeenCalled()
  })
})
