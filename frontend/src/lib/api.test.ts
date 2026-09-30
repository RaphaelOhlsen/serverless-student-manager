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
  createUser,
  deactivateStudent,
  fetchStudent,
  updateStudent,
  authenticatedPost,
  fetchCurrentUserProfile,
  fetchStudents,
  fetchUser,
  fetchUsers,
  reactivateStudent,
  resendUserInvitation,
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

  it.each(['ACTIVE', 'INACTIVE', 'ALL'] as const)(
    'sends the %s status filter to the students list',
    async (status) => {
      const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(JSON.stringify(studentsPage), { status: 200 }),
      )
      await fetchStudents(status)
      expect(fetchMock).toHaveBeenCalledWith(
        `https://api.example.test/students?status=${status}`,
        { method: 'GET', headers: { Authorization: 'Bearer fake-access-token' } },
      )
    },
  )

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

describe('users directory contract', () => {
  const user = {
    userId: '00000000-0000-4000-8000-000000000001',
    fullName: 'Admin Exemplo',
    email: 'admin@example.test',
    role: 'ADMIN',
    status: 'ACTIVE',
    version: 3,
    createdAt: '2026-09-01T10:00:00.000Z',
    updatedAt: '2026-09-02T10:00:00.000Z',
  }
  const page = { items: [user], nextCursor: 'opaque+/=cursor' }

  beforeEach(() => authMocks.fetchAuthSession.mockResolvedValue({
    tokens: { accessToken: { toString: () => 'fake-access-token' } },
  }))
  afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks() })

  it('gets users without filters using the access token', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(page), { status: 200 }),
    )
    await expect(fetchUsers()).resolves.toEqual(page)
    expect(fetchMock).toHaveBeenCalledWith('https://api.example.test/users', {
      method: 'GET', headers: { Authorization: 'Bearer fake-access-token' },
    })
  })

  it.each([
    [{ namePrefix: 'Ana Maria' }, 'namePrefix=Ana+Maria'],
    [{ email: 'admin+qa@example.test' }, 'email=admin%2Bqa%40example.test'],
    [{ role: 'ADMIN' }, 'role=ADMIN'],
    [{ status: 'INVITED' }, 'status=INVITED'],
    [{ limit: 100 }, 'limit=100'],
  ] as const)('serializes %o as %s', async (query, expected) => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(page), { status: 200 }),
    )
    await fetchUsers(query)
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`https://api.example.test/users?${expected}`)
  })

  it('serializes valid combinations and omits ALL filters', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(page), { status: 200 }),
    )
    await fetchUsers({ limit: 20, namePrefix: 'Ana', role: 'ALL', status: 'INACTIVE' })
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      'https://api.example.test/users?limit=20&namePrefix=Ana&status=INACTIVE',
    )
  })

  it('preserves an opaque cursor byte-for-byte through URL encoding', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(page), { status: 200 }),
    )
    await fetchUsers({ cursor: 'opaque+/=cursor' })
    const url = new URL(String(fetchMock.mock.calls[0]?.[0]))
    expect(url.searchParams.get('cursor')).toBe('opaque+/=cursor')
  })

  it.each([
    { limit: 0 }, { limit: 101 }, { limit: 1.5 }, { cursor: '' },
    { namePrefix: 'Ana', email: 'ana@example.test' },
  ])('rejects an invalid local query without an HTTP request: %o', async (query) => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    await expect(fetchUsers(query)).rejects.toBeInstanceOf(TypeError)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it.each([
    { userId: '' }, { role: 'OWNER' }, { status: 'DISABLED' }, { version: '3' },
    { createdAt: 'invalid' }, { updatedAt: '2026-08-01T10:00:00.000Z' },
  ])('rejects a malformed user: %o', async (change) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      ...page, items: [{ ...user, ...change }],
    }), { status: 200 }))
    await expect(fetchUsers()).rejects.toBeInstanceOf(ApiResponseError)
  })

  it.each(['PK', 'SK', 'authVersion', 'cognitoSub'])('rejects internal user field %s', async (field) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      ...page, items: [{ ...user, [field]: 'internal' }],
    }), { status: 200 }))
    await expect(fetchUsers()).rejects.toBeInstanceOf(ApiResponseError)
  })

  it.each([
    { items: 'invalid', nextCursor: null },
    { items: [], nextCursor: 42 },
    { items: [], nextCursor: null, internal: true },
  ])('rejects a malformed page: %o', async (malformed) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(malformed), { status: 200 }),
    )
    await expect(fetchUsers()).rejects.toBeInstanceOf(ApiResponseError)
  })

  it('sanitizes an API error to status and code', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      code: 'INVALID_REQUEST', message: 'sensitive backend detail',
    }), { status: 400 }))
    await expect(fetchUsers()).rejects.toMatchObject({
      status: 400, code: 'INVALID_REQUEST', message: 'API request failed with status 400',
    })
  })
})

