/**
 * @vitest-environment jsdom
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ createUser: vi.fn(), fetchUsers: vi.fn() }))

vi.mock('@/lib/api', () => ({
  createUser: apiMocks.createUser,
  fetchUsers: apiMocks.fetchUsers,
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

import { UsersList } from '@/components/UsersList'
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

function fillCreateUser() {
  fireEvent.change(screen.getByLabelText('Nome completo'), {
    target: { value: invited.fullName },
  })
  fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: invited.email } })
  fireEvent.change(screen.getByLabelText('Perfil'), { target: { value: invited.role } })
}

describe('UsersList', () => {
  beforeEach(() => {
    apiMocks.createUser.mockReset()
    apiMocks.createUser.mockResolvedValue(invited)
    apiMocks.fetchUsers.mockReset()
    apiMocks.fetchUsers.mockResolvedValue({ items: [], nextCursor: null })
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
})
