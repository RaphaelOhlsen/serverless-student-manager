/**
 * @vitest-environment jsdom
 */

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ fetchUser: vi.fn() }))

vi.mock('@/lib/api', () => ({
  fetchUser: apiMocks.fetchUser,
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

import { UserDetailDialog } from '@/components/UserDetailDialog'
import { ApiResponseError } from '@/lib/api'

const first = {
  userId: '00000000-0000-4000-8000-000000000001',
  fullName: 'Admin Exemplo',
  email: 'admin@example.test',
  role: 'ADMIN',
  status: 'ACTIVE',
  version: 3,
  createdAt: '2026-09-01T10:00:00.000Z',
  updatedAt: '2026-09-02T10:00:00.000Z',
}
const second = {
  ...first,
  userId: '00000000-0000-4000-8000-000000000002',
  fullName: 'Operador Exemplo',
  email: 'operator@example.test',
  role: 'OPERATOR',
  status: 'INVITED',
  version: 1,
}

describe('UserDetailDialog', () => {
  beforeEach(() => {
    apiMocks.fetchUser.mockReset()
    apiMocks.fetchUser.mockResolvedValue(first)
  })
  afterEach(() => { cleanup(); vi.clearAllMocks() })

  it('loads fresh detail and presents only the public fields', async () => {
    render(<UserDetailDialog userId={first.userId} onClose={vi.fn()} />)
    expect(screen.getByText('Carregando detalhes…')).toBeTruthy()
    expect(apiMocks.fetchUser).toHaveBeenCalledWith(first.userId)

    expect(await screen.findByText(first.fullName)).toBeTruthy()
    expect(screen.getByText(first.email)).toBeTruthy()
    expect(screen.getByText('ADMIN')).toBeTruthy()
    expect(screen.getByText('ACTIVE')).toBeTruthy()
    expect(screen.getByText(String(first.version))).toBeTruthy()
    expect(screen.getByText(first.createdAt)).toBeTruthy()
    expect(screen.getByText(first.updatedAt)).toBeTruthy()
    expect(screen.queryByText('authVersion')).toBeNull()
    expect(screen.queryByText('cognitoSub')).toBeNull()
  })

  it.each([
    [new ApiResponseError(401), 'Sua sessão expirou.'],
    [new ApiResponseError(403, 'FORBIDDEN'), 'não tem permissão'],
    [new ApiResponseError(404, 'USER_NOT_FOUND'), 'não foi encontrado'],
    [new ApiResponseError(500, 'INTERNAL_ERROR'), 'Não foi possível carregar'],
    [new TypeError('network secret'), 'Não foi possível carregar'],
  ])('renders a sanitized error for %o', async (failure, message) => {
    apiMocks.fetchUser.mockRejectedValueOnce(failure)
    render(<UserDetailDialog userId={first.userId} onClose={vi.fn()} />)

    expect((await screen.findByRole('alert')).textContent).toContain(message)
    expect(screen.queryByText('network secret')).toBeNull()
    expect(screen.queryByText('INTERNAL_ERROR')).toBeNull()
  })

  it('closes from the button and Escape', () => {
    const onClose = vi.fn()
    render(<UserDetailDialog userId={first.userId} onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: 'Fechar' }))
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('ignores an older response after the selected user changes', async () => {
    let resolveFirst!: (value: typeof first) => void
    apiMocks.fetchUser
      .mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve }))
      .mockResolvedValueOnce(second)
    const view = render(<UserDetailDialog userId={first.userId} onClose={vi.fn()} />)
    view.rerender(<UserDetailDialog userId={second.userId} onClose={vi.fn()} />)

    expect(await screen.findByText(second.fullName)).toBeTruthy()
    await act(async () => resolveFirst(first))
    expect(screen.queryByText(first.fullName)).toBeNull()
    expect(screen.getByText(second.fullName)).toBeTruthy()
  })

  it('ignores a response that arrives after closing', async () => {
    let resolve!: (value: typeof first) => void
    apiMocks.fetchUser.mockReturnValueOnce(new Promise((done) => { resolve = done }))
    const view = render(<UserDetailDialog userId={first.userId} onClose={vi.fn()} />)
    view.unmount()

    await act(async () => resolve(first))
    expect(screen.queryByText(first.fullName)).toBeNull()
  })
})