describe('user detail contract', () => {
  const userId = '00000000-0000-4000-8000-000000000001'
  const detail = {
    userId,
    fullName: 'Admin Exemplo',
    email: 'admin@example.test',
    role: 'ADMIN',
    status: 'ACTIVE',
    version: 3,
    createdAt: '2026-09-01T10:00:00.000Z',
    updatedAt: '2026-09-02T10:00:00.000Z',
  }

  beforeEach(() => authMocks.fetchAuthSession.mockResolvedValue({
    tokens: { accessToken: { toString: () => 'fake-access-token' } },
  }))
  afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks() })

  it('gets the encoded user id with authentication and validates the public shape', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(detail), { status: 200 }),
    )

    await expect(fetchUser(`${userId}/segment`)).resolves.toEqual(detail)
    expect(fetchMock).toHaveBeenCalledWith(
      `https://api.example.test/users/${encodeURIComponent(`${userId}/segment`)}`,
      { method: 'GET', headers: { Authorization: 'Bearer fake-access-token' } },
    )
  })

  it('returns a valid public detail', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(detail), { status: 200 }),
    )
    await expect(fetchUser(userId)).resolves.toEqual(detail)
  })

  it.each(['PK', 'SK', 'cognitoSub', 'authVersion', 'normalizedName'])(
    'rejects internal detail field %s',
    async (field) => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
        ...detail, [field]: 'internal',
      }), { status: 200 }))
      await expect(fetchUser(userId)).rejects.toBeInstanceOf(ApiResponseError)
    },
  )

  it('preserves only public error status and code', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      error: 'USER_NOT_FOUND', message: 'sensitive backend detail',
    }), { status: 404 }))
    await expect(fetchUser(userId)).rejects.toMatchObject({
      status: 404,
      code: 'USER_NOT_FOUND',
      message: 'API request failed with status 404',
    })
  })
})

