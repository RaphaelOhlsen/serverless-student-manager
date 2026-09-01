import { type FormEvent, useState } from 'react'
import {
  confirmSignIn,
  signIn,
  type SignInOutput,
} from 'aws-amplify/auth'

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
const GENERIC_TOTP_ERROR =
  'Não foi possível confirmar o código. Verifique-o e tente novamente.'
const UNSUPPORTED_STEP_ERROR =
  'Não foi possível concluir o acesso nesta etapa. Tente novamente mais tarde.'
const AUTHENTICATOR_APP_NAME = 'Serverless Student Manager'

const nextStageContent: Partial<
  Record<AuthView, { eyebrow: string; title: string; description: string }>
> = {
  'mfa-setup-selection': {
    eyebrow: 'Verificação em duas etapas',
    title: 'Preparando o autenticador',
    description: 'Aguarde enquanto o método de segurança é preparado.',
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
  const [totpSetupUri, setTotpSetupUri] = useState<string | null>(null)
  const [totpSharedSecret, setTotpSharedSecret] = useState<string | null>(null)
  const [totpCode, setTotpCode] = useState('')
  const [copyConfirmation, setCopyConfirmation] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  function clearPasswords() {
    setPassword('')
    setNewPassword('')
    setNewPasswordConfirmation('')
  }

  function clearTotpData() {
    setTotpSetupUri(null)
    setTotpSharedSecret(null)
    setTotpCode('')
    setCopyConfirmation(null)
  }

  function transitionToUnsupportedStep() {
    clearPasswords()
    clearTotpData()
    setEmail('')
    setAuthView('unsupported-step')
  }

  async function transitionFromSignInStep(
    nextStep: SignInOutput['nextStep'],
  ) {
    setErrorMessage(null)

    switch (nextStep.signInStep) {
      case 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED':
        setAuthView('new-password-required')
        break
      case 'CONTINUE_SIGN_IN_WITH_MFA_SETUP_SELECTION': {
        setAuthView('mfa-setup-selection')
        if (!nextStep.allowedMFATypes?.includes('TOTP')) {
          transitionToUnsupportedStep()
          break
        }

        try {
          const result = await confirmSignIn({ challengeResponse: 'TOTP' })
          await transitionFromSignInStep(result.nextStep)
        } catch {
          transitionToUnsupportedStep()
        }
        break
      }
      case 'CONTINUE_SIGN_IN_WITH_TOTP_SETUP': {
        const setupDetails = nextStep.totpSetupDetails
        const setupUri = setupDetails.getSetupUri(AUTHENTICATOR_APP_NAME)

        setTotpSetupUri(setupUri.toString())
        setTotpSharedSecret(setupDetails.sharedSecret)
        setTotpCode('')
        setCopyConfirmation(null)
        setAuthView('totp-setup')
        break
      }
      case 'CONFIRM_SIGN_IN_WITH_TOTP_CODE':
        setTotpSetupUri(null)
        setTotpSharedSecret(null)
        setTotpCode('')
        setCopyConfirmation(null)
        setAuthView('totp-challenge')
        break
      case 'DONE':
        clearPasswords()
        clearTotpData()
        setEmail('')
        setAuthView('authenticated')
        break
      default:
        transitionToUnsupportedStep()
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
      await transitionFromSignInStep(result.nextStep)
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
      await transitionFromSignInStep(result.nextStep)
    } catch {
      setErrorMessage(GENERIC_NEW_PASSWORD_ERROR)
    } finally {
      setIsLoading(false)
    }
  }

  async function handleConfirmTotp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setErrorMessage(null)

    const normalizedCode = totpCode.trim()
    if (!/^\d{6}$/.test(normalizedCode)) {
      setErrorMessage('Informe um código de 6 dígitos.')
      return
    }

    setTotpCode('')
    setIsLoading(true)

    try {
      const result = await confirmSignIn({
        challengeResponse: normalizedCode,
      })

      await transitionFromSignInStep(result.nextStep)
    } catch {
      setErrorMessage(GENERIC_TOTP_ERROR)
    } finally {
      setIsLoading(false)
    }
  }

  async function handleCopySharedSecret() {
    if (!totpSharedSecret) {
      return
    }

    try {
      await navigator.clipboard.writeText(totpSharedSecret)
      setCopyConfirmation('Chave copiada.')
    } catch {
      setCopyConfirmation('Não foi possível copiar. Selecione a chave manualmente.')
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

  if (authView === 'totp-setup' || authView === 'totp-challenge') {
    const isSetup = authView === 'totp-setup'

    return (
      <main className="auth-page">
        <section className="auth-card" aria-labelledby="totp-title">
          <div className="auth-heading">
            <p className="auth-eyebrow">Verificação em duas etapas</p>
            <h1 id="totp-title">
              {isSetup ? 'Configure seu autenticador' : 'Informe o código'}
            </h1>
            <p className="auth-description">
              {isSetup
                ? 'Associe um aplicativo autenticador e informe o código gerado para concluir.'
                : 'Informe o código atual gerado pelo aplicativo autenticador.'}
            </p>
          </div>

          {isSetup && totpSetupUri && totpSharedSecret ? (
            <div className="totp-setup-details">
              <a className="totp-setup-link" href={totpSetupUri}>
                Abrir no aplicativo autenticador
              </a>

              <div className="manual-secret">
                <p>Ou use esta chave de configuração manual:</p>
                <code>{totpSharedSecret}</code>
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleCopySharedSecret}
                >
                  Copiar chave
                </Button>
                {copyConfirmation ? (
                  <p className="auth-notice" role="status">
                    {copyConfirmation}
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}

          <form className="auth-form" onSubmit={handleConfirmTotp}>
            <div className="form-field">
              <label htmlFor="totp-code">Código do autenticador</label>
              <input
                id="totp-code"
                name="totp-code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]{6}"
                maxLength={6}
                value={totpCode}
                onChange={(event) => setTotpCode(event.target.value)}
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
              {isLoading ? 'Confirmando…' : 'Confirmar código'}
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
