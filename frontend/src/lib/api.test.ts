/**
 * @vitest-environment jsdom
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { createElement } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const authMocks = vi.hoisted(() => ({
  fetchAuthSession: vi.fn(),
  getCurrentUser: vi.fn(),
}))

vi.mock('aws-amplify/auth', () => ({
  confirmSignIn: vi.fn(),
  fetchAuthSession: authMocks.fetchAuthSession,
  getCurrentUser: authMocks.getCurrentUser,
  signIn: vi.fn(),
  signOut: vi.fn(),
}))

vi.mock('@/config/env', () => ({
  env: {
    apiBaseUrl: 'https://api.example.test/',
  },
}))

import App from '@/App'
import { authenticatedPost } from '@/lib/api'

const activationResponse = {
  userId: '00000000-0000-4000-8000-000000000001',
  role: 'ADMIN',
  status: 'ACTIVE',
  authVersion: 1,
}

describe('authenticated activation request', () => {
  beforeEach(() => {
    authMocks.fetchAuthSession.mockResolvedValue({
      tokens: {
        accessToken: {
          toString: () => 'fake-access-token',
        },
      },
    })
    authMocks.getCurrentUser.mockResolvedValue({ username: 'fake-user' })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('sends the activation POST with authentication and idempotency headers and no body', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(null, { status: 200 }))

    await authenticatedPost(
      '/users/me/activation',
      '00000000-0000-4000-8000-000000000002',
    )

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.test/users/me/activation',
      {
        method: 'POST',
        headers: {
          Authorization: 'Bearer fake-access-token',
          'Idempotency-Key': '00000000-0000-4000-8000-000000000002',
        },
      },
    )
    expect(fetchMock.mock.calls[0]?.[1]).not.toHaveProperty('body')
  })

  it('accepts an integer authVersion in the activation response', async () => {
    vi.spyOn(globalThis.crypto, 'randomUUID').mockReturnValue(
      '00000000-0000-4000-8000-000000000003',
    )
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(activationResponse), { status: 200 }),
    )

    render(createElement(App))
    fireEvent.click(await screen.findByRole('button', { name: 'Ativar acesso' }))

    expect(await screen.findByText('Acesso ativado com sucesso.')).toBeTruthy()
  })

  it('rejects a string authVersion in the activation response', async () => {
    vi.spyOn(globalThis.crypto, 'randomUUID').mockReturnValue(
      '00000000-0000-4000-8000-000000000004',
    )
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ ...activationResponse, authVersion: '1' }),
        { status: 200 },
      ),
    )

    render(createElement(App))
    fireEvent.click(await screen.findByRole('button', { name: 'Ativar acesso' }))

    expect(
      await screen.findByText(
        'Não foi possível ativar o acesso agora. Tente novamente.',
      ),
    ).toBeTruthy()
  })
})
