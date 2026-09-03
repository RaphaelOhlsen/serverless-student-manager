/**
 * @vitest-environment jsdom
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const authMocks = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
}))
const apiMocks = vi.hoisted(() => ({
  authenticatedGet: vi.fn(),
  authenticatedPost: vi.fn(),
}))

vi.mock('aws-amplify/auth', () => ({
  confirmSignIn: vi.fn(),
  getCurrentUser: authMocks.getCurrentUser,
  signIn: vi.fn(),
  signOut: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  authenticatedGet: apiMocks.authenticatedGet,
  authenticatedPost: apiMocks.authenticatedPost,
  AuthSessionUnavailableError: class AuthSessionUnavailableError extends Error {},
}))

import App from '@/App'

const successfulActivation = {
  userId: '00000000-0000-4000-8000-000000000001',
  role: 'ADMIN',
  status: 'ACTIVE',
  authVersion: 1,
}

function response(status: number, body?: object): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
  })
}

function mockUuidSequence(...values: ReturnType<Crypto['randomUUID']>[]) {
  const randomUUID = vi.spyOn(globalThis.crypto, 'randomUUID')
  for (const value of values) {
    randomUUID.mockReturnValueOnce(value)
  }
  return randomUUID
}

async function renderAuthenticatedApp() {
  render(<App />)
  return screen.findByRole('button', { name: 'Ativar acesso' })
}

describe('activation idempotency lifecycle', () => {
  beforeEach(() => {
    authMocks.getCurrentUser.mockResolvedValue({ username: 'fake-user' })
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
    const button = await renderAuthenticatedApp()

    fireEvent.click(button)
    await screen.findByText('Não foi possível ativar o acesso agora. Tente novamente.')
    fireEvent.click(button)
    await screen.findByText('Acesso ativado com sucesso.')

    expect(apiMocks.authenticatedPost).toHaveBeenCalledTimes(2)
    expect(apiMocks.authenticatedPost.mock.calls[0]?.[1]).toBe(
      apiMocks.authenticatedPost.mock.calls[1]?.[1],
    )
  })

  it('discards the key after success', async () => {
    mockUuidSequence(
      '00000000-0000-4000-8000-000000000020',
      '00000000-0000-4000-8000-000000000021',
    )
    apiMocks.authenticatedPost.mockResolvedValue(
      response(200, successfulActivation),
    )
    const button = await renderAuthenticatedApp()

    fireEvent.click(button)
    await screen.findByText('Acesso ativado com sucesso.')
    fireEvent.click(button)
    await waitFor(() => expect(apiMocks.authenticatedPost).toHaveBeenCalledTimes(2))

    expect(apiMocks.authenticatedPost.mock.calls[0]?.[1]).not.toBe(
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
    const button = await renderAuthenticatedApp()

    fireEvent.click(button)
    await screen.findByText(
      'A ativação ainda não é permitida ou o estado é incompatível.',
    )
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
      new Promise<Response>((resolve) => {
        resolveRequest = resolve
      }),
    )
    const button = await renderAuthenticatedApp()

    fireEvent.click(button)
    fireEvent.click(button)

    expect(apiMocks.authenticatedPost).toHaveBeenCalledOnce()
    expect((button as HTMLButtonElement).disabled).toBe(true)

    await act(async () => {
      resolveRequest(response(200, successfulActivation))
    })
    expect(await screen.findByText('Acesso ativado com sucesso.')).toBeTruthy()
  })
})
