/** @vitest-environment jsdom */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ createUser: vi.fn() }))

vi.mock('@/lib/api', () => ({
  createUser: mocks.createUser,
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

import { CreateUserForm } from '@/components/CreateUserForm'
import { ApiResponseError, AuthSessionUnavailableError } from '@/lib/api'

const body = { fullName: 'Operador Exemplo', email: 'operator@example.test', role: 'OPERATOR' }
const created = {
  ...body,
  userId: '00000000-0000-4000-8000-000000000010',
  status: 'INVITED',
  version: 1,
  createdAt: '2026-09-30T10:00:00.000Z',
  updatedAt: '2026-09-30T10:00:00.000Z',
}

function fill(values = body) {
  fireEvent.change(screen.getByLabelText('Nome completo'), {
    target: { value: values.fullName },
  })
  fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: values.email } })
  fireEvent.change(screen.getByLabelText('Perfil'), { target: { value: values.role } })
}

function submit() {
  fireEvent.submit(screen.getByRole('form', { name: 'Novo usuário' }))
}

function renderForm(overrides: Partial<{
  onCreated: (user: typeof created) => void
  onCancel: () => void
  onReconcileUncertain: (email: string) => Promise<boolean>
}> = {}) {
  const props = {
    onCreated: vi.fn(),
    onCancel: vi.fn(),
    onReconcileUncertain: vi.fn(async () => false),
    ...overrides,
  }
  return { ...render(<CreateUserForm {...props} />), props }
}

