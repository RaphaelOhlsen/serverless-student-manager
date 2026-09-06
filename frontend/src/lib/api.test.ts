/**
 * @vitest-environment jsdom
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const authMocks = vi.hoisted(() => ({ fetchAuthSession: vi.fn() }))

vi.mock('aws-amplify/auth', () => ({ fetchAuthSession: authMocks.fetchAuthSession }))
vi.mock('@/config/env', () => ({ env: { apiBaseUrl: 'https://api.example.test/' } }))

import {
  ApiResponseError,
  createStudent,
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


describe('create student contract', () => {
  const body = { fullName: 'Aluno Teste', registrationNumber: 'MAT-001', studentEmail: 'a@example.com', phone: '+15555550123', birthDate: '2000-01-15' }
  const created = { ...body, studentId: '00000000-0000-4000-8000-000000000100', status: 'ACTIVE', version: 1, createdAt: '2026-09-06T10:28:53.080Z', updatedAt: '2026-09-06T10:28:53.080Z' }
  beforeEach(() => authMocks.fetchAuthSession.mockResolvedValue({ tokens: { accessToken: { toString: () => 'fake-access-token' } } }))
  afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks() })
  it('posts exactly the request and validates the ten public fields', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(created), { status: 201 }))
    await expect(createStudent(body, '00000000-0000-4000-8000-000000000001')).resolves.toEqual(created)
    expect(Object.keys(created)).toHaveLength(10)
    expect(fetchMock).toHaveBeenCalledWith('https://api.example.test/students', { method: 'POST', headers: {
      Authorization: 'Bearer fake-access-token', 'Content-Type': 'application/json', 'Idempotency-Key': '00000000-0000-4000-8000-000000000001',
    }, body: JSON.stringify(body) })
  })
  it.each(['PK', 'SK', 'normalizedName', 'normalizedEmail', 'createdBy', 'updatedBy'])('rejects internal field %s', async (field) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ ...created, [field]: 'internal' }), { status: 201 }))
    await expect(createStudent(body, 'key')).rejects.toBeInstanceOf(ApiResponseError)
  })
  it.each(Object.keys(created))('rejects missing %s', async (field) => {
    const value: Record<string, unknown> = { ...created }; delete value[field]
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(value), { status: 201 }))
    await expect(createStudent(body, 'key')).rejects.toBeInstanceOf(ApiResponseError)
  })
  it.each([{ version: '1' }, { version: true }, { version: 2 }, { version: 1.5 }, { status: 'INACTIVE' }, { studentId: 'invalid' }, { createdAt: 'invalid' }, { updatedAt: '2026-09-07T10:28:53.080Z' }, { birthDate: '2000-02-30' }, { phone: 123 }])('rejects invalid public values', async (change) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ ...created, ...change }), { status: 201 }))
    await expect(createStudent(body, 'key')).rejects.toBeInstanceOf(ApiResponseError)
  })
  it('rejects a 200 even with a valid body', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(created), { status: 200 }))
    await expect(createStudent(body, 'key')).rejects.toMatchObject({ status: 200 })
  })
  it('preserves status for malformed JSON', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('invalid', { status: 201 }))
    await expect(createStudent(body, 'key')).rejects.toMatchObject({ status: 201 })
  })
  it('extracts only the error code and status', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ code: 'IDEMPOTENCY_KEY_REUSED', message: 'sensitive' }), { status: 409 }))
    await expect(createStudent(body, 'key')).rejects.toMatchObject({ status: 409, code: 'IDEMPOTENCY_KEY_REUSED', message: 'API request failed with status 409' })
  })
})
