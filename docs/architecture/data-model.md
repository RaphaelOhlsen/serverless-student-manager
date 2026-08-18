# Modelo de dados

**Versão:** 2.5
**Status:** Approved

## 1. Estratégia

Três tabelas de negócio e uma tabela técnica:

```text
students
users
audit-events
idempotency
```

Modelagem orientada a access patterns.  
`Scan` não faz parte dos fluxos normais.

## 2. `students`

### Chave primária

Tabela com chave composta `PK` + `SK`.

Item principal do estudante:

```text
PK = STUDENT#<studentId>
SK = PROFILE
```

Itens técnicos de unicidade continuam fazendo parte do modelo:

```text
UNIQUE#REGISTRATION#<registrationNumber>
UNIQUE#EMAIL#<normalizedEmail>
```

A convenção de `SK` dos itens técnicos de unicidade será definida junto ao fluxo de escrita.

### GSIs

```text
gsi-status-name
gsi-all-name
```

### Regras

- matrícula única e imutável;
- e-mail único;
- telefone obrigatório e não único;
- nome normalizado para ordenação/prefixo;
- status `ACTIVE`/`INACTIVE`;
- paginação por cursor;
- controle otimista por `version`;
- unicidade mantida com transação DynamoDB.

## 3. `users`

Tabela com PK simples `PK`.

Itens:

```text
USER#<userId>
UNIQUE#EMAIL#<normalizedEmail>
COGNITO#<cognitoSub>
CONTROL#ACTIVE_ADMIN_COUNT
```

GSI:

```text
gsi-all-users-name
```

Projeção de autorização:

```text
userId
role
status
authVersion
```

O contador de Administradores ativos é protegido transacionalmente.

## 4. `audit-events`

Chave composta:

```text
PK = RESOURCE#<resourceType>#<resourceId>
SK = TS#<occurredAt>#EVENT#<eventId>
```

GSIs:

```text
gsi-actor-time
gsi-correlation-time
gsi-period-time
```

Chaves físicas dos índices, conforme ADR-021:

```text
GSI1PK = ACTOR#<actorId>
GSI1SK = TS#<occurredAt>#EVENT#<eventId>

GSI2PK = CORRELATION#<correlationId>
GSI2SK = TS#<occurredAt>#EVENT#<eventId>

GSI3PK = PERIOD#<YYYY-MM>
GSI3SK = TS#<occurredAt>#EVENT#<eventId>
```

Regras:

- append-only;
- sem `UpdateItem`/`DeleteItem` para Lambdas normais;
- sem cópia completa de PII;
- consulta por recurso, ator, correlação e período;
- sucesso incluído na transação de negócio quando possível;
- TTL via `expiresAt`.

## 5. `idempotency`

Tabela técnica compartilhada.

Objetivos:

- estado `INPROGRESS`/`COMPLETE`;
- hash de payload;
- resposta técnica mínima;
- TTL de 24 horas;
- proteção de writes repetidos.

## 6. Consistência

- tabela base pode usar leitura fortemente consistente;
- GSIs são eventualmente consistentes;
- atualizações usam `version`;
- unicidade usa transações;
- `COGNITO#<sub>` é consultado com leitura fortemente consistente para autorização.


### Recuperação excepcional de identidade

Em cenário break-glass aprovado pela ADR-019:

```text
USER#<userId>        permanece
COGNITO#<oldSub>     é removido
COGNITO#<newSub>     é criado
authVersion          é incrementado
```

O histórico de auditoria não é reescrito.
