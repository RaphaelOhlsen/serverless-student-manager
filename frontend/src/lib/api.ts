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

export type AdminUser = {
  userId: string
  fullName: string
  email: string
  role: 'ADMIN' | 'OPERATOR'
  status: 'INVITED' | 'ACTIVE' | 'INACTIVE'
  version: number
  createdAt: string
  updatedAt: string
}

export type UsersPage = {
  items: AdminUser[]
  nextCursor: string | null
}

export type UserRoleFilter = 'ALL' | AdminUser['role']
export type UserStatusFilter = 'ALL' | AdminUser['status']

export type UsersQuery = {
  limit?: number
  cursor?: string
  namePrefix?: string
  email?: string
  role?: UserRoleFilter
  status?: UserStatusFilter
}

export type AuditEvent = {
  eventId: string
  eventType: string
  resourceType: 'STUDENT' | 'USER'
  resourceId: string
  actorId: string
  occurredAt: string
  result: 'SUCCESS' | 'FAILURE'
  correlationId: string
}

export type AuditPage = {
  items: AuditEvent[]
  nextCursor: string | null
}

export type AuditQuery = {
  from: string
  to: string
  resourceType?: AuditEvent['resourceType']
  resourceId?: string
  eventType?: string
  actorId?: string
  result?: AuditEvent['result']
  correlationId?: string
  limit?: number
  cursor?: string
}

export type CreateUserRequest = {
  fullName: string
  email: string
  role: AdminUser['role']
}

export type ResendInvitationRequest = {
  expectedVersion: number
}

export type ChangeUserRoleRequest = {
  expectedVersion: number
  role: AdminUser['role']
}

export type UserLifecycleRequest = {
  expectedVersion: number
}

