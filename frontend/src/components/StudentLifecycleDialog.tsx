import { type FormEvent, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  ApiResponseError,
  AuthSessionUnavailableError,
  deactivateStudent,
  reactivateStudent,
  type StudentDetail,
} from '@/lib/api'
import { studentLifecycleErrorMessage } from '@/lib/studentLifecycleError'

export type StudentLifecycleAction = 'deactivate' | 'reactivate'

type Props = {
  action: StudentLifecycleAction
  student: StudentDetail
  onCompleted: (student: StudentDetail, action: StudentLifecycleAction) => void
  onCancel: () => void
}

function hasUnsafeControls(value: string): boolean {
  return Array.from(value).some((character) => {
    const codePoint = character.codePointAt(0) ?? 0
    return codePoint <= 0x1f ||
      (codePoint >= 0x7f && codePoint <= 0x9f) ||
      codePoint === 0x2028 || codePoint === 0x2029
  })
}

function reasonError(reason: string): string | null {
  const normalized = reason.trim()
  if (normalized.length < 5 || normalized.length > 300) {
    return 'Informe um motivo entre 5 e 300 caracteres.'
  }
  if (hasUnsafeControls(normalized)) {
    return 'O motivo contém caracteres não permitidos.'
  }
  return null
}

export function StudentLifecycleDialog({
  action,
  student,
  onCompleted,
  onCancel,
}: Props) {
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const attempt = useRef<{ snapshot: string; key: string } | null>(null)
  const inFlight = useRef(false)
  const current = useRef(false)
  const cancel = useRef(onCancel)
  const reasonField = useRef<HTMLTextAreaElement>(null)
  const confirmButton = useRef<HTMLButtonElement>(null)
  const isDeactivate = action === 'deactivate'

  useEffect(() => {
    cancel.current = onCancel
  }, [onCancel])

  useEffect(() => {
    current.current = true
    if (isDeactivate) reasonField.current?.focus()
    else confirmButton.current?.focus()
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape' && !inFlight.current) cancel.current()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      current.current = false
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [isDeactivate])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (inFlight.current) return
    const normalizedReason = reason.trim()
    if (isDeactivate) {
      const invalid = reasonError(reason)
      if (invalid) {
        setError(invalid)
        return
      }
    }
    const snapshot = JSON.stringify(isDeactivate
      ? { expectedVersion: student.version, reason: normalizedReason }
      : { expectedVersion: student.version })
    if (attempt.current?.snapshot !== snapshot) {
      attempt.current = { snapshot, key: crypto.randomUUID() }
    }
    inFlight.current = true
    setLoading(true)
    setError(null)
    try {
      const updated = isDeactivate
        ? await deactivateStudent(student.studentId, {
          expectedVersion: student.version,
          reason: normalizedReason,
        }, attempt.current.key)
        : await reactivateStudent(student.studentId, {
          expectedVersion: student.version,
        }, attempt.current.key)
      if (!current.current) return
      attempt.current = null
      onCompleted(updated, action)
    } catch (failure) {
      if (!current.current) return
      setError(studentLifecycleErrorMessage(failure))
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

  const title = isDeactivate ? 'Desativar aluno' : 'Reativar aluno'
  const submitLabel = isDeactivate ? 'Confirmar desativação' : 'Confirmar reativação'

  return (
    <div className="dialog-backdrop">
      <section
        className="lifecycle-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="lifecycle-dialog-title"
      >
        <form className="auth-form" aria-label={title} onSubmit={submit} noValidate>
          <h2 id="lifecycle-dialog-title">{title}</h2>
          <p className="auth-description">
            {isDeactivate
              ? 'Confirme a desativação e informe o motivo.'
              : 'Confirme a reativação deste aluno.'}
          </p>
          {isDeactivate ? (
            <div className="form-field">
              <label htmlFor="lifecycle-reason">Motivo</label>
              <textarea
                ref={reasonField}
                id="lifecycle-reason"
                value={reason}
                minLength={5}
                maxLength={300}
                required
                disabled={loading}
                aria-describedby="lifecycle-reason-guidance"
                onChange={(event) => {
                  setReason(event.target.value)
                  setError(null)
                }}
              />
              <p id="lifecycle-reason-guidance" className="field-guidance">
                Evite incluir dados pessoais ou sensíveis desnecessários.
              </p>
            </div>
          ) : null}
          {error ? <p className="auth-error" role="alert">{error}</p> : null}
          {loading ? <p className="auth-notice" role="status">Atualizando status…</p> : null}
          <div className="dialog-actions">
            <Button
              ref={!isDeactivate ? confirmButton : undefined}
              type="submit"
              disabled={loading}
            >
              {loading ? 'Atualizando…' : submitLabel}
            </Button>
            <Button type="button" variant="outline" disabled={loading} onClick={onCancel}>
              Cancelar
            </Button>
          </div>
        </form>
      </section>
    </div>
  )
}
