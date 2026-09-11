import { ApiResponseError, AuthSessionUnavailableError } from '@/lib/api'

export function updateStudentErrorMessage(error: unknown): string {
  if (
    error instanceof AuthSessionUnavailableError ||
    (error instanceof ApiResponseError && error.status === 401)
  ) {
    return 'Sua sessão está inválida ou expirou. Saia e entre novamente.'
  }
  if (error instanceof ApiResponseError) {
    if (error.status === 400) return 'Revise os dados informados.'
    if (error.status === 403) return 'Seu usuário não está autorizado a editar aluno.'
    if (error.status === 404) return 'Aluno não encontrado. Recarregue a lista.'
    if (error.status === 409) {
      switch (error.code) {
        case 'STUDENT_VERSION_CONFLICT':
          return 'Este aluno foi alterado desde que você abriu a edição. Recarregue os dados e tente novamente.'
        case 'STUDENT_EMAIL_ALREADY_EXISTS':
          return 'E-mail já cadastrado.'
        case 'IDEMPOTENCY_KEY_REUSED':
          return 'Esta tentativa é incompatível com os dados enviados. Revise os dados ou inicie uma nova tentativa.'
        case 'OPERATION_IN_PROGRESS':
          return 'A solicitação está em andamento. Aguarde e tente novamente.'
      }
    }
  }
  return 'Não foi possível confirmar a atualização. Tente novamente com os mesmos dados.'
}
