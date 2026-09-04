import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import {
  confirmSignIn,
  getCurrentUser,
  signIn,
  signOut,
  type SignInOutput,
} from 'aws-amplify/auth'

import { Button } from '@/components/ui/button'
import {
  authenticatedPost,
  AuthSessionUnavailableError,
  fetchCurrentUserProfile,
  fetchStudents,
  type StudentSummary,
  type UserProfile,
} from '@/lib/api'

import './App.css'

type AuthView =
  | 'auth-check'
  | 'sign-in'
  | 'new-password-required'
  | 'mfa-setup-selection'
  | 'totp-setup'
  | 'totp-challenge'
  | 'profile-resolution'
  | 'activation'
  | 'operational'
  | 'unsupported-step'

const GENERIC_SIGN_IN_ERROR =
  'Não foi possível entrar. Verifique seus dados e tente novamente.'
const GENERIC_NEW_PASSWORD_ERROR =
  'Não foi possível definir a nova senha. Revise os dados e tente novamente.'
const GENERIC_TOTP_ERROR =
  'Não foi possível confirmar o código. Verifique-o e tente novamente.'
const GENERIC_SESSION_ERROR =
  'Não foi possível verificar sua sessão. Entre novamente.'
const GENERIC_SIGN_OUT_ERROR =
  'Não foi possível sair. Tente novamente.'
const PROFILE_RESOLUTION_ERROR =
  'Não foi possível carregar seu perfil. Tente novamente.'
const STUDENTS_LOAD_ERROR =
  'Não foi possível carregar os alunos. Tente novamente.'
const ACTIVATION_SUCCESS = 'Acesso ativado com sucesso.'
const ACTIVATION_INVALID_REQUEST = 'A solicitação de ativação é inválida.'
const ACTIVATION_AUTH_ERROR = 'Sua sessão ou autenticação não é válida.'
const ACTIVATION_FORBIDDEN = 'Esta identidade não está autorizada.'
const ACTIVATION_CONFLICT =
  'A ativação ainda não é permitida ou o estado é incompatível.'
const ACTIVATION_TEMPORARY_ERROR =
  'Não foi possível ativar o acesso agora. Tente novamente.'
const UNSUPPORTED_STEP_ERROR =
  'Não foi possível concluir o acesso nesta etapa. Tente novamente mais tarde.'
const AUTHENTICATOR_APP_NAME = 'Serverless Student Manager'

const nextStageContent: Partial<
  Record<AuthView, { eyebrow: string; title: string; description: string }>
> = {
  'auth-check': {
    eyebrow: 'Serverless Student Manager',
    title: 'Verificando sua sessão',
    description: 'Aguarde um instante.',
  },
  'mfa-setup-selection': {
    eyebrow: 'Verificação em duas etapas',
    title: 'Preparando o autenticador',
    description: 'Aguarde enquanto o método de segurança é preparado.',
  },
  'unsupported-step': {
    eyebrow: 'Acesso não concluído',
    title: 'Não foi possível continuar',
    description: UNSUPPORTED_STEP_ERROR,
  },
}

