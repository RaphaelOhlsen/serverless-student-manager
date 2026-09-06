/**
 * @vitest-environment jsdom
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const authMocks = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  signIn: vi.fn(),
  signOut: vi.fn(),
}))
const apiMocks = vi.hoisted(() => ({
  authenticatedPost: vi.fn(),
  createStudent: vi.fn(),
  fetchCurrentUserProfile: vi.fn(),
  fetchStudents: vi.fn(),
}))

vi.mock('aws-amplify/auth', () => ({
  confirmSignIn: vi.fn(),
  getCurrentUser: authMocks.getCurrentUser,
  signIn: authMocks.signIn,
  signOut: authMocks.signOut,
}))

vi.mock('@/lib/api', () => ({
  authenticatedPost: apiMocks.authenticatedPost,
  createStudent: apiMocks.createStudent,
  ApiResponseError: class ApiResponseError extends Error {},
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


describe('student creation integration', () => {
  const created = {
    studentId: '00000000-0000-4000-8000-000000000100', fullName: 'Aluno Novo',
    registrationNumber: 'MAT-001', studentEmail: 'a@example.com', phone: '+15555550123',
    birthDate: '2000-01-15', status: 'ACTIVE', version: 1,
    createdAt: '2026-09-06T10:28:53.080Z', updatedAt: '2026-09-06T10:28:53.080Z',
  }
  beforeEach(() => {
    vi.clearAllMocks()
    authMocks.getCurrentUser.mockResolvedValue({})
    apiMocks.fetchCurrentUserProfile.mockResolvedValue(activeProfile)
    apiMocks.fetchStudents.mockResolvedValue(studentsPage)
    authMocks.signOut.mockResolvedValue(undefined)
    apiMocks.createStudent.mockResolvedValue(created)
  })
  afterEach(cleanup)
  async function openAndFill() {
    fireEvent.click(await screen.findByRole('button', { name: 'Novo aluno' }))
    for (const [label, value] of [['Nome completo', created.fullName], ['Matrícula', created.registrationNumber],
      ['E-mail', created.studentEmail], ['Telefone', created.phone], ['Data de nascimento', created.birthDate]])
      fireEvent.change(screen.getByLabelText(label), { target: { value } })
  }
  it('opens and cancels the form preserving the list', async () => {
    render(<App />); await openAndFill(); fireEvent.click(screen.getByText('Cancelar'))
    expect(screen.queryByRole('form', { name: 'Novo aluno' })).toBeNull()
    expect(await screen.findByText('Aluno Exemplo')).toBeTruthy()
  })
  it('closes after success, deduplicates and inserts immediately without refetch', async () => {
    render(<App />); await openAndFill(); fireEvent.click(screen.getByText('Salvar aluno'))
    await screen.findByText('Aluno criado com sucesso.')
    expect(screen.queryByRole('form', { name: 'Novo aluno' })).toBeNull()
    expect(screen.getAllByText('Aluno Novo')).toHaveLength(1)
    expect(screen.queryByText('Aluno Exemplo')).toBeNull()
    expect(apiMocks.fetchStudents).toHaveBeenCalledOnce()
  })
  it('ignores a late initial list after creation', async () => {
    let resolve!: (value: typeof studentsPage) => void
    apiMocks.fetchStudents.mockReturnValueOnce(new Promise((r) => { resolve = r }))
    render(<App />); await openAndFill(); fireEvent.click(screen.getByText('Salvar aluno')); await screen.findByText('Aluno Novo')
    await act(async () => resolve({ items: [], nextCursor: null, hasMore: false }))
    expect(screen.getByText('Aluno Novo')).toBeTruthy(); expect(screen.queryByText('Nenhum aluno encontrado.')).toBeNull()
  })
  it('discards creation after logout and subsequent restored session', async () => {
    let resolve!: (value: typeof created) => void
    apiMocks.createStudent.mockReturnValueOnce(new Promise((r) => { resolve = r }))
    render(<App />); await openAndFill(); fireEvent.click(screen.getByText('Salvar aluno'))
    fireEvent.click(screen.getByRole('button', { name: 'Sair' })); await screen.findByRole('heading', { name: 'Acesse sua conta' })
    apiMocks.fetchCurrentUserProfile.mockResolvedValue({ ...activeProfile, userId: 'other-user' })
    apiMocks.fetchStudents.mockResolvedValue({ items: [], nextCursor: null, hasMore: false })
    authMocks.signIn.mockResolvedValue({ nextStep: { signInStep: 'DONE' } })
    fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'other@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'synthetic-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    await screen.findByText('Nenhum aluno encontrado.')
    await act(async () => resolve(created))
    expect(screen.queryByText('Aluno Novo')).toBeNull(); expect(screen.queryByText('Aluno criado com sucesso.')).toBeNull()
  })
  it('ignores a list response after logout', async () => {
    let resolve!: (value: typeof studentsPage) => void
    apiMocks.fetchStudents.mockReturnValueOnce(new Promise((r) => { resolve = r }))
    render(<App />); await screen.findByText('Carregando alunos…')
    fireEvent.click(screen.getByRole('button', { name: 'Sair' })); await screen.findByRole('heading', { name: 'Acesse sua conta' })
    await act(async () => resolve(studentsPage)); expect(screen.queryByText('Aluno Exemplo')).toBeNull()
  })
})


it('resets activation on logout and isolates the old finally from a new session', async () => {
  vi.clearAllMocks()
  authMocks.getCurrentUser.mockResolvedValue({})
  authMocks.signOut.mockResolvedValue(undefined)
  authMocks.signIn.mockResolvedValue({ nextStep: { signInStep: 'DONE' } })
  apiMocks.fetchCurrentUserProfile.mockResolvedValue(invitedProfile)
  let resolveOldList!: (value: typeof studentsPage) => void
  apiMocks.fetchStudents.mockReturnValueOnce(new Promise((resolve) => { resolveOldList = resolve }))
  apiMocks.authenticatedPost.mockResolvedValueOnce(response(200, successfulActivation))
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'Ativar acesso' }))
  await screen.findByText('Carregando alunos…')
  fireEvent.click(screen.getByRole('button', { name: 'Sair' }))
  await screen.findByRole('heading', { name: 'Acesse sua conta' })
  apiMocks.fetchCurrentUserProfile.mockResolvedValue({ ...invitedProfile, userId: 'new-user' })
  fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'new@example.test' } })
  fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'synthetic-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
  const activate = await screen.findByRole('button', { name: 'Ativar acesso' })
  expect((activate as HTMLButtonElement).disabled).toBe(false)
  expect((screen.getByRole('button', { name: 'Sair' }) as HTMLButtonElement).disabled).toBe(false)

  let resolveNewActivation!: (value: Response) => void
  apiMocks.authenticatedPost.mockReturnValueOnce(new Promise((resolve) => { resolveNewActivation = resolve }))
  fireEvent.click(activate)
  expect(apiMocks.authenticatedPost).toHaveBeenCalledTimes(2)
  await act(async () => resolveOldList(studentsPage))
  expect((screen.getByRole('button', { name: 'Ativando…' }) as HTMLButtonElement).disabled).toBe(true)
  expect(screen.queryByText('Aluno Exemplo')).toBeNull()
  expect(screen.queryByRole('heading', { name: 'Alunos' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Ativando…' }))
  expect(apiMocks.authenticatedPost).toHaveBeenCalledTimes(2)
  await act(async () => resolveNewActivation(response(500)))
  expect((screen.getByRole('button', { name: 'Ativar acesso' }) as HTMLButtonElement).disabled).toBe(false)
  expect((screen.getByRole('button', { name: 'Sair' }) as HTMLButtonElement).disabled).toBe(false)
  cleanup()
})
