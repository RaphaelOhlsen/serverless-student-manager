/** @vitest-environment jsdom */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ deactivate: vi.fn(), reactivate: vi.fn() }))
vi.mock('@/lib/api', async (original) => ({
  ...await original<typeof import('@/lib/api')>(),
  deactivateStudent: mocks.deactivate,
  reactivateStudent: mocks.reactivate,
}))

import { ApiResponseError, type StudentDetail } from '@/lib/api'
import { StudentLifecycleDialog } from './StudentLifecycleDialog'

const activeStudent: StudentDetail = {
  studentId: '00000000-0000-4000-8000-000000000100',
  registrationNumber: 'MAT-001',
  fullName: 'Aluno Sintético',
  studentEmail: 'student@example.invalid',
  phone: '+15555550123',
  birthDate: '2000-01-15',
  status: 'ACTIVE',
  version: 7,
  createdAt: '2026-09-06T10:28:53.080Z',
  updatedAt: '2026-09-07T10:28:53.080Z',
}

function renderDialog(
  action: 'deactivate' | 'reactivate',
  onCompleted = vi.fn(),
) {
  render(
    <StudentLifecycleDialog
      action={action}
      student={action === 'deactivate' ? activeStudent : { ...activeStudent, status: 'INACTIVE' }}
      onCompleted={onCompleted}
      onCancel={vi.fn()}
    />,
  )
  return onCompleted
}

describe('StudentLifecycleDialog', () => {
  beforeEach(() => {
    mocks.deactivate.mockReset()
    mocks.reactivate.mockReset()
  })
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('trims a valid reason and sends the detail version with one UUID', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('00000000-0000-4000-8000-000000000001')
    const result = { ...activeStudent, status: 'INACTIVE' as const, version: 8 }
    mocks.deactivate.mockResolvedValue(result)
    const completed = renderDialog('deactivate')
    fireEvent.change(screen.getByLabelText('Motivo'), {
      target: { value: '  Motivo sintético válido  ' },
    })
    fireEvent.submit(screen.getByRole('form', { name: 'Desativar aluno' }))
    await waitFor(() => expect(mocks.deactivate).toHaveBeenCalledOnce())
    expect(mocks.deactivate).toHaveBeenCalledWith(
      activeStudent.studentId,
      { expectedVersion: 7, reason: 'Motivo sintético válido' },
      '00000000-0000-4000-8000-000000000001',
    )
    expect(completed).toHaveBeenCalledWith(result, 'deactivate')
  })

  it.each(['    ', 'abcd', `${'a'.repeat(301)}`, 'linha\nseguinte'])(
    'rejects an invalid reason without creating an operation: %j',
    (reason) => {
      const uuid = vi.spyOn(crypto, 'randomUUID')
      renderDialog('deactivate')
      fireEvent.change(screen.getByLabelText('Motivo'), { target: { value: reason } })
      fireEvent.submit(screen.getByRole('form', { name: 'Desativar aluno' }))
      expect(screen.getByRole('alert')).toBeTruthy()
      expect(mocks.deactivate).not.toHaveBeenCalled()
      expect(uuid).not.toHaveBeenCalled()
    },
  )

  it('reactivates with only expectedVersion and a UUID', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('00000000-0000-4000-8000-000000000002')
    const result = { ...activeStudent, version: 8 }
    mocks.reactivate.mockResolvedValue(result)
    const completed = renderDialog('reactivate')
    fireEvent.submit(screen.getByRole('form', { name: 'Reativar aluno' }))
    await waitFor(() => expect(mocks.reactivate).toHaveBeenCalledOnce())
    expect(mocks.reactivate).toHaveBeenCalledWith(
      activeStudent.studentId,
      { expectedVersion: 7 },
      '00000000-0000-4000-8000-000000000002',
    )
    expect(completed).toHaveBeenCalledWith(result, 'reactivate')
  })

  it.each([
    ['STUDENT_VERSION_CONFLICT', 'Os dados do aluno foram alterados.'],
    ['IDEMPOTENCY_KEY_REUSED', 'tentativa é incompatível'],
  ])('shows a specific safe error for %s', async (code, expected) => {
    mocks.deactivate.mockRejectedValue(new ApiResponseError(409, code))
    renderDialog('deactivate')
    fireEvent.change(screen.getByLabelText('Motivo'), {
      target: { value: 'Motivo que não deve aparecer no erro' },
    })
    fireEvent.submit(screen.getByRole('form', { name: 'Desativar aluno' }))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(expected)
    expect(alert.textContent).not.toContain('Motivo que não deve aparecer no erro')
  })

  it.each(['deactivate', 'reactivate'] as const)(
    'blocks a second %s submit synchronously while pending',
    async (action) => {
      let resolve!: (value: StudentDetail) => void
      const method = action === 'deactivate' ? mocks.deactivate : mocks.reactivate
      method.mockReturnValue(new Promise((done) => { resolve = done }))
      renderDialog(action)
      if (action === 'deactivate') {
        fireEvent.change(screen.getByLabelText('Motivo'), { target: { value: 'Motivo válido' } })
      }
      const form = screen.getByRole('form', {
        name: action === 'deactivate' ? 'Desativar aluno' : 'Reativar aluno',
      })
      fireEvent.submit(form)
      fireEvent.submit(form)
      expect(method).toHaveBeenCalledOnce()
      expect((screen.getByRole('button', { name: 'Atualizando…' }) as HTMLButtonElement).disabled).toBe(true)
      await act(async () => resolve({
        ...activeStudent,
        status: action === 'deactivate' ? 'INACTIVE' : 'ACTIVE',
        version: 8,
      }))
    },
  )

  it('reuses the key for a technical retry of the same attempt', async () => {
    mocks.deactivate
      .mockRejectedValueOnce(new TypeError('network'))
      .mockResolvedValueOnce({ ...activeStudent, status: 'INACTIVE', version: 8 })
    renderDialog('deactivate')
    fireEvent.change(screen.getByLabelText('Motivo'), { target: { value: 'Motivo válido' } })
    const form = screen.getByRole('form', { name: 'Desativar aluno' })
    fireEvent.submit(form)
    await screen.findByRole('alert')
    fireEvent.submit(form)
    await waitFor(() => expect(mocks.deactivate).toHaveBeenCalledTimes(2))
    expect(mocks.deactivate.mock.calls[1]?.[2]).toBe(mocks.deactivate.mock.calls[0]?.[2])
  })
})
