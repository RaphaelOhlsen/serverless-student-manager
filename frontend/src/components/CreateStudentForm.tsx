import { type FormEvent, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ApiResponseError, AuthSessionUnavailableError, createStudent,
  type CreatedStudent, type CreateStudentRequest } from '@/lib/api'

const empty: CreateStudentRequest = {
  fullName: '', registrationNumber: '', studentEmail: '', phone: '', birthDate: '',
}
// Python str.isspace() (used by strip/split), including the C0 separators.
// eslint-disable-next-line no-control-regex -- Required to mirror Python whitespace exactly.
const whitespace = /[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/u
const trim = (value: string) => value.replace(new RegExp(`^${whitespace.source}|${whitespace.source}$`, 'gu'), '')
const controls = /\p{C}/u

function normalize(input: CreateStudentRequest): CreateStudentRequest {
  return {
    ...input,
    fullName: trim(input.fullName).split(whitespace).join(' '),
    registrationNumber: trim(input.registrationNumber).toUpperCase(),
    studentEmail: trim(input.studentEmail).toLowerCase(),
  }
}

function validate(raw: CreateStudentRequest, value: CreateStudentRequest): string | null {
  if (controls.test(raw.fullName) || [...value.fullName].length < 3 || [...value.fullName].length > 150)
    return 'Informe um nome de 3 a 150 caracteres, sem caracteres de controle.'
  if (!/^[A-Z0-9-]{4,20}$/.test(value.registrationNumber))
    return 'Informe uma matrícula de 4 a 20 letras, números ou hífens.'
  if (!value.studentEmail || [...value.studentEmail].length > 254 ||
      whitespace.test(value.studentEmail) || controls.test(value.studentEmail))
    return 'Informe um e-mail de até 254 caracteres, sem espaços ou caracteres de controle.'
  if (!/^\+[1-9][0-9]{7,14}$/.test(value.phone))
    return 'Informe o telefone com +, código do país e números (E.164).'
  const date = value.birthDate
  const parsed = new Date(date + 'T00:00:00.000Z')
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || date < '0001-01-01' ||
      !Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== date ||
      date > new Date().toISOString().slice(0, 10))
    return 'Informe uma data de nascimento válida, não futura.'
  return null
}

function messageFor(error: unknown): string {
  if (error instanceof AuthSessionUnavailableError ||
      (error instanceof ApiResponseError && error.status === 401))
    return 'Sua sessão está inválida ou expirou. Saia e entre novamente.'
  if (error instanceof ApiResponseError) {
    if (error.status === 400) return 'Revise os dados informados.'
    if (error.status === 403) return 'Seu usuário não está autorizado a criar aluno.'
    if (error.status === 409) {
      switch (error.code) {
        case 'REGISTRATION_NUMBER_ALREADY_EXISTS': return 'Matrícula já cadastrada.'
        case 'STUDENT_EMAIL_ALREADY_EXISTS': return 'E-mail já cadastrado.'
        case 'STUDENT_UNIQUENESS_CONFLICT': return 'Matrícula e e-mail já cadastrados.'
        case 'IDEMPOTENCY_KEY_REUSED': return 'Esta tentativa é incompatível com os dados enviados. Revise os dados ou inicie uma nova tentativa.'
        case 'OPERATION_IN_PROGRESS': return 'A solicitação está em andamento. Aguarde e tente novamente.'
      }
    }
  }
  return 'Não foi possível confirmar a criação. Tente novamente com os mesmos dados.'
}

type Props = {
  onCreated: (student: CreatedStudent) => void
  onCancel: () => void
  disabled?: boolean
}

export function CreateStudentForm({ onCreated, onCancel, disabled = false }: Props) {
  const [fields, setFields] = useState(empty)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const attempt = useRef<{ snapshot: string; key: string } | null>(null)
  const inFlight = useRef(false)
  const current = useRef(false)
  useEffect(() => {
    current.current = true
    return () => { current.current = false }
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (inFlight.current || disabled) return
    const payload = normalize(fields)
    const invalid = validate(fields, payload)
    if (invalid) { setError(invalid); return }
    const snapshot = JSON.stringify(payload)
    if (attempt.current?.snapshot !== snapshot)
      attempt.current = { snapshot, key: crypto.randomUUID() }
    inFlight.current = true
    setLoading(true)
    setError(null)
    try {
      const student = await createStudent(payload, attempt.current.key)
      if (!current.current) return
      attempt.current = null
      onCreated(student)
    } catch (failure) {
      if (!current.current) return
      setError(messageFor(failure))
      if (failure instanceof AuthSessionUnavailableError ||
          (failure instanceof ApiResponseError && failure.status >= 400 && failure.status < 500 &&
           !(failure.status === 409 && failure.code === 'OPERATION_IN_PROGRESS')))
        attempt.current = null
    } finally {
      inFlight.current = false
      if (current.current) setLoading(false)
    }
  }

  const labels: Record<keyof CreateStudentRequest, string> = {
    fullName: 'Nome completo', registrationNumber: 'Matrícula', studentEmail: 'E-mail',
    phone: 'Telefone', birthDate: 'Data de nascimento',
  }
  return (
    <form className="auth-form" aria-label="Novo aluno" onSubmit={submit} noValidate>
      <h2>Novo aluno</h2>
      {(Object.keys(labels) as (keyof CreateStudentRequest)[]).map((name) => (
        <div className="form-field" key={name}>
          <label htmlFor={`create-${name}`}>{labels[name]}</label>
          <input id={`create-${name}`} name={name}
            type={name === 'birthDate' ? 'date' : name === 'phone' ? 'tel' : 'text'}
            inputMode={name === 'studentEmail' ? 'email' : undefined}
            max={name === 'birthDate' ? new Date().toISOString().slice(0, 10) : undefined}
            value={fields[name]} required disabled={loading || disabled}
            onChange={(event) => setFields((old) => ({ ...old, [name]: event.target.value }))} />
        </div>
      ))}
      {error ? <p className="auth-error" role="alert">{error}</p> : null}
      {loading ? <p className="auth-notice" role="status">Salvando aluno…</p> : null}
      <Button type="submit" disabled={loading || disabled}>Salvar aluno</Button>
      <Button type="button" variant="outline" disabled={loading || disabled} onClick={onCancel}>Cancelar</Button>
    </form>
  )
}
