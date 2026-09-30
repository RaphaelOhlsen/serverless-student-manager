/** @vitest-environment jsdom */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ createUser: vi.fn() }))

vi.mock('@/lib/api', async (original) => ({
  ...await original<typeof import('@/lib/api')>(),
  createUser: mocks.createUser,
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

describe('CreateUserForm', () => {
  beforeEach(() => { mocks.createUser.mockReset() })
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks() })

  it('cancels without creating an idempotency key or request', () => {
    const cancel = vi.fn()
    const uuid = vi.spyOn(crypto, 'randomUUID')
    render(<CreateUserForm onCreated={vi.fn()} onCancel={cancel} />)
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
    render(<CreateUserForm onCreated={vi.fn()} onCancel={vi.fn()} />)
    fill({ ...body, fullName, email })
    submit()
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(uuid).not.toHaveBeenCalled()
    expect(mocks.createUser).not.toHaveBeenCalled()
  })

  it('normalizes the payload and supports both roles', async () => {
    mocks.createUser.mockResolvedValue(created)
    render(<CreateUserForm onCreated={vi.fn()} onCancel={vi.fn()} />)
    fill({ fullName: '  Ａna   Silva  ', email: ' ADMIN@EXAMPLE.TEST ', role: 'ADMIN' })
    submit()
    await waitFor(() => expect(mocks.createUser).toHaveBeenCalledWith({
      fullName: 'Ana Silva', email: 'admin@example.test', role: 'ADMIN',
    }, expect.stringMatching(/^[0-9a-f-]{36}$/)))
  })

  it('accepts 150 Unicode code points after normalization', async () => {
    mocks.createUser.mockResolvedValue(created)
    render(<CreateUserForm onCreated={vi.fn()} onCancel={vi.fn()} />)
    fill({ ...body, fullName: '😀'.repeat(150) })
    submit()
    await waitFor(() => expect(mocks.createUser).toHaveBeenCalledOnce())
  })

  it('blocks double submit and cancellation while pending', async () => {
    let resolve!: (value: typeof created) => void
    mocks.createUser.mockReturnValue(new Promise((done) => { resolve = done }))
    const cancel = vi.fn()
    render(<CreateUserForm onCreated={vi.fn()} onCancel={cancel} />)
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
    render(<CreateUserForm onCreated={vi.fn()} onCancel={vi.fn()} />)
    fill()
    submit()
    expect((await screen.findByRole('alert')).textContent).toContain(message)
    expect(screen.queryByText('network secret')).toBeNull()
    submit()
    await waitFor(() => expect(mocks.createUser).toHaveBeenCalledTimes(2))
    expect(mocks.createUser.mock.calls[1][1]).toBe(mocks.createUser.mock.calls[0][1])
  })

  it('uses a new key after a semantic payload change', async () => {
    mocks.createUser.mockRejectedValue(new ApiResponseError(500, 'INTERNAL_ERROR'))
    render(<CreateUserForm onCreated={vi.fn()} onCancel={vi.fn()} />)
    fill()
    submit()
    await screen.findByRole('alert')
    fill({ ...body, fullName: 'Outro Operador' })
    submit()
    await waitFor(() => expect(mocks.createUser).toHaveBeenCalledTimes(2))
    expect(mocks.createUser.mock.calls[1][1]).not.toBe(mocks.createUser.mock.calls[0][1])
  })

  it('does not retry uncertain delivery or silently replace its key', async () => {
    mocks.createUser
      .mockRejectedValueOnce(new ApiResponseError(503, 'INVITATION_DELIVERY_UNCERTAIN'))
      .mockResolvedValueOnce(created)
    render(<CreateUserForm onCreated={vi.fn()} onCancel={vi.fn()} />)
    fill()
    submit()
    expect((await screen.findByRole('alert')).textContent).toContain('pode ter sido concluída')
    submit()
    expect(mocks.createUser).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Iniciar nova intenção' }))
    submit()
    await waitFor(() => expect(mocks.createUser).toHaveBeenCalledTimes(2))
    expect(mocks.createUser.mock.calls[1][1]).not.toBe(mocks.createUser.mock.calls[0][1])
  })

  it.each([
    [new ApiResponseError(400, 'INVALID_REQUEST'), 'Revise os dados'],
    [new AuthSessionUnavailableError(), 'sessão está inválida'],
    [new ApiResponseError(403, 'FORBIDDEN'), 'não está autorizado'],
    [new ApiResponseError(409, 'EMAIL_ALREADY_EXISTS'), 'E-mail já cadastrado'],
    [new ApiResponseError(409, 'IDEMPOTENCY_KEY_REUSED'), 'tentativa é incompatível'],
  ])('maps terminal failure safely: %o', async (failure, message) => {
    mocks.createUser.mockRejectedValueOnce(failure)
    render(<CreateUserForm onCreated={vi.fn()} onCancel={vi.fn()} />)
    fill()
    submit()
    expect((await screen.findByRole('alert')).textContent).toContain(message)
  })

  it('finishes the attempt after a successful invitation', async () => {
    mocks.createUser.mockResolvedValue(created)
    const onCreated = vi.fn()
    render(<CreateUserForm onCreated={onCreated} onCancel={vi.fn()} />)
    fill()
    submit()
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created))
  })

  it('ignores a late response after unmount', async () => {
    let resolve!: (value: typeof created) => void
    mocks.createUser.mockReturnValue(new Promise((done) => { resolve = done }))
    const onCreated = vi.fn()
    const view = render(<CreateUserForm onCreated={onCreated} onCancel={vi.fn()} />)
    fill()
    submit()
    view.unmount()
    await act(async () => resolve(created))
    expect(onCreated).not.toHaveBeenCalled()
  })
})
