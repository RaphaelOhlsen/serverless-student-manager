/**
 * @vitest-environment jsdom
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  changeUserRole: vi.fn(),
  createUser: vi.fn(),
  fetchUser: vi.fn(),
  fetchUsers: vi.fn(),
  resendUserInvitation: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  changeUserRole: apiMocks.changeUserRole,
  createUser: apiMocks.createUser,
  fetchUser: apiMocks.fetchUser,
  fetchUsers: apiMocks.fetchUsers,
  resendUserInvitation: apiMocks.resendUserInvitation,
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

import { UsersList as UsersListComponent } from '@/components/UsersList'
import { ApiResponseError } from '@/lib/api'

const admin = {
  userId: '00000000-0000-4000-8000-000000000001',
  fullName: 'Admin Exemplo',
  email: 'admin@example.test',
  role: 'ADMIN',
  status: 'ACTIVE',
  version: 2,
  createdAt: '2026-09-01T10:00:00.000Z',
  updatedAt: '2026-09-02T10:00:00.000Z',
}
const operator = {
  ...admin,
  userId: '00000000-0000-4000-8000-000000000002',
  fullName: 'Operador Exemplo',
  email: 'operator@example.test',
  role: 'OPERATOR',
  status: 'INVITED',
}
const invited = {
  ...operator,
  version: 1,
  createdAt: '2026-09-30T10:00:00.000Z',
  updatedAt: '2026-09-30T10:00:00.000Z',
}

function UsersList({ currentUserId = admin.userId }: { currentUserId?: string }) {
  return <UsersListComponent currentUserId={currentUserId} />
}

function fillCreateUser() {
  fireEvent.change(screen.getByLabelText('Nome completo'), {
    target: { value: invited.fullName },
  })
  fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: invited.email } })
  fireEvent.change(screen.getByLabelText('Perfil'), { target: { value: invited.role } })
}

async function openResendConfirmation() {
  fireEvent.click(await screen.findByRole('button', { name: 'Reenviar convite' }))
}

function confirmResend() {
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar reenvio' }))
}

describe('UsersList', () => {
  beforeEach(() => {
    apiMocks.changeUserRole.mockReset()
    apiMocks.changeUserRole.mockResolvedValue({ ...admin, role: 'OPERATOR', version: 3 })
    apiMocks.createUser.mockReset()
    apiMocks.createUser.mockResolvedValue(invited)
    apiMocks.fetchUsers.mockReset()
    apiMocks.fetchUsers.mockResolvedValue({ items: [], nextCursor: null })
    apiMocks.fetchUser.mockReset()
    apiMocks.fetchUser.mockResolvedValue(admin)
    apiMocks.resendUserInvitation.mockReset()
    apiMocks.resendUserInvitation.mockResolvedValue(undefined)
  })
  afterEach(() => { cleanup(); vi.clearAllMocks() })

  it('renders loading and then the populated public user fields', async () => {
    let resolve!: (value: object) => void
    apiMocks.fetchUsers.mockReturnValueOnce(new Promise((done) => { resolve = done }))
    render(<UsersList />)
    expect(screen.getByText('Carregando usuários…')).toBeTruthy()
    await act(async () => resolve({ items: [admin, operator], nextCursor: null }))
    expect(await screen.findByText('Admin Exemplo')).toBeTruthy()
    expect(screen.getByText('admin@example.test')).toBeTruthy()
    expect(screen.getAllByText('ADMIN')).toHaveLength(2)
    expect(screen.getAllByText('ACTIVE')).toHaveLength(2)
    expect(screen.getAllByText('OPERATOR')).toHaveLength(2)
    expect(screen.getAllByText('INVITED')).toHaveLength(2)
  })

  it('renders the empty state', async () => {
    render(<UsersList />)
    expect(await screen.findByText('Nenhum usuário encontrado.')).toBeTruthy()
  })

  it('does not load detail until requested and closes without refreshing the list', async () => {
    apiMocks.fetchUsers.mockResolvedValueOnce({ items: [admin], nextCursor: null })
    render(<UsersList />)
    const detailButton = await screen.findByRole('button', { name: 'Ver detalhes' })
    expect(apiMocks.fetchUser).not.toHaveBeenCalled()

    fireEvent.click(detailButton)
    expect(apiMocks.fetchUser).toHaveBeenCalledOnce()
    expect(apiMocks.fetchUser).toHaveBeenCalledWith(admin.userId)
    expect(await screen.findByRole('dialog', { name: 'Detalhes do usuário' })).toBeTruthy()
    expect(await screen.findAllByText(admin.fullName)).toHaveLength(2)

    fireEvent.click(screen.getByRole('button', { name: 'Fechar' }))
    expect(screen.queryByRole('dialog', { name: 'Detalhes do usuário' })).toBeNull()
    expect(apiMocks.fetchUsers).toHaveBeenCalledOnce()
  })

  it('opens and cancels the inline create form', async () => {
    render(<UsersList />)
    await screen.findByText('Nenhum usuário encontrado.')
    fireEvent.click(screen.getByRole('button', { name: 'Novo usuário' }))
    expect(screen.getByRole('form', { name: 'Novo usuário' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByRole('form', { name: 'Novo usuário' })).toBeNull()
    expect(apiMocks.createUser).not.toHaveBeenCalled()
  })

  it('refreshes the first page with applied filters and drops the old cursor after create', async () => {
    apiMocks.fetchUsers
      .mockResolvedValueOnce({ items: [admin], nextCursor: 'old-cursor' })
      .mockResolvedValueOnce({ items: [operator], nextCursor: 'filtered-cursor' })
      .mockResolvedValueOnce({ items: [invited], nextCursor: null })
    render(<UsersList />)
    await screen.findByRole('button', { name: 'Carregar mais' })
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'OPERATOR' } })
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'INVITED' } })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
    await waitFor(() => expect(apiMocks.fetchUsers).toHaveBeenCalledTimes(2))

    fireEvent.click(screen.getByRole('button', { name: 'Novo usuário' }))
    fillCreateUser()
    fireEvent.submit(screen.getByRole('form', { name: 'Novo usuário' }))

    expect(await screen.findByText('Usuário criado e convite solicitado com sucesso.')).toBeTruthy()
    await waitFor(() => expect(apiMocks.fetchUsers).toHaveBeenCalledTimes(3))
    expect(apiMocks.fetchUsers).toHaveBeenLastCalledWith({
      limit: 20, role: 'OPERATOR', status: 'INVITED',
    })
    expect(apiMocks.fetchUsers.mock.calls.at(-1)?.[0]).not.toHaveProperty('cursor')
    expect(screen.queryByRole('button', { name: 'Carregar mais' })).toBeNull()
    expect(screen.queryByRole('form', { name: 'Novo usuário' })).toBeNull()
  })

  it('offers resend only for INVITED users and cancels before creating a key', async () => {
    apiMocks.fetchUsers.mockResolvedValueOnce({ items: [admin, invited], nextCursor: null })
    const uuid = vi.spyOn(crypto, 'randomUUID')
    render(<UsersList />)

    expect(await screen.findAllByRole('button', { name: 'Reenviar convite' })).toHaveLength(1)
    await openResendConfirmation()
    expect(screen.getByText(`Confirmar reenvio do convite para ${invited.fullName}?`)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))

    expect(uuid).not.toHaveBeenCalled()
    expect(apiMocks.resendUserInvitation).not.toHaveBeenCalled()
    expect(screen.queryByText(`Confirmar reenvio do convite para ${invited.fullName}?`)).toBeNull()
  })

  it('sends displayed version once and blocks double submit while pending', async () => {
    let resolve!: () => void
    apiMocks.fetchUsers.mockResolvedValueOnce({ items: [invited], nextCursor: null })
    apiMocks.resendUserInvitation.mockReturnValueOnce(new Promise<void>((done) => { resolve = done }))
    render(<UsersList />)
    await openResendConfirmation()
    confirmResend()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar reenvio' }))

    expect(apiMocks.resendUserInvitation).toHaveBeenCalledOnce()
    expect(apiMocks.resendUserInvitation).toHaveBeenCalledWith(
      invited.userId,
      { expectedVersion: invited.version },
      expect.stringMatching(/^[0-9a-f-]{36}$/),
    )
    expect((screen.getByRole('button', { name: 'Confirmar reenvio' }) as HTMLButtonElement).disabled)
      .toBe(true)
    await act(async () => resolve())
  })

  it.each([
    new TypeError('network secret'),
    new ApiResponseError(500, 'INTERNAL_ERROR'),
    new ApiResponseError(409, 'OPERATION_IN_PROGRESS'),
    new ApiResponseError(503, 'INVITATION_DELIVERY_FAILED'),
  ])('retries recoverable resend failure %o with the same key', async (failure) => {
    apiMocks.fetchUsers.mockResolvedValueOnce({ items: [invited], nextCursor: null })
    apiMocks.resendUserInvitation.mockRejectedValueOnce(failure).mockResolvedValueOnce(undefined)
    render(<UsersList />)
    await openResendConfirmation()
    confirmResend()
    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))

    await waitFor(() => expect(apiMocks.resendUserInvitation).toHaveBeenCalledTimes(2))
    expect(apiMocks.resendUserInvitation.mock.calls[1][2])
      .toBe(apiMocks.resendUserInvitation.mock.calls[0][2])
    expect(screen.queryByText('network secret')).toBeNull()
  })

  it('locks uncertain delivery and creates a new key only after explicit new intent', async () => {
    apiMocks.fetchUsers.mockResolvedValue({ items: [invited], nextCursor: null })
    apiMocks.resendUserInvitation
      .mockRejectedValueOnce(new ApiResponseError(503, 'INVITATION_DELIVERY_UNCERTAIN'))
      .mockResolvedValueOnce(undefined)
    render(<UsersList />)
    await openResendConfirmation()
    confirmResend()

    expect((await screen.findByRole('alert')).textContent).toContain('pode ter sido enviado')
    const locked = screen.getByRole('button', { name: 'Confirmar reenvio' }) as HTMLButtonElement
    expect(locked.disabled).toBe(true)
    fireEvent.click(locked)
    expect(apiMocks.resendUserInvitation).toHaveBeenCalledOnce()

    fireEvent.click(screen.getByRole('button', { name: 'Atualizar lista' }))
    await waitFor(() => expect(apiMocks.fetchUsers).toHaveBeenCalledTimes(2))
    expect(apiMocks.resendUserInvitation).toHaveBeenCalledOnce()

    fireEvent.click(screen.getByRole('button', { name: 'Iniciar nova intenção' }))
    confirmResend()
    await waitFor(() => expect(apiMocks.resendUserInvitation).toHaveBeenCalledTimes(2))
    expect(apiMocks.resendUserInvitation.mock.calls[1][2])
      .not.toBe(apiMocks.resendUserInvitation.mock.calls[0][2])
  })

  it.each([
    ['USER_VERSION_CONFLICT', 'O usuário foi alterado.'],
    ['USER_STATE_CONFLICT', 'não está mais aguardando convite'],
  ])('refreshes and ends the intent on %s', async (code, message) => {
    apiMocks.fetchUsers.mockResolvedValue({ items: [invited], nextCursor: null })
    apiMocks.resendUserInvitation.mockRejectedValueOnce(new ApiResponseError(409, code))
    render(<UsersList />)
    await openResendConfirmation()
    confirmResend()

    expect(await screen.findByText(message, { exact: false })).toBeTruthy()
    await waitFor(() => expect(apiMocks.fetchUsers).toHaveBeenCalledTimes(2))
    expect(screen.queryByText(`Confirmar reenvio do convite para ${invited.fullName}?`)).toBeNull()
  })

  it.each([
    [new ApiResponseError(400, 'INVALID_REQUEST'), 'solicitação de reenvio é inválida'],
    [new ApiResponseError(401, 'UNAUTHORIZED'), 'sessão expirou'],
    [new ApiResponseError(403, 'FORBIDDEN'), 'não tem permissão'],
    [new ApiResponseError(404, 'USER_NOT_FOUND'), 'não foi encontrado'],
    [new ApiResponseError(409, 'IDEMPOTENCY_KEY_REUSED'), 'tentativa é incompatível'],
    [new ApiResponseError(500, 'INTERNAL_ERROR'), 'Não foi possível confirmar'],
  ])('renders a sanitized resend error for %o', async (failure, message) => {
    apiMocks.fetchUsers.mockResolvedValue({ items: [invited], nextCursor: null })
    apiMocks.resendUserInvitation.mockRejectedValueOnce(failure)
    render(<UsersList />)
    await openResendConfirmation()
    confirmResend()

    expect((await screen.findByText(message, { exact: false })).textContent).toContain(message)
    expect(screen.queryByText('sensitive backend detail')).toBeNull()
  })

  it('refreshes the first page after resend with filters preserved and cursor removed', async () => {
    apiMocks.fetchUsers
      .mockResolvedValueOnce({ items: [invited], nextCursor: 'old-cursor' })
      .mockResolvedValueOnce({ items: [invited], nextCursor: 'filtered-cursor' })
      .mockResolvedValueOnce({ items: [invited], nextCursor: null })
    render(<UsersList />)
    await screen.findByRole('button', { name: 'Carregar mais' })
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'OPERATOR' } })
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'INVITED' } })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
    await waitFor(() => expect(apiMocks.fetchUsers).toHaveBeenCalledTimes(2))

    await openResendConfirmation()
    confirmResend()

    expect(await screen.findByText('Convite reenviado com sucesso.')).toBeTruthy()
    await waitFor(() => expect(apiMocks.fetchUsers).toHaveBeenCalledTimes(3))
    expect(apiMocks.fetchUsers).toHaveBeenLastCalledWith({
      limit: 20, role: 'OPERATOR', status: 'INVITED',
    })
    expect(apiMocks.fetchUsers.mock.calls.at(-1)?.[0]).not.toHaveProperty('cursor')
    expect(screen.queryByRole('button', { name: 'Carregar mais' })).toBeNull()
  })

  it('ignores a stale post-resend refresh after a newer filter request', async () => {
    let resolveRefresh!: (value: object) => void
    apiMocks.fetchUsers
      .mockResolvedValueOnce({ items: [invited], nextCursor: null })
      .mockReturnValueOnce(new Promise((done) => { resolveRefresh = done }))
      .mockResolvedValueOnce({ items: [], nextCursor: null })
    render(<UsersList />)
    await openResendConfirmation()
    confirmResend()
    await screen.findByText('Convite reenviado com sucesso.')

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'ACTIVE' } })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
    expect(await screen.findByText('Nenhum usuário encontrado.')).toBeTruthy()
    await act(async () => resolveRefresh({ items: [invited], nextCursor: null }))
    expect(screen.queryByText(invited.fullName)).toBeNull()
  })

  it.each([
    [new ApiResponseError(400, 'INVALID_REQUEST'), 'A busca informada é inválida.'],
    [new ApiResponseError(401), 'Sua sessão expirou.'],
    [new ApiResponseError(403, 'FORBIDDEN'), 'Você não tem permissão'],
    [new ApiResponseError(500, 'INTERNAL_ERROR'), 'Não foi possível carregar os usuários.'],
    [new TypeError('network detail'), 'Não foi possível carregar os usuários.'],
  ])('renders a safe error for %o', async (failure, message) => {
    apiMocks.fetchUsers.mockRejectedValueOnce(failure)
    render(<UsersList />)
    expect((await screen.findByRole('alert')).textContent).toContain(message)
    expect(screen.queryByText('network detail')).toBeNull()
  })

  it('retries the exact failed query', async () => {
    apiMocks.fetchUsers
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockResolvedValueOnce({ items: [admin], nextCursor: null })
    render(<UsersList />)
    fireEvent.click(await screen.findByRole('button', { name: 'Tentar novamente' }))
    expect(await screen.findByText('Admin Exemplo')).toBeTruthy()
    expect(apiMocks.fetchUsers).toHaveBeenNthCalledWith(1, {
      limit: 20, role: 'ALL', status: 'ALL',
    })
    expect(apiMocks.fetchUsers).toHaveBeenNthCalledWith(2, {
      limit: 20, role: 'ALL', status: 'ALL',
    })
  })

  it('submits an explicit name search without an email', async () => {
    render(<UsersList />)
    await screen.findByText('Nenhum usuário encontrado.')
    fireEvent.change(screen.getByLabelText('Nome'), { target: { value: '  Ana  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
    await waitFor(() => expect(apiMocks.fetchUsers).toHaveBeenLastCalledWith({
      limit: 20, role: 'ALL', status: 'ALL', namePrefix: 'Ana',
    }))
    expect(apiMocks.fetchUsers.mock.calls.at(-1)?.[0]).not.toHaveProperty('email')
  })

  it('switches to email search and never combines both search parameters', async () => {
    render(<UsersList />)
    await screen.findByText('Nenhum usuário encontrado.')
    fireEvent.change(screen.getByLabelText('Nome'), { target: { value: 'Ana' } })
    fireEvent.change(screen.getByLabelText('Buscar por'), { target: { value: 'email' } })
    expect((screen.getByLabelText('E-mail') as HTMLInputElement).value).toBe('')
    fireEvent.change(screen.getByLabelText('E-mail'), {
      target: { value: ' ADMIN@EXAMPLE.TEST ' },
    })
    fireEvent.submit(screen.getByRole('form', { name: 'Filtros de usuários' }))
    await waitFor(() => expect(apiMocks.fetchUsers).toHaveBeenLastCalledWith({
      limit: 20, role: 'ALL', status: 'ALL', email: 'ADMIN@EXAMPLE.TEST',
    }))
    expect(apiMocks.fetchUsers.mock.calls.at(-1)?.[0]).not.toHaveProperty('namePrefix')
  })

  it('applies role and status filters', async () => {
    render(<UsersList />)
    await screen.findByText('Nenhum usuário encontrado.')
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'OPERATOR' } })
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'INACTIVE' } })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
    await waitFor(() => expect(apiMocks.fetchUsers).toHaveBeenLastCalledWith({
      limit: 20, role: 'OPERATOR', status: 'INACTIVE',
    }))
  })

  it('sends the returned cursor unchanged and appends the next page', async () => {
    apiMocks.fetchUsers
      .mockResolvedValueOnce({ items: [admin], nextCursor: 'opaque+/=cursor' })
      .mockResolvedValueOnce({ items: [operator], nextCursor: null })
    render(<UsersList />)
    fireEvent.click(await screen.findByRole('button', { name: 'Carregar mais' }))
    expect(await screen.findByText('Operador Exemplo')).toBeTruthy()
    expect(screen.getByText('Admin Exemplo')).toBeTruthy()
    expect(apiMocks.fetchUsers).toHaveBeenLastCalledWith({
      limit: 20, role: 'ALL', status: 'ALL', cursor: 'opaque+/=cursor',
    })
  })

  it('drops the old cursor and results when the query changes', async () => {
    apiMocks.fetchUsers.mockResolvedValueOnce({ items: [admin], nextCursor: 'old-cursor' })
    render(<UsersList />)
    await screen.findByRole('button', { name: 'Carregar mais' })
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'INVITED' } })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
    await waitFor(() => expect(apiMocks.fetchUsers).toHaveBeenLastCalledWith({
      limit: 20, role: 'ALL', status: 'INVITED',
    }))
    expect(apiMocks.fetchUsers.mock.calls.at(-1)?.[0]).not.toHaveProperty('cursor')
    expect(screen.queryByText('Admin Exemplo')).toBeNull()
  })

  it('ignores an older response after a newer query completes', async () => {
    let resolveInitial!: (value: object) => void
    apiMocks.fetchUsers.mockReturnValueOnce(new Promise((done) => { resolveInitial = done }))
    render(<UsersList />)
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'INVITED' } })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
    expect(await screen.findByText('Nenhum usuário encontrado.')).toBeTruthy()
    await act(async () => resolveInitial({ items: [admin], nextCursor: null }))
    expect(screen.queryByText('Admin Exemplo')).toBeNull()
  })

  it('ignores a stale post-create refresh after a newer filter request', async () => {
    let resolveRefresh!: (value: object) => void
    apiMocks.fetchUsers
      .mockResolvedValueOnce({ items: [], nextCursor: null })
      .mockReturnValueOnce(new Promise((done) => { resolveRefresh = done }))
      .mockResolvedValueOnce({ items: [operator], nextCursor: null })
    render(<UsersList />)
    await screen.findByText('Nenhum usuário encontrado.')
    fireEvent.click(screen.getByRole('button', { name: 'Novo usuário' }))
    fillCreateUser()
    fireEvent.submit(screen.getByRole('form', { name: 'Novo usuário' }))
    await screen.findByText('Usuário criado e convite solicitado com sucesso.')

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'INVITED' } })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
    expect(await screen.findByText('Operador Exemplo')).toBeTruthy()
    await act(async () => resolveRefresh({ items: [admin], nextCursor: null }))
    expect(screen.queryByText('Admin Exemplo')).toBeNull()
  })

  it('passes current user identity to the detail self guard', async () => {
    apiMocks.fetchUsers.mockResolvedValueOnce({ items: [admin, operator], nextCursor: null })
    apiMocks.fetchUser.mockImplementation(async (userId: string) => (
      userId === admin.userId ? admin : operator
    ))
    render(<UsersList currentUserId={admin.userId} />)
    const details = await screen.findAllByRole('button', { name: 'Ver detalhes' })

    fireEvent.click(details[0])
    await screen.findByRole('dialog', { name: 'Detalhes do usuário' })
    expect(screen.queryByRole('button', { name: 'Alterar role' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Fechar' }))

    fireEvent.click(details[1])
    expect(await screen.findByRole('button', { name: 'Alterar role' })).toBeTruthy()
  })

  it('refreshes the first page with filters preserved and cursor discarded after role change', async () => {
    const updated = { ...operator, role: 'ADMIN' as const, version: operator.version + 1 }
    apiMocks.fetchUsers
      .mockResolvedValueOnce({ items: [operator], nextCursor: 'old-cursor' })
      .mockResolvedValueOnce({ items: [operator], nextCursor: 'filtered-cursor' })
      .mockResolvedValueOnce({ items: [updated], nextCursor: null })
    apiMocks.fetchUser.mockResolvedValueOnce(operator).mockResolvedValueOnce(updated)
    apiMocks.changeUserRole.mockResolvedValueOnce(updated)
    render(<UsersList currentUserId={admin.userId} />)
    await screen.findByRole('button', { name: 'Carregar mais' })
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'OPERATOR' } })
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'INVITED' } })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
    await waitFor(() => expect(apiMocks.fetchUsers).toHaveBeenCalledTimes(2))

    fireEvent.click(screen.getByRole('button', { name: 'Ver detalhes' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Alterar role' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar alteração' }))

    await waitFor(() => expect(apiMocks.fetchUsers).toHaveBeenCalledTimes(3))
    expect(apiMocks.fetchUsers).toHaveBeenLastCalledWith({
      limit: 20, role: 'OPERATOR', status: 'INVITED',
    })
    expect(apiMocks.fetchUsers.mock.calls.at(-1)?.[0]).not.toHaveProperty('cursor')
    expect(apiMocks.fetchUser).toHaveBeenCalledTimes(2)
    expect(await screen.findByText(`Role de ${operator.fullName} alterada para ADMIN.`)).toBeTruthy()
  })

  it('keeps stale post-role-change refresh from replacing a newer filter result', async () => {
    let resolveRefresh!: (value: object) => void
    const updated = { ...operator, role: 'ADMIN' as const, version: operator.version + 1 }
    apiMocks.fetchUsers
      .mockResolvedValueOnce({ items: [operator], nextCursor: null })
      .mockReturnValueOnce(new Promise((done) => { resolveRefresh = done }))
      .mockResolvedValueOnce({ items: [], nextCursor: null })
    apiMocks.fetchUser.mockResolvedValueOnce(operator).mockResolvedValueOnce(updated)
    apiMocks.changeUserRole.mockResolvedValueOnce(updated)
    render(<UsersList currentUserId={admin.userId} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Ver detalhes' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Alterar role' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar alteração' }))
    await screen.findByText(`Role de ${operator.fullName} alterada para ADMIN.`)

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'ACTIVE' } })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
    expect(await screen.findByText('Nenhum usuário encontrado.')).toBeTruthy()
    await act(async () => resolveRefresh({ items: [operator], nextCursor: null }))
    expect(screen.queryByRole('listitem')).toBeNull()
  })
})
