/**
 * @vitest-environment jsdom
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const authMocks = vi.hoisted(() => ({ fetchAuthSession: vi.fn() }))

vi.mock('aws-amplify/auth', () => ({ fetchAuthSession: authMocks.fetchAuthSession }))
vi.mock('@/config/env', () => ({ env: { apiBaseUrl: 'https://api.example.test/' } }))

import {
  ApiResponseError,
  authenticatedPost,
  fetchCurrentUserProfile,
  fetchStudents,
} from '@/lib/api'

const profile = {
  userId: '00000000-0000-4000-8000-000000000001',
  fullName: 'Usuário Exemplo',
  email: 'usuario@example.test',
  role: 'ADMIN',
  status: 'ACTIVE',
  authVersion: 1,
}
const studentsPage = {
  items: [{
    studentId: '00000000-0000-4000-8000-000000000100',
    registrationNumber: 'MAT-001',
    fullName: 'Aluno Exemplo',
    status: 'ACTIVE',
  }],
  nextCursor: null,
  hasMore: false,
}

describe('authenticated API requests', () => {
  beforeEach(() => {
    authMocks.fetchAuthSession.mockResolvedValue({
      tokens: { accessToken: { toString: () => 'fake-access-token' } },
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('gets and validates the current profile with the access token', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(profile), { status: 200 }),
    )
    await expect(fetchCurrentUserProfile()).resolves.toEqual(profile)
    expect(fetchMock).toHaveBeenCalledWith('https://api.example.test/users/me', {
      method: 'GET',
      headers: { Authorization: 'Bearer fake-access-token' },
    })
  })

  it('rejects a string authVersion in the current profile', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ...profile, authVersion: '1' }), { status: 200 }),
    )
    await expect(fetchCurrentUserProfile()).rejects.toBeInstanceOf(ApiResponseError)
  })

  it('gets and validates the default students page with the access token', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(studentsPage), { status: 200 }),
    )
    await expect(fetchStudents()).resolves.toEqual(studentsPage)
    expect(fetchMock).toHaveBeenCalledWith('https://api.example.test/students', {
      method: 'GET',
      headers: { Authorization: 'Bearer fake-access-token' },
    })
  })

  it('rejects an invalid students response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ...studentsPage, hasMore: 'false' }), { status: 200 }),
    )
    await expect(fetchStudents()).rejects.toBeInstanceOf(ApiResponseError)
  })

  it('sends activation with authentication, idempotency and no body', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(null, { status: 200 }),
    )
    await authenticatedPost(
      '/users/me/activation',
      '00000000-0000-4000-8000-000000000002',
    )
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
})
