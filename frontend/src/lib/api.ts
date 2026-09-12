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

export type StudentStatusFilter = 'ACTIVE' | 'INACTIVE' | 'ALL'

export class ApiResponseError extends Error {
  readonly status: number
  readonly code?: string

  constructor(status: number, code?: string) {
    super(`API request failed with status ${status}`)
    this.name = 'ApiResponseError'
    this.status = status
    this.code = code
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
  body?: object,
): Promise<Response> {
  const accessToken = await getAccessToken()

  return fetch(apiUrl(path), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Idempotency-Key': idempotencyKey,
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  })
}

export async function authenticatedPatch(
  path: string,
  idempotencyKey: string,
  body: UpdateStudentRequest,
): Promise<Response> {
  const accessToken = await getAccessToken()

  return fetch(apiUrl(path), {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
      'Idempotency-Key': idempotencyKey,
    },
    body: JSON.stringify(body),
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

export async function fetchStudents(
  status?: StudentStatusFilter,
): Promise<StudentsPage> {
  const response = await authenticatedGet(
    status ? `/students?status=${encodeURIComponent(status)}` : '/students',
  )
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

export type CreateStudentRequest = {
  fullName: string
  registrationNumber: string
  studentEmail: string
  phone: string
  birthDate: string
}

export type CreatedStudent = CreateStudentRequest & {
  studentId: string
  status: 'ACTIVE'
  version: number
  createdAt: string
  updatedAt: string
}

export type StudentDetail = CreateStudentRequest & {
  studentId: string
  status: 'ACTIVE' | 'INACTIVE'
  version: number
  createdAt: string
  updatedAt: string
}

export type UpdateStudentRequest = {
  expectedVersion: number
  fullName?: string
  studentEmail?: string
  phone?: string
  birthDate?: string
}

export type DeactivateStudentRequest = {
  expectedVersion: number
  reason: string
}

export type ReactivateStudentRequest = {
  expectedVersion: number
}

export async function createStudent(
  body: CreateStudentRequest,
  idempotencyKey: string,
): Promise<CreatedStudent> {
  const response = await authenticatedPost('/students', idempotencyKey, body)
  let value: unknown
  try {
    value = await response.json()
  } catch {
    throw new ApiResponseError(response.status)
  }
  if (response.status !== 201 || !isCreatedStudent(value)) {
    throw new ApiResponseError(
      response.status,
      response.status !== 201 && isRecord(value) && typeof value.code === 'string'
        ? value.code : undefined,
    )
  }
  return value
}

export async function fetchStudent(studentId: string): Promise<StudentDetail> {
  const response = await authenticatedGet(`/students/${encodeURIComponent(studentId)}`)
  let value: unknown
  try {
    value = await response.json()
  } catch {
    throw new ApiResponseError(response.status)
  }
  if (!response.ok || !isStudentDetail(value)) {
    throw new ApiResponseError(
      response.status,
      !response.ok && isRecord(value) && typeof value.code === 'string'
        ? value.code
        : undefined,
    )
  }
  return value
}

export async function updateStudent(
  studentId: string,
  body: UpdateStudentRequest,
  idempotencyKey: string,
): Promise<StudentDetail> {
  const response = await authenticatedPatch(
    `/students/${encodeURIComponent(studentId)}`,
    idempotencyKey,
    body,
  )
  let value: unknown
  try {
    value = await response.json()
  } catch {
    throw new ApiResponseError(response.status)
  }
  if (response.status !== 200 || !isStudentDetail(value)) {
    throw new ApiResponseError(
      response.status,
      response.status !== 200 && isRecord(value) && typeof value.code === 'string'
        ? value.code
        : undefined,
    )
  }
  return value
}

async function lifecycleStudentRequest(
  path: string,
  body: DeactivateStudentRequest | ReactivateStudentRequest,
  idempotencyKey: string,
): Promise<StudentDetail> {
  const response = await authenticatedPost(path, idempotencyKey, body)
  let value: unknown
  try {
    value = await response.json()
  } catch {
    throw new ApiResponseError(response.status)
  }
  if (response.status !== 200 || !isStudentDetail(value)) {
    throw new ApiResponseError(
      response.status,
      response.status !== 200 && isRecord(value) && typeof value.code === 'string'
        ? value.code
        : undefined,
    )
  }
  return value
}

export function deactivateStudent(
  studentId: string,
  body: DeactivateStudentRequest,
  idempotencyKey: string,
): Promise<StudentDetail> {
  return lifecycleStudentRequest(
    `/students/${encodeURIComponent(studentId)}/deactivation`,
    body,
    idempotencyKey,
  )
}

export function reactivateStudent(
  studentId: string,
  body: ReactivateStudentRequest,
  idempotencyKey: string,
): Promise<StudentDetail> {
  return lifecycleStudentRequest(
    `/students/${encodeURIComponent(studentId)}/reactivation`,
    body,
    idempotencyKey,
  )
}

function isCreatedStudent(value: unknown): value is CreatedStudent {
  return isStudentDetail(value) && value.status === 'ACTIVE' &&
    value.version === 1 && value.updatedAt === value.createdAt
}

function isStudentDetail(value: unknown): value is StudentDetail {
  const fields = ['studentId', 'registrationNumber', 'fullName', 'studentEmail',
    'phone', 'birthDate', 'status', 'version', 'createdAt', 'updatedAt']
  if (!isRecord(value) || Object.keys(value).length !== fields.length ||
      !fields.every((field) => Object.hasOwn(value, field))) return false
  const strings = fields.filter((field) => field !== 'version')
  if (!strings.every((field) => isNonEmptyString(value[field]))) return false
  return typeof value.studentId === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value.studentId) &&
    (value.status === 'ACTIVE' || value.status === 'INACTIVE') &&
    typeof value.version === 'number' && Number.isInteger(value.version) && value.version >= 1 &&
    isTimestamp(value.createdAt) && isTimestamp(value.updatedAt) &&
    value.updatedAt >= value.createdAt && typeof value.birthDate === 'string' &&
    /^\d{4}-\d{2}-\d{2}$/.test(value.birthDate) && value.birthDate >= '0001-01-01' &&
    Number.isFinite(Date.parse(value.birthDate + 'T00:00:00.000Z')) &&
    new Date(value.birthDate + 'T00:00:00.000Z').toISOString().slice(0, 10) === value.birthDate
}

function isTimestamp(value: unknown): value is string {
  return typeof value === 'string' &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value) &&
    Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value
}
