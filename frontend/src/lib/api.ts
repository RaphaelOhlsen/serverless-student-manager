import { fetchAuthSession } from 'aws-amplify/auth'

import { env } from '@/config/env'

export class AuthSessionUnavailableError extends Error {
  constructor() {
    super('Authenticated session is unavailable')
    this.name = 'AuthSessionUnavailableError'
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
