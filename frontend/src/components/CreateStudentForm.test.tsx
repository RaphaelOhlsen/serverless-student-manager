/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ create: vi.fn() }))
vi.mock('@/lib/api', async (original) => ({ ...await original<typeof import('@/lib/api')>(), createStudent: mocks.create }))
import { ApiResponseError, AuthSessionUnavailableError } from '@/lib/api'
import { CreateStudentForm } from './CreateStudentForm'
const body = { fullName: 'Aluno Teste', registrationNumber: 'MAT-001', studentEmail: 'a@example.com', phone: '+15555550123', birthDate: '2000-01-15' }
const labels = { fullName: 'Nome completo', registrationNumber: 'Matrícula', studentEmail: 'E-mail', phone: 'Telefone', birthDate: 'Data de nascimento' }
function fill(values = body) {
  for (const name of Object.keys(values) as (keyof typeof body)[]) fireEvent.change(screen.getByLabelText(labels[name]), { target: { value: values[name] } })
}
function submit() { fireEvent.submit(screen.getByRole('form', { name: 'Novo aluno' })) }
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks() })
beforeEach(() => { mocks.create.mockReset() })
describe('CreateStudentForm', () => {
  it('cancels without creating a key or sending a request', () => {
    const cancel = vi.fn(); const uuid = vi.spyOn(crypto, 'randomUUID')
    render(<CreateStudentForm onCreated={vi.fn()} onCancel={cancel} />)
    fireEvent.click(screen.getByText('Cancelar')); expect(cancel).toHaveBeenCalledOnce(); expect(uuid).not.toHaveBeenCalled()
  })
  it.each(Object.keys(body) as (keyof typeof body)[])('requires %s before generating a key', (field) => {
    const uuid = vi.spyOn(crypto, 'randomUUID')
    render(<CreateStudentForm onCreated={vi.fn()} onCancel={vi.fn()} />); fill({ ...body, [field]: '' }); submit()
    expect(screen.getByRole('alert')).toBeTruthy(); expect(mocks.create).not.toHaveBeenCalled(); expect(uuid).not.toHaveBeenCalled()
  })
  it.each([
    ['fullName', 'ab'], ['fullName', 'a'.repeat(151)], ['fullName', 'Aluno\tTeste'], ['fullName', 'Aluno\u200bTeste'],
    ['phone', '555123'], ['birthDate', '2999-01-01'], ['birthDate', '2000-02-30'], ['birthDate', '0000-01-01'],
    ['registrationNumber', 'ABC'], ['studentEmail', 'a b'], ['studentEmail', 'a'.repeat(255)],
  ])('rejects invalid %s', (field, value) => {
    render(<CreateStudentForm onCreated={vi.fn()} onCancel={vi.fn()} />); fill({ ...body, [field]: value }); submit()
    expect(screen.getByRole('alert')).toBeTruthy(); expect(mocks.create).not.toHaveBeenCalled()
  })
  it.each(['Á'.repeat(3), 'Á'.repeat(150), '😀'.repeat(150)])('accepts canonical name boundaries', async (fullName) => {
    mocks.create.mockResolvedValue({}); render(<CreateStudentForm onCreated={vi.fn()} onCancel={vi.fn()} />)
    fill({ ...body, fullName }); submit(); await waitFor(() => expect(mocks.create).toHaveBeenCalledOnce())
  })
  it('normalizes names, registration and email without imposing email grammar', async () => {
    mocks.create.mockResolvedValue({}); render(<CreateStudentForm onCreated={vi.fn()} onCancel={vi.fn()} />)
    fill({ ...body, fullName: '  Áluno   Teste  ', registrationNumber: ' mat-001 ', studentEmail: ' SIMPLE ' }); submit()
    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith({ ...body, fullName: 'Áluno Teste', studentEmail: 'simple' }, expect.stringMatching(/^[0-9a-f-]{36}$/)))
  })
  it('blocks concurrent submit and cancellation while pending', async () => {
    let resolve!: (value: object) => void
    mocks.create.mockReturnValue(new Promise((r) => { resolve = r }))
    const cancel = vi.fn(); render(<CreateStudentForm onCreated={vi.fn()} onCancel={cancel} />); fill(); submit(); submit()
    expect(mocks.create).toHaveBeenCalledOnce(); expect((screen.getByText('Cancelar') as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByRole('status').textContent).toContain('Salvando'); fireEvent.click(screen.getByText('Cancelar')); expect(cancel).not.toHaveBeenCalled()
    await act(async () => resolve({}))
  })
  it.each([
    [400, undefined, 'Revise os dados informados.'], [401, undefined, 'Sua sessão está inválida'],
    [403, undefined, 'não está autorizado'], [409, 'REGISTRATION_NUMBER_ALREADY_EXISTS', 'Matrícula já cadastrada.'],
    [409, 'STUDENT_EMAIL_ALREADY_EXISTS', 'E-mail já cadastrado.'], [409, 'STUDENT_UNIQUENESS_CONFLICT', 'Matrícula e e-mail já cadastrados.'],
    [409, 'IDEMPOTENCY_KEY_REUSED', 'tentativa é incompatível'], [409, 'OPERATION_IN_PROGRESS', 'A solicitação está em andamento.'],
    [500, undefined, 'Não foi possível confirmar'],
  ])('maps %s %s safely', async (status, code, message) => {
    mocks.create.mockRejectedValue(new ApiResponseError(status as number, code as string | undefined))
    render(<CreateStudentForm onCreated={vi.fn()} onCancel={vi.fn()} />); fill(); submit()
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain(message)); expect(mocks.create).toHaveBeenCalledOnce()
  })
  it.each([new TypeError('network'), new ApiResponseError(500), new ApiResponseError(201), new ApiResponseError(409, 'OPERATION_IN_PROGRESS')])('preserves the key for recoverable failures', async (failure) => {
    mocks.create.mockRejectedValue(failure); render(<CreateStudentForm onCreated={vi.fn()} onCancel={vi.fn()} />); fill(); submit()
    await screen.findByRole('alert'); fill({ ...body, fullName: ' Aluno  Teste ', registrationNumber: ' mat-001 ', studentEmail: ' A@EXAMPLE.COM ' }); submit()
    await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(2)); expect(mocks.create.mock.calls[1][1]).toBe(mocks.create.mock.calls[0][1])
  })
  it('uses a new key after semantic payload change', async () => {
    mocks.create.mockRejectedValue(new ApiResponseError(500)); render(<CreateStudentForm onCreated={vi.fn()} onCancel={vi.fn()} />); fill(); submit()
    await screen.findByRole('alert'); fill({ ...body, fullName: 'Outro Aluno' }); submit()
    await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(2)); expect(mocks.create.mock.calls[1][1]).not.toBe(mocks.create.mock.calls[0][1])
  })
  it('ends the attempt after success', async () => {
    mocks.create.mockResolvedValue({}); const created = vi.fn(); render(<CreateStudentForm onCreated={created} onCancel={vi.fn()} />); fill(); submit()
    await waitFor(() => expect(created).toHaveBeenCalledOnce()); submit(); await waitFor(() => expect(created).toHaveBeenCalledTimes(2))
    expect(mocks.create.mock.calls[1][1]).not.toBe(mocks.create.mock.calls[0][1])
  })
  it('maps unavailable session without exposing details', async () => {
    mocks.create.mockRejectedValue(new AuthSessionUnavailableError()); render(<CreateStudentForm onCreated={vi.fn()} onCancel={vi.fn()} />); fill(); submit()
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('sessão está inválida'))
  })
  it('ignores a late response after unmount', async () => {
    let resolve!: (value: object) => void; mocks.create.mockReturnValue(new Promise((r) => { resolve = r }))
    const created = vi.fn(); const view = render(<CreateStudentForm onCreated={created} onCancel={vi.fn()} />); fill(); submit(); view.unmount()
    await act(async () => resolve({})); expect(created).not.toHaveBeenCalled()
  })
})
