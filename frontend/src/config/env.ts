function requireEnv(name: string, value: string | undefined): string {
  const normalizedValue = value?.trim()

  if (!normalizedValue) {
    throw new Error(`Missing required environment variable: ${name}`)
  }

  return normalizedValue
}

export const env = {
  cognitoUserPoolId: requireEnv(
    'VITE_COGNITO_USER_POOL_ID',
    import.meta.env.VITE_COGNITO_USER_POOL_ID,
  ),
  cognitoUserPoolClientId: requireEnv(
    'VITE_COGNITO_USER_POOL_CLIENT_ID',
    import.meta.env.VITE_COGNITO_USER_POOL_CLIENT_ID,
  ),
} as const
