/** @vitest-environment jsdom */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ update: vi.fn() }))
vi.mock('@/lib/api', async (original) => ({
  ...await original<typeof import('@/lib/api')>(),
  updateStudent: mocks.update,
}))

import { ApiResponseError, type StudentDetail } from '@/lib/api'
import { updateStudentErrorMessage } from '@/lib/updateStudentError'
import { EditStudentForm } from './EditStudentForm'

const student: StudentDetail = {
  studentId: '00000000-0000-4000-8000-000000000100',
  registrationNumber: 'MAT-001',
  fullName: 'Aluno Exemplo',
  studentEmail: 'aluno@example.test',
  phone: '+15555550123',
  birthDate: '2000-01-15',
  status: 'INACTIVE',
  version: 7,
  createdAt: '2026-09-06T10:28:53.080Z',
  updatedAt: '2026-09-07T10:28:53.080Z',
}

function renderForm(onUpdated = vi.fn()) {
  render(<EditStudentForm student={student} onUpdated={onUpdated} onCancel={vi.fn()} />)
  return onUpdated
}

function submit() {
  fireEvent.submit(screen.getByRole('form', { name: 'Editar aluno' }))
}

describe('EditStudentForm', () => {
  beforeEach(() => mocks.update.mockReset())
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('renders detail fields and keeps registration and status read-only', () => {
    renderForm()
    expect((screen.getByLabelText('Nome completo') as HTMLInputElement).value).toBe(student.fullName)
    expect((screen.getByLabelText('E-mail') as HTMLInputElement).value).toBe(student.studentEmail)
    expect((screen.getByLabelText('Telefone') as HTMLInputElement).value).toBe(student.phone)
    expect((screen.getByLabelText('Data de nascimento') as HTMLInputElement).value).toBe(student.birthDate)
    expect(screen.getByText('MAT-001')).toBeTruthy()
    expect(screen.getByText('INACTIVE')).toBeTruthy()
    expect(screen.queryByLabelText('Matrícula')).toBeNull()
    expect(screen.queryByLabelText('Status')).toBeNull()
  })

  it('sends expectedVersion and only normalized changed fields with one UUID', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('00000000-0000-4000-8000-000000000001')
    mocks.update.mockResolvedValue({ ...student, fullName: 'Aluno Atualizado', version: 8 })
    const updated = renderForm()
    fireEvent.change(screen.getByLabelText('Nome completo'), {
      target: { value: '  Aluno   Atualizado  ' },
    })
    submit()
    await waitFor(() => expect(mocks.update).toHaveBeenCalledOnce())
    expect(mocks.update).toHaveBeenCalledWith(
      student.studentId,
      { expectedVersion: 7, fullName: 'Aluno Atualizado' },
      '00000000-0000-4000-8000-000000000001',
    )
    expect(updated).toHaveBeenCalledWith({ ...student, fullName: 'Aluno Atualizado', version: 8 })
  })

  it('does not submit when normalized values did not change', () => {
    const uuid = vi.spyOn(crypto, 'randomUUID')
    renderForm()
    fireEvent.change(screen.getByLabelText('Nome completo'), {
      target: { value: '  Aluno   Exemplo  ' },
    })
    expect((screen.getByRole('button', { name: 'Salvar alterações' }) as HTMLButtonElement).disabled).toBe(true)
    submit()
    expect(mocks.update).not.toHaveBeenCalled()
    expect(uuid).not.toHaveBeenCalled()
  })

  it.each([
    ['STUDENT_VERSION_CONFLICT', 'Este aluno foi alterado'],
    ['STUDENT_EMAIL_ALREADY_EXISTS', 'E-mail já cadastrado.'],
    ['IDEMPOTENCY_KEY_REUSED', 'tentativa é incompatível'],
  ])('maps %s to a specific message', (code, message) => {
    expect(updateStudentErrorMessage(new ApiResponseError(409, code))).toContain(message)
  })

  it('blocks double submit and cancellation while pending', async () => {
    let resolve!: (value: StudentDetail) => void
    mocks.update.mockReturnValue(new Promise((done) => { resolve = done }))
    const cancel = vi.fn()
    render(<EditStudentForm student={student} onUpdated={vi.fn()} onCancel={cancel} />)
    fireEvent.change(screen.getByLabelText('Telefone'), { target: { value: '+15555550124' } })
    submit()
    submit()
    expect(mocks.update).toHaveBeenCalledOnce()
    expect((screen.getByRole('button', { name: 'Salvar alterações' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(cancel).not.toHaveBeenCalled()
    await act(async () => resolve({ ...student, phone: '+15555550124', version: 8 }))
  })

  it('reuses one key for a recoverable retry of the same request', async () => {
    mocks.update
      .mockRejectedValueOnce(new TypeError('network'))
      .mockResolvedValueOnce({ ...student, phone: '+15555550124', version: 8 })
    renderForm()
    fireEvent.change(screen.getByLabelText('Telefone'), { target: { value: '+15555550124' } })
    submit()
    await screen.findByRole('alert')
    submit()
    await waitFor(() => expect(mocks.update).toHaveBeenCalledTimes(2))
    expect(mocks.update.mock.calls[1]?.[2]).toBe(mocks.update.mock.calls[0]?.[2])
  })
})
