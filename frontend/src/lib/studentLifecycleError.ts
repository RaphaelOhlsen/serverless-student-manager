import { ApiResponseError, AuthSessionUnavailableError } from '@/lib/api'

export function studentLifecycleErrorMessage(error: unknown): string {
  if (error instanceof AuthSessionUnavailableError) {
    return 'Sua sessão não está disponível. Entre novamente.'
  }
  if (!(error instanceof ApiResponseError)) {
    return 'Não foi possível atualizar o status do aluno. Tente novamente.'
  }
  if (error.status === 400) return 'A solicitação é inválida. Revise os dados.'
  if (error.status === 401) return 'Sua sessão expirou. Entre novamente.'
  if (error.status === 403) return 'Você não tem permissão para esta ação.'
  if (error.status === 404) return 'Aluno não encontrado.'
  if (error.status === 409 && error.code === 'STUDENT_VERSION_CONFLICT') {
    return 'Os dados do aluno foram alterados. Atualize e tente novamente.'
  }
  if (error.status === 409 && error.code === 'IDEMPOTENCY_KEY_REUSED') {
    return 'Esta tentativa é incompatível com uma operação anterior. Tente novamente.'
  }
  if (error.status === 409 && error.code === 'OPERATION_IN_PROGRESS') {
    return 'Esta operação ainda está em andamento. Tente novamente em instantes.'
  }
  return 'Não foi possível atualizar o status do aluno. Tente novamente.'
}
