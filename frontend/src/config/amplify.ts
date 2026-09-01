import { Amplify } from 'aws-amplify'

import { env } from './env'

export function configureAmplify(): void {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: env.cognitoUserPoolId,
        userPoolClientId: env.cognitoUserPoolClientId,
        loginWith: {
          email: true,
        },
      },
    },
  })
}
