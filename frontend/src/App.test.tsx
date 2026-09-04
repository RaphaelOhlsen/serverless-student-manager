/**
 * @vitest-environment jsdom
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const authMocks = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  signOut: vi.fn(),
}))
const apiMocks = vi.hoisted(() => ({
  authenticatedPost: vi.fn(),
  fetchCurrentUserProfile: vi.fn(),
  fetchStudents: vi.fn(),
}))

vi.mock('aws-amplify/auth', () => ({
  confirmSignIn: vi.fn(),
  getCurrentUser: authMocks.getCurrentUser,
  signIn: vi.fn(),
  signOut: authMocks.signOut,
}))

vi.mock('@/lib/api', () => ({
  authenticatedPost: apiMocks.authenticatedPost,
  fetchCurrentUserProfile: apiMocks.fetchCurrentUserProfile,
  fetchStudents: apiMocks.fetchStudents,
  AuthSessionUnavailableError: class AuthSessionUnavailableError extends Error {},
}))

import App from '@/App'

const invitedProfile = {
  userId: '00000000-0000-4000-8000-000000000001',
  fullName: 'Usuário Convidado',
  email: 'convidado@example.test',
  role: 'ADMIN',
  status: 'INVITED',
  authVersion: 1,
}
const activeProfile = { ...invitedProfile, status: 'ACTIVE' }
const successfulActivation = {
  userId: invitedProfile.userId,
  role: 'ADMIN',
  status: 'ACTIVE',
  authVersion: 1,
}
const studentsPage = {
  items: [
    {
      studentId: '00000000-0000-4000-8000-000000000100',
      registrationNumber: 'MAT-001',
      fullName: 'Aluno Exemplo',
      status: 'ACTIVE',
    },
  ],
  nextCursor: null,
  hasMore: false,
}

function response(status: number, body?: object): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), { status })
}

function mockUuidSequence(...values: ReturnType<Crypto['randomUUID']>[]) {
  const randomUUID = vi.spyOn(globalThis.crypto, 'randomUUID')
  for (const value of values) randomUUID.mockReturnValueOnce(value)
  return randomUUID
}

async function renderInvitedApp() {
  apiMocks.fetchCurrentUserProfile.mockResolvedValue(invitedProfile)
  render(<App />)
  return screen.findByRole('button', { name: 'Ativar acesso' })
}

describe('post-login operational flow', () => {
  beforeEach(() => {
    authMocks.getCurrentUser.mockResolvedValue({ username: 'fake-user' })
    authMocks.signOut.mockResolvedValue(undefined)
    apiMocks.fetchStudents.mockResolvedValue({ items: [], nextCursor: null, hasMore: false })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('resolves an ACTIVE restored session before loading students', async () => {
    apiMocks.fetchCurrentUserProfile.mockResolvedValue(activeProfile)
    apiMocks.fetchStudents.mockResolvedValue(studentsPage)
    render(<App />)

    expect(await screen.findByText('Aluno Exemplo')).toBeTruthy()
    expect(apiMocks.fetchCurrentUserProfile).toHaveBeenCalledOnce()
    expect(apiMocks.fetchStudents).toHaveBeenCalledOnce()
    expect(apiMocks.fetchCurrentUserProfile.mock.invocationCallOrder[0]).toBeLessThan(
      apiMocks.fetchStudents.mock.invocationCallOrder[0] ?? 0,
    )
  })

  it('shows activation for an INVITED restored session without loading students', async () => {
    expect(await renderInvitedApp()).toBeTruthy()
    expect(apiMocks.fetchStudents).not.toHaveBeenCalled()
  })

  it('loads the operational list immediately after successful activation', async () => {
    apiMocks.authenticatedPost.mockResolvedValue(response(200, successfulActivation))
    apiMocks.fetchStudents.mockResolvedValue(studentsPage)
    fireEvent.click(await renderInvitedApp())

    expect(await screen.findByText('Acesso ativado com sucesso.')).toBeTruthy()
    expect(await screen.findByText('Matrícula: MAT-001')).toBeTruthy()
    expect(apiMocks.fetchStudents).toHaveBeenCalledOnce()
  })

  it('renders student name, registration number and status', async () => {
    apiMocks.fetchCurrentUserProfile.mockResolvedValue(activeProfile)
    apiMocks.fetchStudents.mockResolvedValue(studentsPage)
    render(<App />)

    expect(await screen.findByText('Aluno Exemplo')).toBeTruthy()
    expect(screen.getByText('Matrícula: MAT-001')).toBeTruthy()
    expect(screen.getByText('ACTIVE')).toBeTruthy()
  })

  it('renders an empty state', async () => {
    apiMocks.fetchCurrentUserProfile.mockResolvedValue(activeProfile)
    render(<App />)
    expect(await screen.findByText('Nenhum aluno encontrado.')).toBeTruthy()
  })

  it('renders a profile resolution error without showing activation', async () => {
    apiMocks.fetchCurrentUserProfile.mockRejectedValue(new Error('failed'))
    render(<App />)

    expect(await screen.findByText('Não foi possível carregar seu perfil. Tente novamente.')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Ativar acesso' })).toBeNull()
    expect(apiMocks.fetchStudents).not.toHaveBeenCalled()
  })

  it('renders a recoverable students error', async () => {
    apiMocks.fetchCurrentUserProfile.mockResolvedValue(activeProfile)
    apiMocks.fetchStudents.mockRejectedValue(new Error('failed'))
    render(<App />)

    expect(await screen.findByText('Não foi possível carregar os alunos. Tente novamente.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeTruthy()
  })

  it('keeps logout available after profile resolution', async () => {
    apiMocks.fetchCurrentUserProfile.mockResolvedValue(activeProfile)
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Sair' }))

    await waitFor(() => expect(authMocks.signOut).toHaveBeenCalledOnce())
    expect(await screen.findByRole('button', { name: 'Entrar' })).toBeTruthy()
  })

  it('keeps logout available while activation is pending', async () => {
    await renderInvitedApp()
    fireEvent.click(screen.getByRole('button', { name: 'Sair' }))

    await waitFor(() => expect(authMocks.signOut).toHaveBeenCalledOnce())
    expect(await screen.findByRole('button', { name: 'Entrar' })).toBeTruthy()
    expect(apiMocks.fetchStudents).not.toHaveBeenCalled()
  })
})

describe('activation idempotency lifecycle', () => {
  beforeEach(() => {
    authMocks.getCurrentUser.mockResolvedValue({ username: 'fake-user' })
    authMocks.signOut.mockResolvedValue(undefined)
    apiMocks.fetchStudents.mockResolvedValue({ items: [], nextCursor: null, hasMore: false })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('reuses the same key after a temporary failure', async () => {
    mockUuidSequence('00000000-0000-4000-8000-000000000010')
    apiMocks.authenticatedPost
      .mockResolvedValueOnce(response(500))
      .mockResolvedValueOnce(response(200, successfulActivation))
    const button = await renderInvitedApp()

    fireEvent.click(button)
    await screen.findByText('Não foi possível ativar o acesso agora. Tente novamente.')
    fireEvent.click(button)
    await screen.findByText('Acesso ativado com sucesso.')

    expect(apiMocks.authenticatedPost).toHaveBeenCalledTimes(2)
    expect(apiMocks.authenticatedPost.mock.calls[0]?.[1]).toBe(
      apiMocks.authenticatedPost.mock.calls[1]?.[1],
    )
  })

  it('discards the key after a definitive HTTP error', async () => {
    mockUuidSequence(
      '00000000-0000-4000-8000-000000000030',
      '00000000-0000-4000-8000-000000000031',
    )
    apiMocks.authenticatedPost
      .mockResolvedValueOnce(response(409))
      .mockResolvedValueOnce(response(200, successfulActivation))
    const button = await renderInvitedApp()

    fireEvent.click(button)
    await screen.findByText('A ativação ainda não é permitida ou o estado é incompatível.')
    fireEvent.click(button)
    await screen.findByText('Acesso ativado com sucesso.')

    expect(apiMocks.authenticatedPost.mock.calls[0]?.[1]).not.toBe(
      apiMocks.authenticatedPost.mock.calls[1]?.[1],
    )
  })

  it('blocks a second activation while the first request is pending', async () => {
    mockUuidSequence('00000000-0000-4000-8000-000000000040')
    let resolveRequest!: (value: Response) => void
    apiMocks.authenticatedPost.mockReturnValue(
      new Promise<Response>((resolve) => { resolveRequest = resolve }),
    )
    const button = await renderInvitedApp()

    fireEvent.click(button)
    fireEvent.click(button)
    expect(apiMocks.authenticatedPost).toHaveBeenCalledOnce()
    expect((button as HTMLButtonElement).disabled).toBe(true)

    await act(async () => { resolveRequest(response(200, successfulActivation)) })
    expect(await screen.findByText('Acesso ativado com sucesso.')).toBeTruthy()
  })

  it('rejects a string authVersion in the activation response', async () => {
    mockUuidSequence('00000000-0000-4000-8000-000000000050')
    apiMocks.authenticatedPost.mockResolvedValue(
      response(200, { ...successfulActivation, authVersion: '1' }),
    )
    fireEvent.click(await renderInvitedApp())

    expect(await screen.findByText('Não foi possível ativar o acesso agora. Tente novamente.')).toBeTruthy()
    expect(apiMocks.fetchStudents).not.toHaveBeenCalled()
  })
})
