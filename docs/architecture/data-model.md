# Modelo de dados

**Versão:** 2.7
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

Tabela com chave composta `PK` + `SK`, conforme ADR-023.

### Item principal do usuário

```text
PK = USER#<userId>
SK = PROFILE
```

Atributos principais:

```text
userId
cognitoSub
fullName
normalizedName
email
role
status
authVersion
createdAt
createdBy
updatedAt
updatedBy
```

### Unicidade de e-mail

```text
PK = UNIQUE#EMAIL#<normalizedEmail>
SK = UNIQUE
```

O item referencia o `userId` e é criado com condição de não existência.

### Projeção de autorização Cognito

```text
PK = COGNITO#<cognitoSub>
SK = AUTHORIZATION
```

Atributos:

```text
userId
role
status
authVersion
```

Essa projeção é utilizada para autorização por Cognito `sub`.

### Controle de Administradores ativos

```text
PK = CONTROL#ACTIVE_ADMIN_COUNT
SK = CONTROL
activeAdminCount = <inteiro >= 0>
```

`activeAdminCount` armazena a quantidade de usuários com `role = ADMIN` e `status = ACTIVE`.

O contador é protegido transacionalmente.

Usuários com status `INVITED` não participam do contador.

### Trava singleton do primeiro Administrador

```text
PK = CONTROL#FIRST_ADMIN_BOOTSTRAP
SK = CONTROL
```

Atributos:

```text
userId
operationId
createdAt
createdBy
```

O marker:

- é permanente e não possui TTL;
- é criado exclusivamente pela transação do bootstrap inicial;
- nunca é removido automaticamente;
- impede que outra operação materialize um segundo "primeiro Admin".

O bootstrap inicial usa uma única `TransactWriteItems` com cinco operações `Put` atômicas:

1. USER profile;
2. UNIQUE EMAIL;
3. COGNITO projection;
4. `CONTROL#FIRST_ADMIN_BOOTSTRAP / CONTROL`;
5. audit event `USER_CREATED`.

Todos os itens impedem sobrescrita por condição de inexistência. O item `CONTROL#ACTIVE_ADMIN_COUNT / CONTROL` não participa enquanto o usuário estiver `INVITED`.

### GSI

```text
gsi-all-users-name

GSI1PK = USERS
GSI1SK = NAME#<normalizedName>#USER#<userId>
```

Somente itens `USER#<userId> / PROFILE` participam do índice.

O índice suporta:

- listagem paginada por nome com `Query`;
- pesquisa por prefixo de nome normalizado;
- ordenação determinística para usuários com nomes iguais.

Busca exata por e-mail utiliza o item `UNIQUE#EMAIL#<normalizedEmail> / UNIQUE`, sem `Scan`.

### Normalização

Nome:

```text
normalizedName
```

é produzido com Unicode NFKC, trim, redução de whitespace interno e Unicode case folding.

E-mail:

```text
normalizedEmail = trim(email).lower()
```

O e-mail persistido no perfil utiliza a forma normalizada.

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

- protocolo de estados compatível com a origem e a operação;
- hash de payload;
- resposta técnica mínima;
- TTL de 24 horas;
- proteção de writes repetidos.

A tabela é compartilhada, mas suas máquinas de estado não são artificialmente unificadas:

- fluxos HTTP podem utilizar `INPROGRESS` e `COMPLETE`, conforme ADR-012;
- operações não HTTP utilizam máquinas de estados próprias, conforme ADR-018 e suas especializações;
- `bootstrap-admin` utiliza os estados e as transições normais e excepcionais definidos pela ADR-024;
- `resume-first-admin-invitation` utiliza `STARTED`, `COMPLETED` e `RECONCILIATION_REQUIRED`, conforme ADR-024.

### Bootstrap do primeiro Administrador

O registro idempotente de `bootstrap-admin` preserva:

```text
userId
eventId
correlationId
operationId
payloadHash
occurredAt
auditExpiresAt
actorId
createdAt
updatedAt
expiration
```

`fullName` e e-mail não são duplicados nesse registro. Em replay, o payload original é reapresentado, normalizado deterministicamente e validado pelo `payloadHash` antes de qualquer reconstrução ou efeito.

O token da transação é derivado deterministicamente:

```text
ClientRequestToken = operationId
```

`clientRequestToken` não é persistido como atributo separado.

Os IDs técnicos são UUIDv4 canônicos e os timestamps de criação usam UTC RFC3339 com precisão de milissegundos e sufixo `Z`, conforme ADR-024.

Após o TTL de 24 horas, o marker permanente continua protegendo contra um novo bootstrap. A operação `resume-first-admin-invitation` pode retomar somente o convite do mesmo `ADMIN` em estado `INVITED`, depois da reconciliação completa, sem criar ou alterar USER, UNIQUE EMAIL, COGNITO projection ou marker.

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

Essa recuperação da ADR-019 é exclusiva para um `ADMIN` `ACTIVE` sem acesso ao TOTP e não se confunde com `resume-first-admin-invitation`, restrita ao primeiro Admin ainda `INVITED`.
