import { type FormEvent, useState } from 'react'
import { confirmSignIn, signIn } from 'aws-amplify/auth'

import { Button } from '@/components/ui/button'

import './App.css'

type AuthView =
  | 'sign-in'
  | 'new-password-required'
  | 'mfa-setup-selection'
  | 'totp-setup'
  | 'totp-challenge'
  | 'authenticated'
  | 'unsupported-step'

const GENERIC_SIGN_IN_ERROR =
  'Não foi possível entrar. Verifique seus dados e tente novamente.'
const GENERIC_NEW_PASSWORD_ERROR =
  'Não foi possível definir a nova senha. Revise os dados e tente novamente.'
const UNSUPPORTED_STEP_ERROR =
  'Não foi possível concluir o acesso nesta etapa. Tente novamente mais tarde.'

const nextStageContent: Partial<
  Record<AuthView, { eyebrow: string; title: string; description: string }>
> = {
  'mfa-setup-selection': {
    eyebrow: 'Verificação em duas etapas',
    title: 'Escolha do método de segurança necessária',
    description:
      'A próxima etapa será selecionar o método de autenticação adicional.',
  },
  'totp-setup': {
    eyebrow: 'Verificação em duas etapas',
    title: 'Configuração do autenticador necessária',
    description:
      'A próxima etapa será associar um aplicativo autenticador à sua conta.',
  },
  'totp-challenge': {
    eyebrow: 'Verificação em duas etapas',
    title: 'Código do autenticador necessário',
    description:
      'A próxima etapa será informar o código gerado pelo seu autenticador.',
  },
  authenticated: {
    eyebrow: 'Acesso confirmado',
    title: 'Autenticação concluída',
    description: 'Sua identidade foi autenticada com sucesso.',
  },
  'unsupported-step': {
    eyebrow: 'Acesso não concluído',
    title: 'Não foi possível continuar',
    description: UNSUPPORTED_STEP_ERROR,
  },
}

function App() {
  const [authView, setAuthView] = useState<AuthView>('sign-in')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newPasswordConfirmation, setNewPasswordConfirmation] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  function transitionFromSignInStep(signInStep: string) {
    setErrorMessage(null)

    switch (signInStep) {
      case 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED':
        setAuthView('new-password-required')
        break
      case 'CONTINUE_SIGN_IN_WITH_MFA_SETUP_SELECTION':
        setAuthView('mfa-setup-selection')
        break
      case 'CONTINUE_SIGN_IN_WITH_TOTP_SETUP':
        setAuthView('totp-setup')
        break
      case 'CONFIRM_SIGN_IN_WITH_TOTP_CODE':
        setAuthView('totp-challenge')
        break
      case 'DONE':
        setEmail('')
        setAuthView('authenticated')
        break
      default:
        setEmail('')
        setAuthView('unsupported-step')
    }
  }

  async function handleSignIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setErrorMessage(null)
    setIsLoading(true)

    try {
      const result = await signIn({
        username: email.trim(),
        password,
      })

      setPassword('')
      transitionFromSignInStep(result.nextStep.signInStep)
    } catch {
      setErrorMessage(GENERIC_SIGN_IN_ERROR)
    } finally {
      setIsLoading(false)
    }
  }

  async function handleConfirmNewPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setErrorMessage(null)

    if (!newPassword || !newPasswordConfirmation) {
      setErrorMessage('Preencha e confirme a nova senha.')
      return
    }

    if (newPassword !== newPasswordConfirmation) {
      setErrorMessage('A nova senha e a confirmação devem ser iguais.')
      return
    }

    setIsLoading(true)

    try {
      const result = await confirmSignIn({
        challengeResponse: newPassword,
      })

      setNewPassword('')
      setNewPasswordConfirmation('')
      transitionFromSignInStep(result.nextStep.signInStep)
    } catch {
      setErrorMessage(GENERIC_NEW_PASSWORD_ERROR)
    } finally {
      setIsLoading(false)
    }
  }

  if (authView === 'new-password-required') {
    return (
      <main className="auth-page">
        <section className="auth-card" aria-labelledby="new-password-title">
          <div className="auth-heading">
            <p className="auth-eyebrow">Primeiro acesso</p>
            <h1 id="new-password-title">Defina uma nova senha</h1>
            <p className="auth-description">
              Substitua a senha temporária para continuar o acesso.
            </p>
          </div>

          <form className="auth-form" onSubmit={handleConfirmNewPassword}>
            <div className="form-field">
              <label htmlFor="new-password">Nova senha</label>
              <input
                id="new-password"
                name="new-password"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                disabled={isLoading}
                required
              />
            </div>

            <div className="form-field">
              <label htmlFor="new-password-confirmation">
                Confirme a nova senha
              </label>
              <input
                id="new-password-confirmation"
                name="new-password-confirmation"
                type="password"
                autoComplete="new-password"
                value={newPasswordConfirmation}
                onChange={(event) =>
                  setNewPasswordConfirmation(event.target.value)
                }
                disabled={isLoading}
                required
              />
            </div>

            {errorMessage ? (
              <p className="auth-error" role="alert">
                {errorMessage}
              </p>
            ) : null}

            <Button className="auth-submit" type="submit" disabled={isLoading}>
              {isLoading ? 'Continuando…' : 'Continuar'}
            </Button>
          </form>
        </section>
      </main>
    )
  }

  if (authView !== 'sign-in') {
    const content = nextStageContent[authView]

    if (!content) {
      return null
    }

    return (
      <main className="auth-page">
        <section className="auth-card" aria-labelledby="next-stage-title">
          <p className="auth-eyebrow">{content.eyebrow}</p>
          <h1 id="next-stage-title">{content.title}</h1>
          <p className="auth-description">{content.description}</p>
        </section>
      </main>
    )
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="sign-in-title">
        <div className="auth-heading">
          <p className="auth-eyebrow">Serverless Student Manager</p>
          <h1 id="sign-in-title">Acesse sua conta</h1>
          <p className="auth-description">
            Entre com o e-mail associado ao seu usuário administrativo.
          </p>
        </div>

        <form className="auth-form" onSubmit={handleSignIn}>
          <div className="form-field">
            <label htmlFor="email">E-mail</label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={isLoading}
              required
            />
          </div>

          <div className="form-field">
            <label htmlFor="password">Senha</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={isLoading}
              required
            />
          </div>

          {errorMessage ? (
            <p className="auth-error" role="alert">
              {errorMessage}
            </p>
          ) : null}

          <Button className="auth-submit" type="submit" disabled={isLoading}>
            {isLoading ? 'Entrando…' : 'Entrar'}
          </Button>
        </form>
      </section>
    </main>
  )
}

export default App
