import { type FormEvent, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  ApiResponseError,
  AuthSessionUnavailableError,
  updateStudent,
  type StudentDetail,
  type UpdateStudentRequest,
} from '@/lib/api'
import {
  mutableStudentFieldNames,
  normalizeMutableStudentFields,
  validateMutableStudentFields,
  type MutableStudentFields,
} from '@/lib/studentFields'
import { updateStudentErrorMessage } from '@/lib/updateStudentError'

function mutableFields(student: StudentDetail): MutableStudentFields {
  return {
    fullName: student.fullName,
    studentEmail: student.studentEmail,
    phone: student.phone,
    birthDate: student.birthDate,
  }
}

function updateRequest(
  student: StudentDetail,
  fields: MutableStudentFields,
): UpdateStudentRequest {
  const request: UpdateStudentRequest = { expectedVersion: student.version }
  for (const name of mutableStudentFieldNames) {
    if (fields[name] !== student[name]) request[name] = fields[name]
  }
  return request
}

type Props = {
  student: StudentDetail
  onUpdated: (student: StudentDetail) => void
  onCancel: () => void
  disabled?: boolean
}

export function EditStudentForm({
  student,
  onUpdated,
  onCancel,
  disabled = false,
}: Props) {
  const [fields, setFields] = useState(() => mutableFields(student))
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const attempt = useRef<{ snapshot: string; key: string } | null>(null)
  const inFlight = useRef(false)
  const current = useRef(false)

  useEffect(() => {
    current.current = true
    return () => {
      current.current = false
    }
  }, [])

  const normalized = normalizeMutableStudentFields(fields)
  const request = updateRequest(student, normalized)
  const hasChanges = Object.keys(request).length > 1

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (inFlight.current || disabled || !hasChanges) return
    const invalid = validateMutableStudentFields(fields, normalized)
    if (invalid) {
      setError(invalid)
      return
    }
    const snapshot = JSON.stringify(request)
    if (attempt.current?.snapshot !== snapshot) {
      attempt.current = { snapshot, key: crypto.randomUUID() }
    }
    inFlight.current = true
    setLoading(true)
    setError(null)
    try {
      const updated = await updateStudent(
        student.studentId,
        request,
        attempt.current.key,
      )
      if (!current.current) return
      attempt.current = null
      onUpdated(updated)
    } catch (failure) {
      if (!current.current) return
      setError(updateStudentErrorMessage(failure))
      if (
        failure instanceof AuthSessionUnavailableError ||
        (failure instanceof ApiResponseError &&
          failure.status >= 400 &&
          failure.status < 500 &&
          !(failure.status === 409 && failure.code === 'OPERATION_IN_PROGRESS'))
      ) {
        attempt.current = null
      }
    } finally {
      inFlight.current = false
      if (current.current) setLoading(false)
    }
  }

  const labels: Record<keyof MutableStudentFields, string> = {
    fullName: 'Nome completo',
    studentEmail: 'E-mail',
    phone: 'Telefone',
    birthDate: 'Data de nascimento',
  }

  return (
    <form className="auth-form" aria-label="Editar aluno" onSubmit={submit} noValidate>
      <h2>Editar aluno</h2>
      <div className="student-readonly-fields" aria-label="Dados não editáveis">
        <p><strong>Matrícula:</strong> {student.registrationNumber}</p>
        <p><strong>Status:</strong> {student.status}</p>
      </div>
      {mutableStudentFieldNames.map((name) => (
        <div className="form-field" key={name}>
          <label htmlFor={`edit-${name}`}>{labels[name]}</label>
          <input
            id={`edit-${name}`}
            name={name}
            type={name === 'birthDate' ? 'date' : name === 'phone' ? 'tel' : 'text'}
            inputMode={name === 'studentEmail' ? 'email' : undefined}
            max={name === 'birthDate' ? new Date().toISOString().slice(0, 10) : undefined}
            value={fields[name]}
            required
            disabled={loading || disabled}
            onChange={(event) => {
              setFields((old) => ({ ...old, [name]: event.target.value }))
              setError(null)
            }}
          />
        </div>
      ))}
      {!hasChanges && !error ? (
        <p className="auth-notice" role="status">Nenhuma alteração realizada.</p>
      ) : null}
      {error ? <p className="auth-error" role="alert">{error}</p> : null}
      {loading ? <p className="auth-notice" role="status">Salvando alterações…</p> : null}
      <Button type="submit" disabled={loading || disabled || !hasChanges}>
        Salvar alterações
      </Button>
      <Button type="button" variant="outline" disabled={loading || disabled} onClick={onCancel}>
        Cancelar
      </Button>
    </form>
  )
}
