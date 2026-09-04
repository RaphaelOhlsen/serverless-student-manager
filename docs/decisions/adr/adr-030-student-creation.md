# ADR-030 — Criação transacional e idempotente de aluno

**Status:** Approved
**Data:** 2026-09-04

## Contexto

O SRS exige que Administradores e Operadores ativos possam cadastrar alunos,
com matrícula e e-mail únicos mesmo sob concorrência, auditoria imutável e
resposta `201 Created`. O modelo da tabela `students` já prevê o item principal
e os prefixos das reservas de unicidade, mas ainda não fixava a sort key desses
itens nem o contrato completo de `POST /students`.

Esta decisão fecha essas lacunas sem criar tabela, índice, serviço AWS ou fonte
de identidade adicional.

## Endpoint, autenticação e autorização

```http
POST /students
Authorization: Bearer <access-token>
Idempotency-Key: <UUID-canônico>
Content-Type: application/json
```

O JWT Authorizer exige access token válido. A Lambda extrai o Cognito `sub`
somente do contexto autenticado e lê de forma fortemente consistente:

```text
PK = COGNITO#<sub>
SK = AUTHORIZATION
```

Somente `ADMIN` ou `OPERATOR` com `status = ACTIVE` podem criar alunos.
Identidade ausente ou inconsistente, `INVITED`, `INACTIVE` e role não permitida
recebem `403`. A operação não consulta nem modifica Cognito.

## Request

O corpo é um objeto JSON estrito com exatamente os cinco campos obrigatórios:

```json
{
  "fullName": "Maria da Silva",
  "registrationNumber": "MAT-0001",
  "studentEmail": "maria@example.com",
  "phone": "+5527999999999",
  "birthDate": "2010-05-21"
}
```

Campos ausentes, extras, com tipo incorreto ou formato inválido recebem `400`.
O backend gera `studentId`, status, versão, timestamps, campos de autoria,
chaves físicas, atributos de índices, idempotência e auditoria.

## Normalização e validação

- `studentId`: UUIDv4 canônico lowercase, gerado exclusivamente pelo backend;
- `registrationNumber`: trim, uppercase e regex `[A-Z0-9-]{4,20}`; a forma
  normalizada é a forma canônica persistida;
- `studentEmail`: trim, lowercase, máximo de 254 caracteres e sem whitespace ou
  control characters; reutiliza o validador e a gramática canônica de e-mail
  já existente no projeto quando disponível, sem criar regra divergente para
  Students;
- `phone`: forma E.164 canônica, validada por `^\+[1-9][0-9]{7,14}$`;
- `fullName`: trim externo, sequências internas de whitespace reduzidas a um
  espaço, sem control characters, de 3 a 150 caracteres, preservando acentos e
  capitalização;
- `normalizedName`: Unicode NFKC sobre o nome normalizado para exibição, trim,
  whitespace interno reduzido e Unicode case folding, como na ADR-026;
- `birthDate`: `YYYY-MM-DD`, data real de calendário, sem horário ou timezone e
  não futura;
- `status`: `ACTIVE`;
- `version`: integer `1`.

`createdAt` e `updatedAt` usam o mesmo instante UTC da criação. `createdBy` e
`updatedBy` recebem o `userId` do ator autorizado.

## Resposta

O sucesso retorna `201 Created` com exatamente:

```json
{
  "studentId": "9ca82c95-cabf-4f8b-9323-a704fcf70e44",
  "registrationNumber": "MAT-0001",
  "fullName": "Maria da Silva",
  "studentEmail": "maria@example.com",
  "phone": "+5527999999999",
  "birthDate": "2010-05-21",
  "status": "ACTIVE",
  "version": 1,
  "createdAt": "2026-09-04T14:20:00.000Z",
  "updatedAt": "2026-09-04T14:20:00.000Z"
}
```

A resposta não expõe PK/SK, GSIs, valores normalizados, autoria, auditoria ou
metadados de idempotência.

## Modelo físico e unicidade

Item principal:

```text
PK = STUDENT#<studentId>
SK = PROFILE
```

Reserva de matrícula:

```text
PK = UNIQUE#REGISTRATION#<registrationNumber-normalizado>
SK = UNIQUE
studentId = <studentId>
```

Reserva de e-mail:

```text
PK = UNIQUE#EMAIL#<normalizedEmail>
SK = UNIQUE
studentId = <studentId>
```

Os itens técnicos não recebem atributos dos índices de listagem. Lookup e
conflito usam chaves determinísticas, sem `Scan` e sem índice novo.

## Transação DynamoDB

Uma criação bem-sucedida executa uma única `TransactWriteItems` com quatro
operações `Put`:

1. `STUDENT#<studentId> / PROFILE`;
2. `UNIQUE#REGISTRATION#... / UNIQUE`;
3. `UNIQUE#EMAIL#... / UNIQUE`;
4. audit event `STUDENT_CREATED / SUCCESS`.

Cada item impede sobrescrita por condição de inexistência da chave. As duas
reservas tornam matrícula e e-mail únicos entre alunos ativos e inativos sob
concorrência. Falha de qualquer condição cancela toda a transação: não existe
aluno, reserva ou auditoria parcialmente persistido.

Uma colisão somente de matrícula retorna
`409 REGISTRATION_NUMBER_ALREADY_EXISTS`; somente de e-mail retorna
`409 STUDENT_EMAIL_ALREADY_EXISTS`; colisão comprovada de ambos retorna
`409 STUDENT_UNIQUENESS_CONFLICT`. Cancellation reasons e chaves físicas nunca
são expostos ao cliente ou registrados com PII.

## Idempotência

A operação segue a ADR-012 e reutiliza Powertools e a tabela compartilhada:

