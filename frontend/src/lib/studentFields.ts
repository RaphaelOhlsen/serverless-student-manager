export type MutableStudentFields = {
  fullName: string
  studentEmail: string
  phone: string
  birthDate: string
}

export const mutableStudentFieldNames = [
  'fullName',
  'studentEmail',
  'phone',
  'birthDate',
] as const satisfies readonly (keyof MutableStudentFields)[]

// Python str.isspace() (used by the backend strip/split), including C0 separators.
// eslint-disable-next-line no-control-regex -- Required to mirror Python whitespace exactly.
const whitespace = /[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/u
const controls = /\p{C}/u

function trim(value: string): string {
  return value.replace(
    new RegExp(`^${whitespace.source}|${whitespace.source}$`, 'gu'),
    '',
  )
}

export function normalizeMutableStudentFields(
  input: MutableStudentFields,
): MutableStudentFields {
  return {
    ...input,
    fullName: trim(input.fullName).split(whitespace).join(' '),
    studentEmail: trim(input.studentEmail).toLowerCase(),
  }
}

export function validateMutableStudentFields(
  raw: MutableStudentFields,
  value: MutableStudentFields,
): string | null {
  if (
    controls.test(raw.fullName) ||
    [...value.fullName].length < 3 ||
    [...value.fullName].length > 150
  ) {
    return 'Informe um nome de 3 a 150 caracteres, sem caracteres de controle.'
  }
  if (
    !value.studentEmail ||
    [...value.studentEmail].length > 254 ||
    whitespace.test(value.studentEmail) ||
    controls.test(value.studentEmail)
  ) {
    return 'Informe um e-mail de até 254 caracteres, sem espaços ou caracteres de controle.'
  }
  if (!/^\+[1-9][0-9]{7,14}$/.test(value.phone)) {
    return 'Informe o telefone com +, código do país e números (E.164).'
  }
  const date = value.birthDate
  const parsed = new Date(date + 'T00:00:00.000Z')
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(date) ||
    date < '0001-01-01' ||
    !Number.isFinite(parsed.getTime()) ||
    parsed.toISOString().slice(0, 10) !== date ||
    date > new Date().toISOString().slice(0, 10)
  ) {
    return 'Informe uma data de nascimento válida, não futura.'
  }
  return null
}

export function normalizeRegistrationNumber(value: string): string {
  return trim(value).toUpperCase()
}

export function validateRegistrationNumber(value: string): string | null {
  return /^[A-Z0-9-]{4,20}$/.test(value)
    ? null
    : 'Informe uma matrícula de 4 a 20 letras, números ou hífens.'
}