export type CreatedAdminUser = Omit<AdminUser, 'status' | 'version'> & {
  status: 'INVITED'
  version: 1
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

export async function fetchUsers(query: UsersQuery = {}): Promise<UsersPage> {
  if (query.limit !== undefined &&
      (!Number.isInteger(query.limit) || query.limit < 1 || query.limit > 100)) {
    throw new TypeError('Invalid users limit')
  }
  if (query.namePrefix !== undefined && query.email !== undefined) {
    throw new TypeError('User name and email searches are mutually exclusive')
  }
  if (query.cursor === '') throw new TypeError('Invalid users cursor')
  const parameters = new URLSearchParams()
  if (query.limit !== undefined) parameters.set('limit', String(query.limit))
  if (query.cursor !== undefined) parameters.set('cursor', query.cursor)
  if (query.namePrefix !== undefined) parameters.set('namePrefix', query.namePrefix)
  if (query.email !== undefined) parameters.set('email', query.email)
  if (query.role !== undefined && query.role !== 'ALL') parameters.set('role', query.role)
  if (query.status !== undefined && query.status !== 'ALL') parameters.set('status', query.status)
  const queryString = parameters.toString()
  const response = await authenticatedGet(`/users${queryString ? `?${queryString}` : ''}`)
  let value: unknown
  try {
    value = await response.json()
  } catch {
    throw new ApiResponseError(response.status)
  }
  if (!response.ok || !isUsersPage(value)) {
    throw new ApiResponseError(
      response.status,
      !response.ok ? publicErrorCode(value) : undefined,
    )
  }
  return value
}

export async function fetchAuditEvents(query: AuditQuery): Promise<AuditPage> {
  validateAuditQuery(query)
  const parameters = new URLSearchParams()
  parameters.set('from', query.from)
  parameters.set('to', query.to)
  if (query.resourceType !== undefined) parameters.set('resourceType', query.resourceType)
  if (query.resourceId !== undefined) parameters.set('resourceId', query.resourceId)
  if (query.eventType !== undefined) parameters.set('eventType', query.eventType)
  if (query.actorId !== undefined) parameters.set('actorId', query.actorId)
  if (query.result !== undefined) parameters.set('result', query.result)
  if (query.correlationId !== undefined) parameters.set('correlationId', query.correlationId)
  if (query.limit !== undefined) parameters.set('limit', String(query.limit))
  if (query.cursor !== undefined) parameters.set('cursor', query.cursor)

  const response = await authenticatedGet(`/audit-events?${parameters.toString()}`)
  let value: unknown
  try {
    value = await response.json()
  } catch {
    throw new ApiResponseError(response.status)
  }
  if (!response.ok || !isAuditPage(value)) {
    throw new ApiResponseError(
      response.status,
      !response.ok ? publicErrorCode(value) : undefined,
    )
  }
  return value
}

export async function fetchUser(userId: string): Promise<AdminUser> {
  const response = await authenticatedGet(`/users/${encodeURIComponent(userId)}`)
  let value: unknown
  try {
    value = await response.json()
  } catch {
    throw new ApiResponseError(response.status)
  }
  if (!response.ok || !isAdminUser(value)) {
    throw new ApiResponseError(
      response.status,
      !response.ok ? publicErrorCode(value) : undefined,
    )
  }
  return value
}

export async function createUser(
  body: CreateUserRequest,
  idempotencyKey: string,
): Promise<CreatedAdminUser> {
  const response = await authenticatedPost('/users', idempotencyKey, body)
  let value: unknown
  try {
    value = await response.json()
  } catch {
    throw new ApiResponseError(response.status)
  }
  if (response.status !== 201 || !isCreatedAdminUser(value)) {
    throw new ApiResponseError(
      response.status,
      response.status !== 201 ? publicErrorCode(value) : undefined,
    )
  }
  return value
}

export async function resendUserInvitation(
  userId: string,
  body: ResendInvitationRequest,
  idempotencyKey: string,
): Promise<void> {
  const response = await authenticatedPost(
    `/users/${encodeURIComponent(userId)}/invitation/resend`,
    idempotencyKey,
    body,
  )
  if (response.status === 204) return

  let value: unknown
  try {
    value = await response.json()
  } catch {
    value = undefined
  }
  throw new ApiResponseError(response.status, publicErrorCode(value))
}

export async function changeUserRole(
  userId: string,
  body: ChangeUserRoleRequest,
  idempotencyKey: string,
): Promise<AdminUser> {
  const response = await authenticatedPost(
    `/users/${encodeURIComponent(userId)}/role-change`,
    idempotencyKey,
    body,
  )
  let value: unknown
  try {
    value = await response.json()
  } catch {
    throw new ApiResponseError(response.status)
  }
  if (response.status !== 200 || !isAdminUser(value)) {
    throw new ApiResponseError(
      response.status,
      response.status !== 200 ? publicErrorCode(value) : undefined,
    )
  }
  return value
}

async function changeUserLifecycle(
  userId: string,
  action: 'deactivation' | 'reactivation',
  body: UserLifecycleRequest,
  idempotencyKey: string,
): Promise<AdminUser> {
  const response = await authenticatedPost(
    `/users/${encodeURIComponent(userId)}/${action}`,
    idempotencyKey,
    body,
  )
  let value: unknown
  try {
    value = await response.json()
  } catch {
    throw new ApiResponseError(response.status)
  }
  if (response.status !== 200 || !isAdminUser(value)) {
    throw new ApiResponseError(
      response.status,
      response.status !== 200 ? publicErrorCode(value) : undefined,
    )
  }
  return value
}

export function deactivateUser(
  userId: string,
  body: UserLifecycleRequest,
  idempotencyKey: string,
): Promise<AdminUser> {
  return changeUserLifecycle(userId, 'deactivation', body, idempotencyKey)
}

export function reactivateUser(
  userId: string,
  body: UserLifecycleRequest,
  idempotencyKey: string,
): Promise<AdminUser> {
  return changeUserLifecycle(userId, 'reactivation', body, idempotencyKey)
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

function isUsersPage(value: unknown): value is UsersPage {
  return isExactRecord(value, ['items', 'nextCursor']) &&
    Array.isArray(value.items) && value.items.every(isAdminUser) &&
    (value.nextCursor === null || isNonEmptyString(value.nextCursor))
}

function isAuditPage(value: unknown): value is AuditPage {
  return isExactRecord(value, ['items', 'nextCursor']) &&
    Array.isArray(value.items) && value.items.every(isAuditEvent) &&
    (value.nextCursor === null || isNonEmptyString(value.nextCursor))
}

function isAuditEvent(value: unknown): value is AuditEvent {
  const fields = [
    'eventId', 'eventType', 'resourceType', 'resourceId', 'actorId',
    'occurredAt', 'result', 'correlationId',
  ]
  return isExactRecord(value, fields) &&
    isExactAuditValue(value.eventId) &&
    isExactAuditValue(value.eventType) &&
    (value.resourceType === 'STUDENT' || value.resourceType === 'USER') &&
    isExactAuditValue(value.resourceId) &&
    isExactAuditValue(value.actorId) &&
    isTimestamp(value.occurredAt) &&
    (value.result === 'SUCCESS' || value.result === 'FAILURE') &&
    isExactAuditValue(value.correlationId)
}

function validateAuditQuery(query: AuditQuery): void {
  if (!isCanonicalAuditTimestamp(query.from) || !isCanonicalAuditTimestamp(query.to)) {
    throw new TypeError('Invalid audit date range')
  }
  const from = Date.parse(query.from)
  const to = Date.parse(query.to)
  if (from > to || to - from > 366 * 24 * 60 * 60 * 1000) {
    throw new TypeError('Invalid audit date range')
  }
  if (query.resourceType !== undefined &&
      query.resourceType !== 'STUDENT' && query.resourceType !== 'USER') {
    throw new TypeError('Invalid audit resource type')
  }
  if (query.resourceId !== undefined && query.resourceType === undefined) {
    throw new TypeError('Audit resource ID requires resource type')
  }
  if (query.result !== undefined && query.result !== 'SUCCESS' && query.result !== 'FAILURE') {
    throw new TypeError('Invalid audit result')
  }
  for (const value of [
    query.resourceId, query.eventType, query.actorId, query.correlationId,
  ]) {
    if (value !== undefined && !isExactAuditValue(value)) {
      throw new TypeError('Invalid exact audit filter')
    }
  }
  if (query.limit !== undefined &&
      (!Number.isInteger(query.limit) || query.limit < 1 || query.limit > 100)) {
    throw new TypeError('Invalid audit limit')
  }
  if (query.cursor === '') throw new TypeError('Invalid audit cursor')
}

function isCanonicalAuditTimestamp(value: unknown): value is string {
  if (typeof value !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(value) ||
      value.startsWith('0000-')) return false
  const normalized = value.includes('.') ? value : value.replace(/Z$/, '.000Z')
  return Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === normalized
}

function isExactAuditValue(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0 && value === value.trim() &&
    new TextEncoder().encode(value).length <= 512 && !/\p{C}/u.test(value)
}

function isAdminUser(value: unknown): value is AdminUser {
  const fields = [
    'userId', 'fullName', 'email', 'role', 'status', 'version', 'createdAt', 'updatedAt',
  ]
  return isExactRecord(value, fields) &&
    isNonEmptyString(value.userId) &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value.userId) &&
    isNonEmptyString(value.fullName) &&
    isNonEmptyString(value.email) &&
    (value.role === 'ADMIN' || value.role === 'OPERATOR') &&
    (value.status === 'INVITED' || value.status === 'ACTIVE' || value.status === 'INACTIVE') &&
    typeof value.version === 'number' && Number.isInteger(value.version) && value.version >= 1 &&
    isTimestamp(value.createdAt) && isTimestamp(value.updatedAt) &&
    value.updatedAt >= value.createdAt
}

function isCreatedAdminUser(value: unknown): value is CreatedAdminUser {
  return isAdminUser(value) && value.status === 'INVITED' && value.version === 1 &&
    value.updatedAt === value.createdAt
}

function isExactRecord(value: unknown, fields: string[]): value is Record<string, unknown> {
  return isRecord(value) && Object.keys(value).length === fields.length &&
    fields.every((field) => Object.hasOwn(value, field))
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function publicErrorCode(value: unknown): string | undefined {
  if (!isRecord(value)) return undefined
  if (typeof value.error === 'string') return value.error
  return typeof value.code === 'string' ? value.code : undefined
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
      response.status !== 201 ? publicErrorCode(value) : undefined,
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
      !response.ok ? publicErrorCode(value) : undefined,
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
      response.status !== 200 ? publicErrorCode(value) : undefined,
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
      response.status !== 200 ? publicErrorCode(value) : undefined,
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