describe('create user contract', () => {
  const body = { fullName: 'Operador Exemplo', email: 'operator@example.test', role: 'OPERATOR' } as const
  const created = {
    ...body,
    userId: '00000000-0000-4000-8000-000000000010',
    status: 'INVITED',
    version: 1,
    createdAt: '2026-09-30T10:00:00.000Z',
    updatedAt: '2026-09-30T10:00:00.000Z',
  }

  beforeEach(() => authMocks.fetchAuthSession.mockResolvedValue({
    tokens: { accessToken: { toString: () => 'fake-access-token' } },
  }))
  afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks() })

  it('posts exact body with authentication and idempotency and accepts strict 201', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(created), { status: 201 }),
    )
    await expect(createUser(
      body,
      '00000000-0000-4000-8000-000000000011',
    )).resolves.toEqual(created)
    expect(fetchMock).toHaveBeenCalledWith('https://api.example.test/users', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer fake-access-token',
        'Content-Type': 'application/json',
        'Idempotency-Key': '00000000-0000-4000-8000-000000000011',
      },
      body: JSON.stringify(body),
    })
  })

  it.each([
    { status: 'ACTIVE' }, { status: 'INACTIVE' }, { version: 2 }, { version: '1' },
    { updatedAt: '2026-09-30T10:00:01.000Z' }, { userId: 'invalid' },
  ])('rejects a non-INVITED/version-1 creation response: %o', async (change) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      ...created, ...change,
    }), { status: 201 }))
    await expect(createUser(body, 'key')).rejects.toBeInstanceOf(ApiResponseError)
  })

  it.each(['PK', 'SK', 'authVersion', 'cognitoSub', 'normalizedName'])(
    'rejects internal response field %s',
    async (field) => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
        ...created, [field]: 'internal',
      }), { status: 201 }))
      await expect(createUser(body, 'key')).rejects.toBeInstanceOf(ApiResponseError)
    },
  )

  it.each([
    ['error', 'EMAIL_ALREADY_EXISTS'],
    ['code', 'OPERATION_IN_PROGRESS'],
  ] as const)('accepts public error code from %s without exposing message', async (field, code) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      [field]: code, message: 'sensitive backend detail',
    }), { status: 409 }))
    await expect(createUser(body, 'key')).rejects.toMatchObject({
      status: 409, code, message: 'API request failed with status 409',
    })
  })

  it('rejects malformed JSON and non-201 success status', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('not-json', { status: 201 }))
    await expect(createUser(body, 'key')).rejects.toMatchObject({ status: 201 })
    vi.restoreAllMocks()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(created), { status: 200 }),
    )
    await expect(createUser(body, 'key')).rejects.toMatchObject({ status: 200 })
  })
})

describe('resend user invitation contract', () => {
  const userId = '00000000-0000-4000-8000-000000000010'
  const body = { expectedVersion: 3 }
  const key = '00000000-0000-4000-8000-000000000011'

  beforeEach(() => authMocks.fetchAuthSession.mockResolvedValue({
    tokens: { accessToken: { toString: () => 'fake-access-token' } },
  }))
  afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks() })

  it('posts the expected version with authentication and idempotency and requires 204', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(null, { status: 204 }),
    )

    await expect(resendUserInvitation(userId, body, key)).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledWith(
      `https://api.example.test/users/${userId}/invitation/resend`,
      {
        method: 'POST',
        headers: {
          Authorization: 'Bearer fake-access-token',
          'Content-Type': 'application/json',
          'Idempotency-Key': key,
        },
        body: JSON.stringify(body),
      },
    )
  })

  it('rejects a non-204 success response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 200 }))
    await expect(resendUserInvitation(userId, body, key)).rejects.toMatchObject({
      status: 200,
      message: 'API request failed with status 200',
    })
  })

  it.each([
    ['error', 'INVITATION_DELIVERY_FAILED'],
    ['code', 'INVITATION_DELIVERY_UNCERTAIN'],
  ] as const)('accepts public error code from %s without exposing message', async (field, code) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      [field]: code, message: 'sensitive backend detail',
    }), { status: 503 }))
    await expect(resendUserInvitation(userId, body, key)).rejects.toMatchObject({
      status: 503, code, message: 'API request failed with status 503',
    })
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

