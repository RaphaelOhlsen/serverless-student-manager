import { type FormEvent, useState } from 'react'
import { signIn } from 'aws-amplify/auth'

import { Button } from '@/components/ui/button'

import './App.css'

type AuthView = 'sign-in' | 'new-password-required'

const GENERIC_SIGN_IN_ERROR =
  'Não foi possível entrar. Verifique seus dados e tente novamente.'

function App() {
  const [authView, setAuthView] = useState<AuthView>('sign-in')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)

  async function handleSignIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setErrorMessage(null)
    setStatusMessage(null)
    setIsLoading(true)

    try {
      const result = await signIn({
        username: email.trim(),
        password,
      })

      switch (result.nextStep.signInStep) {
        case 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED':
          setPassword('')
          setAuthView('new-password-required')
          break
        case 'DONE':
          setPassword('')
          setStatusMessage('Autenticação concluída com sucesso.')
          break
        default:
          setErrorMessage(
            'Não foi possível concluir o acesso nesta etapa. Tente novamente mais tarde.',
          )
      }
    } catch {
      setErrorMessage(GENERIC_SIGN_IN_ERROR)
    } finally {
      setIsLoading(false)
    }
  }

  if (authView === 'new-password-required') {
    return (
      <main className="auth-page">
        <section className="auth-card" aria-labelledby="new-password-title">
          <p className="auth-eyebrow">Primeiro acesso</p>
          <h1 id="new-password-title">Defina uma nova senha</h1>
          <p className="auth-description">
            Sua identidade foi confirmada. Para continuar, será necessário
            substituir a senha temporária.
          </p>
          <p className="auth-notice" role="status">
            A definição da nova senha será disponibilizada na próxima etapa.
          </p>
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

          {statusMessage ? (
            <p className="auth-success" role="status">
              {statusMessage}
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