- `Idempotency-Key` é UUID canônico obrigatório;
- `operation = create-student`;
- o escopo inclui ambiente, ator, operação e chave;
- o fingerprint é calculado sobre os cinco campos de negócio após normalização
  determinística, antes da geração de campos do backend;
- mesma chave e payload retorna exatamente a resposta `201` persistida, sem
  repetir transação ou auditoria;
- mesma chave com payload diferente retorna `409 IDEMPOTENCY_KEY_REUSED`;
- execução concorrente ainda aberta retorna `409 OPERATION_IN_PROGRESS`;
- TTL permanece em 24 horas;
- falha transitória não terminal permite retry pelo mecanismo da ADR-012;
- não é criada nova máquina de estados.

O `ClientRequestToken` de `TransactWriteItems` é derivado deterministicamente
do contexto idempotente em representação compatível com o limite do DynamoDB.
O registro técnico envolve a transação, mas não é um quinto item do conjunto
atômico de negócio.

## Auditoria

O quarto `Put` cria evento append-only com:

```text
eventType     = STUDENT_CREATED
resourceType  = STUDENT
resourceId    = <studentId>
actorId       = <userId autorizado>
result        = SUCCESS
eventId       = <eventId preservado>
correlationId = <correlationId preservado>
occurredAt    = <instante UTC preservado>
changes       = status null -> ACTIVE; version null -> 1
```

O objeto `changes` canônico é:

```json
{
  "status": {"from": null, "to": "ACTIVE"},
  "version": {"from": null, "to": 1}
}
```

O evento usa as chaves, índices e retenção das ADR-015 e ADR-021. Não contém
e-mail, telefone ou corpo integral. `eventId`, `correlationId` e `occurredAt`
são gerados uma vez no contexto idempotente e preservados em retries/replays.

## Erros

Erros usam o envelope canônico do SRS:

```json
{
  "code": "INVALID_REQUEST",
  "message": "Invalid student creation request",
  "correlationId": "request-correlation-id",
  "details": []
}
```

| Situação | HTTP | Código |
|---|---:|---|
| JSON, content type, campos, tipos ou formatos inválidos | `400` | `INVALID_REQUEST` |
| JWT ausente ou inválido | `401` | `UNAUTHORIZED` |
| Ator não autorizado ou não `ACTIVE` | `403` | `FORBIDDEN` |
| Matrícula já existente | `409` | `REGISTRATION_NUMBER_ALREADY_EXISTS` |
| E-mail já existente | `409` | `STUDENT_EMAIL_ALREADY_EXISTS` |
| Matrícula e e-mail já existentes | `409` | `STUDENT_UNIQUENESS_CONFLICT` |
| Chave idempotente reutilizada com outro payload | `409` | `IDEMPOTENCY_KEY_REUSED` |
| Operação da mesma chave ainda em andamento | `409` | `OPERATION_IN_PROGRESS` |
| Falha inesperada | `500` | `INTERNAL_ERROR` |

Mensagens e detalhes não revelam PK/SK, estado interno, stack trace ou PII
desnecessária.

## IAM e infraestrutura

A `students-api` receberá somente:

- ações necessárias a `TransactWriteItems` nas tabelas `students` e
  `audit-events`;
- `PutItem` nessas tabelas condicionado a
  `dynamodb:EnclosingOperation = TransactWriteItems`;
- ações mínimas exigidas pelo mecanismo ADR-012 na tabela `idempotency`;
- nomes das tabelas de auditoria e idempotência por configuração.

A leitura existente de AUTHORIZATION é preservada. Não há permissão Cognito,
nova tabela, novo índice ou mudança do modelo físico provisionado. A HTTP API
receberá somente a rota JWT `POST /students` integrada à `students-api`.

## Consequências

### Positivas

- criação, reservas e auditoria de sucesso são atômicas;
- retries não duplicam alunos ou eventos;
- unicidade resiste à concorrência sem `Scan`;
- autorização continua baseada no estado atual do DynamoDB;
- dados pessoais não são copiados para auditoria ou idempotência.

### Negativas

- o serviço precisa distinguir condições de unicidade canceladas sem expor
  cancellation reasons;
- a escrita passa a envolver três tabelas e permissões IAM adicionais;
- o frontend deve preservar a chave idempotente em falhas recuperáveis e
  descartá-la após sucesso ou erro definitivo.

## Relação com decisões anteriores

- **ADR-003:** mantém HTTP API e JWT Authorizer.
- **ADR-005:** especializa a escrita transacional na tabela por domínio.
- **ADR-006:** mantém Cognito para autenticação e DynamoDB para role/status.
- **ADR-012:** reutiliza idempotência HTTP e sua tabela compartilhada.
- **ADR-015 e ADR-021:** reutiliza retenção e modelo físico da auditoria.
- **ADR-023:** reutiliza `COGNITO#<sub> / AUTHORIZATION` para autorização.
- **ADR-026:** mantém os índices, normalização de nome e contrato de listagem;
  itens técnicos não participam dos GSIs.
- **ADR-029:** não amplia a exceção de `INVITED`; criação é operação de negócio
  e exige `ACTIVE`.

## Impacto de implementação após aprovação

Backend deverá adicionar validação, serviço, repositórios, idempotência,
transação e rota. Terraform deverá adicionar a rota e o IAM mínimo descrito.
Frontend deverá adicionar formulário e estados de criação sem expor campos
internos. Testes devem cobrir validação, autorização, replay, concorrência,
conflitos isolados/conjuntos, atomicidade, envelope seguro e infraestrutura.

Implementação, apply, release e teste E2E permanecem fora desta decisão
documental.