describe('update student contract', () => {
  const detail = {
    fullName: 'Aluno Teste', registrationNumber: 'MAT-001',
    studentEmail: 'a@example.com', phone: '+15555550123', birthDate: '2000-01-15',
    studentId: '00000000-0000-4000-8000-000000000100', status: 'INACTIVE', version: 3,
    createdAt: '2026-09-06T10:28:53.080Z', updatedAt: '2026-09-07T10:28:53.080Z',
  }
  beforeEach(() => authMocks.fetchAuthSession.mockResolvedValue({
    tokens: { accessToken: { toString: () => 'fake-access-token' } },
  }))
  afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks() })

  it('gets and validates the full student detail before editing', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(detail), { status: 200 }),
    )
    await expect(fetchStudent(detail.studentId)).resolves.toEqual(detail)
    expect(fetchMock).toHaveBeenCalledWith(
      `https://api.example.test/students/${detail.studentId}`,
      { method: 'GET', headers: { Authorization: 'Bearer fake-access-token' } },
    )
  })

  it('patches only the supplied fields with access token and idempotency key', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ...detail, fullName: 'Novo Nome', version: 4 }), { status: 200 }),
    )
    const request = { expectedVersion: 3, fullName: 'Novo Nome' }
    await updateStudent(detail.studentId, request, '00000000-0000-4000-8000-000000000001')
    expect(fetchMock).toHaveBeenCalledWith(
      `https://api.example.test/students/${detail.studentId}`,
      {
        method: 'PATCH',
        headers: {
          Authorization: 'Bearer fake-access-token',
          'Content-Type': 'application/json',
          'Idempotency-Key': '00000000-0000-4000-8000-000000000001',
        },
        body: JSON.stringify(request),
      },
    )
  })

  it('preserves canonical update error status and code', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      code: 'STUDENT_VERSION_CONFLICT', message: 'not exposed',
    }), { status: 409 }))
    await expect(updateStudent(detail.studentId, {
      expectedVersion: 3, fullName: 'Novo Nome',
    }, 'key')).rejects.toMatchObject({ status: 409, code: 'STUDENT_VERSION_CONFLICT' })
  })

  it('rejects incomplete or internally extended detail responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(JSON.stringify({
      ...detail, version: '3',
    }), { status: 200 })).mockResolvedValueOnce(new Response(JSON.stringify({
      ...detail, updatedBy: 'internal',
    }), { status: 200 }))
    await expect(fetchStudent(detail.studentId)).rejects.toBeInstanceOf(ApiResponseError)
    await expect(fetchStudent(detail.studentId)).rejects.toBeInstanceOf(ApiResponseError)
  })
})

describe('student lifecycle contract', () => {
  const detail = {
    fullName: 'Aluno Sintético', registrationNumber: 'MAT-001',
    studentEmail: 'student@example.invalid', phone: '+15555550123', birthDate: '2000-01-15',
    studentId: '00000000-0000-4000-8000-000000000100', status: 'ACTIVE' as const, version: 3,
    createdAt: '2026-09-06T10:28:53.080Z', updatedAt: '2026-09-07T10:28:53.080Z',
  }
  beforeEach(() => authMocks.fetchAuthSession.mockResolvedValue({
    tokens: { accessToken: { toString: () => 'fake-access-token' } },
  }))
  afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks() })

  it('posts deactivation with auth, JSON and idempotency headers', async () => {
    const updated = { ...detail, status: 'INACTIVE', version: 4 }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(updated), { status: 200 }),
    )
    const body = { expectedVersion: 3, reason: 'Motivo sintético' }
    await expect(deactivateStudent(detail.studentId, body, '00000000-0000-4000-8000-000000000003'))
      .resolves.toEqual(updated)
    expect(fetchMock).toHaveBeenCalledWith(
      `https://api.example.test/students/${detail.studentId}/deactivation`,
      {
        method: 'POST',
        headers: {
          Authorization: 'Bearer fake-access-token',
          'Content-Type': 'application/json',
          'Idempotency-Key': '00000000-0000-4000-8000-000000000003',
        },
        body: JSON.stringify(body),
      },
    )
  })

  it('posts reactivation with only expectedVersion', async () => {
    const inactive = { ...detail, status: 'INACTIVE' as const }
    const updated = { ...detail, version: 4 }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(updated), { status: 200 }),
    )
    const body = { expectedVersion: inactive.version }
    await expect(reactivateStudent(inactive.studentId, body, '00000000-0000-4000-8000-000000000004'))
      .resolves.toEqual(updated)
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify(body),
    })
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `https://api.example.test/students/${inactive.studentId}/reactivation`,
    )
  })

  it('preserves lifecycle error status and code without its message', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      code: 'STUDENT_VERSION_CONFLICT', message: 'not exposed',
    }), { status: 409 }))
    await expect(reactivateStudent(detail.studentId, { expectedVersion: 3 }, 'key'))
      .rejects.toMatchObject({
        status: 409,
        code: 'STUDENT_VERSION_CONFLICT',
        message: 'API request failed with status 409',
      })
  })
})
