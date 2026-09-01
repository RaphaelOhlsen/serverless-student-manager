import { fetchAuthSession } from 'aws-amplify/auth'

import { env } from '@/config/env'

export class AuthSessionUnavailableError extends Error {
  constructor() {
    super('Authenticated session is unavailable')
    this.name = 'AuthSessionUnavailableError'
  }
}

export async function authenticatedGet(path: string): Promise<Response> {
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

  const baseUrl = env.apiBaseUrl.replace(/\/+$/, '')

  return fetch(`${baseUrl}/${path.replace(/^\/+/, '')}`, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })
}