function App() {
  const [authView, setAuthView] = useState<AuthView>('auth-check')
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
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null)
  const [isProfileLoading, setIsProfileLoading] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [students, setStudents] = useState<StudentSummary[]>([])
  const [isStudentsLoading, setIsStudentsLoading] = useState(false)
  const [studentsError, setStudentsError] = useState<string | null>(null)
  const [isActivationLoading, setIsActivationLoading] = useState(false)
  const [activationMessage, setActivationMessage] = useState<string | null>(
    null,
  )
  const [isActivationError, setIsActivationError] = useState(false)
  const activationIdempotencyKey = useRef<string | null>(null)
  const activationInFlight = useRef(false)

  const loadStudents = useCallback(async () => {
    setStudentsError(null)
    setIsStudentsLoading(true)

    try {
      const page = await fetchStudents()
      setStudents(page.items)
    } catch {
      setStudentsError(STUDENTS_LOAD_ERROR)
    } finally {
      setIsStudentsLoading(false)
    }
  }, [])

  const resolveCurrentUser = useCallback(async (
    isCurrent: () => boolean = () => true,
  ) => {
    setAuthView('profile-resolution')
    setProfileError(null)
    setIsProfileLoading(true)

    try {
      const profile = await fetchCurrentUserProfile()
      if (!isCurrent()) {
        return
      }

      setUserProfile(profile)
      if (profile.status === 'INVITED') {
        setAuthView('activation')
      } else {
        setAuthView('operational')
        await loadStudents()
      }
    } catch {
      if (isCurrent()) {
        setProfileError(PROFILE_RESOLUTION_ERROR)
      }
    } finally {
      if (isCurrent()) {
        setIsProfileLoading(false)
      }
    }
  }, [loadStudents])

  useEffect(() => {
    let isActive = true

    async function restoreSession() {
      try {
        await getCurrentUser()

        if (isActive) {
          await resolveCurrentUser(() => isActive)
        }
      } catch (error) {
        if (!isActive) {
          return
        }

        const isUnauthenticated =
          error instanceof Error &&
          error.name === 'UserUnAuthenticatedException'

        setErrorMessage(isUnauthenticated ? null : GENERIC_SESSION_ERROR)
        setAuthView('sign-in')
      }
    }

    void restoreSession()

    return () => {
      isActive = false
    }
  }, [resolveCurrentUser])

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
        await resolveCurrentUser()
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

  async function handleSignOut() {
    setErrorMessage(null)
    setIsLoading(true)

    try {
      await signOut()
      clearPasswords()
      clearTotpData()
      setEmail('')
      setUserProfile(null)
      setProfileError(null)
      setStudents([])
      setStudentsError(null)
      setActivationMessage(null)
      setIsActivationError(false)
      activationIdempotencyKey.current = null
      setAuthView('sign-in')
    } catch {
      setErrorMessage(GENERIC_SIGN_OUT_ERROR)
    } finally {
      setIsLoading(false)
    }
  }

  async function handleActivation() {
    if (activationInFlight.current) {
      return
    }

    activationInFlight.current = true
    setActivationMessage(null)
    setIsActivationError(false)
    setIsActivationLoading(true)

    const idempotencyKey =
      activationIdempotencyKey.current ?? crypto.randomUUID()
    activationIdempotencyKey.current = idempotencyKey

    try {
      const response = await authenticatedPost(
        '/users/me/activation',
        idempotencyKey,
      )

      if (response.status === 200) {
        const result: unknown = await response.json()

        if (!isSuccessfulActivation(result)) {
          setIsActivationError(true)
          setActivationMessage(ACTIVATION_TEMPORARY_ERROR)
          return
        }

        activationIdempotencyKey.current = null
        setUserProfile((current) =>
          current
            ? {
                ...current,
                role: result.role,
                status: 'ACTIVE',
                authVersion: result.authVersion,
              }
            : current,
        )
        setActivationMessage(ACTIVATION_SUCCESS)
        setAuthView('operational')
        await loadStudents()
        return
      }

      setIsActivationError(true)

      if (response.status < 500) {
        activationIdempotencyKey.current = null
      }

      switch (response.status) {
        case 400:
          setActivationMessage(ACTIVATION_INVALID_REQUEST)
          break
        case 401:
          setActivationMessage(ACTIVATION_AUTH_ERROR)
          break
        case 403:
          setActivationMessage(ACTIVATION_FORBIDDEN)
          break
        case 409:
          setActivationMessage(ACTIVATION_CONFLICT)
          break
        default:
          setActivationMessage(ACTIVATION_TEMPORARY_ERROR)
      }
    } catch (error) {
      setIsActivationError(true)

      if (error instanceof AuthSessionUnavailableError) {
        activationIdempotencyKey.current = null
        setActivationMessage(ACTIVATION_AUTH_ERROR)
      } else {
        setActivationMessage(ACTIVATION_TEMPORARY_ERROR)
      }
    } finally {
      activationInFlight.current = false
      setIsActivationLoading(false)
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

  if (authView === 'profile-resolution') {
    return (
      <main className="auth-page">
        <section className="auth-card" aria-labelledby="profile-title">
          <div className="auth-heading">
            <p className="auth-eyebrow">Acesso confirmado</p>
            <h1 id="profile-title">Carregando seu perfil</h1>
            <p className="auth-description">
              Aguarde enquanto verificamos seu estado de acesso.
            </p>
          </div>

          {profileError ? (
            <p className="auth-error" role="alert">
              {profileError}
            </p>
          ) : null}

          {isProfileLoading ? (
            <p className="auth-notice" role="status">
              Verificando acesso…
            </p>
          ) : (
            <Button type="button" onClick={() => void resolveCurrentUser()}>
              Tentar novamente
            </Button>
          )}

          <Button
            type="button"
            variant="outline"
            onClick={handleSignOut}
            disabled={isLoading || isProfileLoading}
          >
            {isLoading ? 'Saindo…' : 'Sair'}
          </Button>
        </section>
      </main>
    )
  }

  if (authView === 'activation') {
    return (
      <main className="auth-page">
        <section className="auth-card" aria-labelledby="activation-title">
          <div className="auth-heading">
            <p className="auth-eyebrow">Primeiro acesso</p>
            <h1 id="activation-title">Ative seu acesso</h1>
            <p className="auth-description">
              Olá, {userProfile?.fullName}. Conclua a ativação para continuar.
            </p>
          </div>

          {activationMessage ? (
            <p
              className={isActivationError ? 'auth-error' : 'auth-notice'}
              role={isActivationError ? 'alert' : 'status'}
            >
              {activationMessage}
            </p>
          ) : null}

          <Button
            type="button"
            onClick={handleActivation}
            disabled={isLoading || isActivationLoading}
          >
            {isActivationLoading ? 'Ativando…' : 'Ativar acesso'}
          </Button>

          <Button
            type="button"
            variant="outline"
            onClick={handleSignOut}
            disabled={isLoading || isActivationLoading}
          >
            {isLoading ? 'Saindo…' : 'Sair'}
          </Button>
        </section>
      </main>
    )
  }

  if (authView === 'operational') {
    return (
      <main className="operational-page">
        <section className="operational-card" aria-labelledby="students-title">
          <header className="operational-header">
            <div className="auth-heading">
              <p className="auth-eyebrow">Área operacional</p>
              <h1 id="students-title">Alunos</h1>
              <p className="auth-description">
                {userProfile?.fullName}, consulte os alunos cadastrados.
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={handleSignOut}
              disabled={isLoading || isStudentsLoading}
            >
              {isLoading ? 'Saindo…' : 'Sair'}
            </Button>
          </header>

          {activationMessage ? (
            <p className="auth-notice" role="status">
              {activationMessage}
            </p>
          ) : null}

          {isStudentsLoading ? (
            <p className="auth-notice" role="status">
              Carregando alunos…
            </p>
          ) : null}

          {studentsError ? (
            <div className="students-feedback">
              <p className="auth-error" role="alert">
                {studentsError}
              </p>
              <Button type="button" onClick={() => void loadStudents()}>
                Tentar novamente
              </Button>
            </div>
          ) : null}

          {!isStudentsLoading && !studentsError && students.length === 0 ? (
            <p className="students-empty">Nenhum aluno encontrado.</p>
          ) : null}

          {!isStudentsLoading && !studentsError && students.length > 0 ? (
            <ul className="students-list">
              {students.map((student) => (
                <li className="student-card" key={student.studentId}>
                  <div>
                    <h2>{student.fullName}</h2>
                    <p>Matrícula: {student.registrationNumber}</p>
                  </div>
                  <span className="student-status">{student.status}</span>
                </li>
              ))}
            </ul>
          ) : null}
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

function isSuccessfulActivation(value: unknown): value is {
  userId: string
  role: 'ADMIN' | 'OPERATOR'
  status: 'ACTIVE'
  authVersion: number
} {
  if (typeof value !== 'object' || value === null) {
    return false
  }

  const activation = value as Record<string, unknown>

  return (
    typeof activation.userId === 'string' &&
    (activation.role === 'ADMIN' || activation.role === 'OPERATOR') &&
    activation.status === 'ACTIVE' &&
    Number.isInteger(activation.authVersion) &&
    typeof activation.authVersion === 'number'
  )
}

export default App
