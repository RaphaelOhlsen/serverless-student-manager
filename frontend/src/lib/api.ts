import { fetchAuthSession } from 'aws-amplify/auth'

import { env } from '@/config/env'

export class AuthSessionUnavailableError extends Error {
  constructor() {
    super('Authenticated session is unavailable')
    this.name = 'AuthSessionUnavailableError'
  }
}

export type UserProfile = {
  userId: string
  fullName: string
  email: string
  role: 'ADMIN' | 'OPERATOR'
  status: 'INVITED' | 'ACTIVE'
  authVersion: number
}

export type StudentSummary = {
  studentId: string
  registrationNumber: string
  fullName: string
  status: 'ACTIVE' | 'INACTIVE'
}

export type StudentsPage = {
  items: StudentSummary[]
  nextCursor: string | null
  hasMore: boolean
}

export class ApiResponseError extends Error {
  readonly status: number

  constructor(status: number) {
    super(`API request failed with status ${status}`)
    this.name = 'ApiResponseError'
    this.status = status
  }
}

async function getAccessToken(): Promise<string> {
  let accessToken: string | undefined

  try {
    const session = await fetchAuthSession()
    accessToken = session.tokens?.accessToken.toString()
  } catch {
    throw new AuthSessionUnavailableError()
  }

  if (!accessToken) {
    throw new AuthSessionUnavailableError()
  }

  return accessToken
}

function apiUrl(path: string): string {
  const baseUrl = env.apiBaseUrl.replace(/\/+$/, '')

  return `${baseUrl}/${path.replace(/^\/+/, '')}`
}

export async function authenticatedGet(path: string): Promise<Response> {
  const accessToken = await getAccessToken()

  return fetch(apiUrl(path), {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })
}

export async function authenticatedPost(
  path: string,
  idempotencyKey: string,
): Promise<Response> {
  const accessToken = await getAccessToken()

  return fetch(apiUrl(path), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Idempotency-Key': idempotencyKey,
    },
  })
}

export async function fetchCurrentUserProfile(): Promise<UserProfile> {
  const response = await authenticatedGet('/users/me')
  if (!response.ok) {
    throw new ApiResponseError(response.status)
  }

  const value: unknown = await response.json()
  if (!isUserProfile(value)) {
    throw new ApiResponseError(response.status)
  }

  return value
}

export async function fetchStudents(): Promise<StudentsPage> {
  const response = await authenticatedGet('/students')
  if (!response.ok) {
    throw new ApiResponseError(response.status)
  }

  const value: unknown = await response.json()
  if (!isStudentsPage(value)) {
    throw new ApiResponseError(response.status)
  }

  return value
}

function isUserProfile(value: unknown): value is UserProfile {
  if (!isRecord(value)) {
    return false
  }

  return (
    isNonEmptyString(value.userId) &&
    isNonEmptyString(value.fullName) &&
    isNonEmptyString(value.email) &&
    (value.role === 'ADMIN' || value.role === 'OPERATOR') &&
    (value.status === 'INVITED' || value.status === 'ACTIVE') &&
    typeof value.authVersion === 'number' &&
    Number.isInteger(value.authVersion) &&
    value.authVersion >= 1
  )
}

function isStudentsPage(value: unknown): value is StudentsPage {
  return (
    isRecord(value) &&
    Array.isArray(value.items) &&
    value.items.every(isStudentSummary) &&
    (value.nextCursor === null || typeof value.nextCursor === 'string') &&
    typeof value.hasMore === 'boolean'
  )
}

function isStudentSummary(value: unknown): value is StudentSummary {
  return (
    isRecord(value) &&
    isNonEmptyString(value.studentId) &&
    isNonEmptyString(value.registrationNumber) &&
    isNonEmptyString(value.fullName) &&
    (value.status === 'ACTIVE' || value.status === 'INACTIVE')
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
}