describe('CreateUserForm', () => {
  beforeEach(() => { mocks.createUser.mockReset() })
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks() })

  it('cancels without creating an idempotency key or request', () => {
    const cancel = vi.fn()
    const uuid = vi.spyOn(crypto, 'randomUUID')
    renderForm({ onCancel: cancel })
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(cancel).toHaveBeenCalledOnce()
    expect(uuid).not.toHaveBeenCalled()
    expect(mocks.createUser).not.toHaveBeenCalled()
  })

  it.each([
    ['', 'operator@example.test'],
    ['A', 'operator@example.test'],
    ['A'.repeat(151), 'operator@example.test'],
    ['Nome\tInválido', 'operator@example.test'],
    ['Operador Exemplo', ''],
    ['Operador Exemplo', 'invalid'],
    ['Operador Exemplo', 'a@invalid'],
    ['Operador Exemplo', `a${'x'.repeat(245)}@example.test`],
  ])('rejects invalid name/email before creating a key', (fullName, email) => {
    const uuid = vi.spyOn(crypto, 'randomUUID')
    renderForm()
    fill({ ...body, fullName, email })
    submit()
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(uuid).not.toHaveBeenCalled()
    expect(mocks.createUser).not.toHaveBeenCalled()
  })

  it('normalizes the payload and supports both roles', async () => {
    mocks.createUser.mockResolvedValue(created)
    renderForm()
    fill({ fullName: '  Ａna   Silva  ', email: ' ADMIN@EXAMPLE.TEST ', role: 'ADMIN' })
    submit()
    await waitFor(() => expect(mocks.createUser).toHaveBeenCalledWith({
      fullName: 'Ana Silva', email: 'admin@example.test', role: 'ADMIN',
    }, expect.stringMatching(/^[0-9a-f-]{36}$/)))
  })

  it('accepts 150 Unicode code points after normalization', async () => {
    mocks.createUser.mockResolvedValue(created)
    renderForm()
    fill({ ...body, fullName: '😀'.repeat(150) })
    submit()
    await waitFor(() => expect(mocks.createUser).toHaveBeenCalledOnce())
  })

  it('blocks double submit and cancellation while pending', async () => {
    let resolve!: (value: typeof created) => void
    mocks.createUser.mockReturnValue(new Promise((done) => { resolve = done }))
    const cancel = vi.fn()
    renderForm({ onCancel: cancel })
    fill()
    submit()
    submit()
    expect(mocks.createUser).toHaveBeenCalledOnce()
    expect((screen.getByRole('button', { name: 'Cancelar' }) as HTMLButtonElement).disabled)
      .toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(cancel).not.toHaveBeenCalled()
    await act(async () => resolve(created))
  })

  it.each([
    [new TypeError('network secret'), 'Não foi possível confirmar'],
    [new ApiResponseError(500, 'INTERNAL_ERROR'), 'Não foi possível confirmar'],
    [new ApiResponseError(409, 'OPERATION_IN_PROGRESS'), 'está em andamento'],
    [new ApiResponseError(503, 'INVITATION_DELIVERY_FAILED'), 'retomar a mesma operação'],
  ])('retries recoverable failure %o with the same key', async (failure, message) => {
    mocks.createUser.mockRejectedValueOnce(failure).mockResolvedValueOnce(created)
    const { props } = renderForm()
    fill()
    submit()
    expect((await screen.findByRole('alert')).textContent).toContain(message)
    expect(screen.queryByText('network secret')).toBeNull()
    expect((screen.getByLabelText('Nome completo') as HTMLInputElement).disabled).toBe(true)
    expect((screen.getByLabelText('E-mail') as HTMLInputElement).disabled).toBe(true)
    expect((screen.getByLabelText('Perfil') as HTMLSelectElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: 'Cancelar' }) as HTMLButtonElement).disabled)
      .toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(props.onCancel).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    await waitFor(() => expect(mocks.createUser).toHaveBeenCalledTimes(2))
    expect(mocks.createUser.mock.calls[1][0]).toEqual(mocks.createUser.mock.calls[0][0])
    expect(mocks.createUser.mock.calls[1][1]).toBe(mocks.createUser.mock.calls[0][1])
  })

  it('freezes the original payload and key through repeated recoverable retries', async () => {
    const key = '00000000-0000-4000-8000-000000000010'
    const uuid = vi.spyOn(crypto, 'randomUUID').mockReturnValue(key)
    mocks.createUser
      .mockRejectedValueOnce(new ApiResponseError(500, 'INTERNAL_ERROR'))
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockResolvedValueOnce(created)
    renderForm()
    fill()
    submit()
    await screen.findByRole('alert')
    fill({ ...body, fullName: 'Outro Operador' })
    expect((screen.getByLabelText('Nome completo') as HTMLInputElement).value).toBe(body.fullName)
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    await waitFor(() => expect(mocks.createUser).toHaveBeenCalledTimes(3))
    expect(mocks.createUser.mock.calls.map((call) => call[0])).toEqual([body, body, body])
    expect(mocks.createUser.mock.calls.map((call) => call[1])).toEqual([key, key, key])
    expect(uuid).toHaveBeenCalledOnce()
  })

  it('reconciles uncertain delivery without retrying or allowing a new create', async () => {
    mocks.createUser.mockRejectedValueOnce(
      new ApiResponseError(503, 'INVITATION_DELIVERY_UNCERTAIN'),
    )
    const reconcile = vi.fn(async () => true)
    const { props } = renderForm({ onReconcileUncertain: reconcile })
    fill()
    submit()
    expect((await screen.findByRole('alert')).textContent).toContain('pode ter sido concluída')
    submit()
    expect(mocks.createUser).toHaveBeenCalledOnce()
    expect(screen.queryByRole('button', { name: 'Tentar novamente' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Iniciar nova intenção' })).toBeNull()
    expect((screen.getByLabelText('Nome completo') as HTMLInputElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: 'Cancelar' }) as HTMLButtonElement).disabled)
      .toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Reconciliar estado' }))
    await waitFor(() => expect(reconcile).toHaveBeenCalledWith(body.email))
    expect(props.onCancel).not.toHaveBeenCalled()
    expect(mocks.createUser).toHaveBeenCalledOnce()
  })

  it('keeps uncertain creation locked when remote reconciliation fails', async () => {
    mocks.createUser.mockRejectedValueOnce(
      new ApiResponseError(503, 'INVITATION_DELIVERY_UNCERTAIN'),
    )
    const reconcile = vi.fn()
      .mockRejectedValueOnce(new TypeError('network secret'))
      .mockResolvedValueOnce(false)
    renderForm({ onReconcileUncertain: reconcile })
    fill()
    submit()
    await screen.findByRole('alert')

    fireEvent.click(screen.getByRole('button', { name: 'Reconciliar estado' }))
    expect((await screen.findByRole('alert')).textContent).toContain('estado remoto')
    fireEvent.click(screen.getByRole('button', { name: 'Reconciliar estado' }))
    expect((await screen.findByRole('alert')).textContent).toContain('ainda não foi localizado')
    expect((screen.getByRole('button', { name: 'Cancelar' }) as HTMLButtonElement).disabled)
      .toBe(true)
    expect(mocks.createUser).toHaveBeenCalledOnce()
  })

  it.each([
    [new ApiResponseError(400, 'INVALID_REQUEST'), 'Revise os dados'],
    [new AuthSessionUnavailableError(), 'sessão está inválida'],
    [new ApiResponseError(403, 'FORBIDDEN'), 'não está autorizado'],
    [new ApiResponseError(409, 'EMAIL_ALREADY_EXISTS'), 'E-mail já cadastrado'],
    [new ApiResponseError(409, 'IDEMPOTENCY_KEY_REUSED'), 'tentativa é incompatível'],
  ])('maps terminal failure safely: %o', async (failure, message) => {
    mocks.createUser.mockRejectedValueOnce(failure)
    const { props } = renderForm()
    fill()
    submit()
    expect((await screen.findByRole('alert')).textContent).toContain(message)
    expect((screen.getByRole('button', { name: 'Cancelar' }) as HTMLButtonElement).disabled)
      .toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(props.onCancel).toHaveBeenCalledOnce()
  })

  it('uses a new key for a new submission after a terminal result', async () => {
    vi.spyOn(crypto, 'randomUUID')
      .mockReturnValueOnce('00000000-0000-4000-8000-000000000020')
      .mockReturnValueOnce('00000000-0000-4000-8000-000000000021')
    mocks.createUser
      .mockRejectedValueOnce(new ApiResponseError(409, 'EMAIL_ALREADY_EXISTS'))
      .mockResolvedValueOnce(created)
    renderForm()
    fill()
    submit()
    await screen.findByRole('alert')
    submit()

    await waitFor(() => expect(mocks.createUser).toHaveBeenCalledTimes(2))
    expect(mocks.createUser.mock.calls.map((call) => call[1])).toEqual([
      '00000000-0000-4000-8000-000000000020',
      '00000000-0000-4000-8000-000000000021',
    ])
  })

  it('finishes the attempt after a successful invitation', async () => {
    mocks.createUser.mockResolvedValue(created)
    const onCreated = vi.fn()
    renderForm({ onCreated })
    fill()
    submit()
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created))
  })

  it('ignores a late response after unmount', async () => {
    let resolve!: (value: typeof created) => void
    mocks.createUser.mockReturnValue(new Promise((done) => { resolve = done }))
    const onCreated = vi.fn()
    const view = renderForm({ onCreated })
    fill()
    submit()
    view.unmount()
    await act(async () => resolve(created))
    expect(onCreated).not.toHaveBeenCalled()
  })
})
