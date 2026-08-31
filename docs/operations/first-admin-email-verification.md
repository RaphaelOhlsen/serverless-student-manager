# Runbook — Verificação do e-mail do primeiro Administrador

**Status:** Approved
**Data:** 2026-08-31
**ADRs relacionadas:** ADR-015, ADR-018, ADR-021, ADR-022, ADR-024 e ADR-025

## 1. Objetivo

Definir o protocolo operacional de implementação de `verify-first-admin-email`,
operação que corrige exclusivamente o atributo `email_verified` da identidade
Cognito histórica do primeiro Administrador.

Este runbook detalha a ADR-025 sem alterar suas decisões. Em particular, a
confirmação da auditoria é obrigatória antes de `COMPLETED`, mas não é
pré-condição absoluta para registrar `RECONCILIATION_REQUIRED`.

## 2. Escopo e identidade lógica

```text
operation = verify-first-admin-email
target    = first-admin
```

O payload lógico é exatamente:

```json
{"target":"first-admin"}
```

O registro idempotente usa:

```text
NONHTTP#<environment>#verify-first-admin-email#first-admin#<operationId>
```

O operador fornece somente `operationId` e a autoria operacional. Não fornece
`userId`, e-mail, nome completo nem `cognitoSub`.

## 3. Estados

A máquina de estados possui somente:

```text
STARTED → COMPLETED
STARTED → RECONCILIATION_REQUIRED
```

`COMPLETED` e `RECONCILIATION_REQUIRED` são terminais. Falhas recuperáveis ou
inconclusivas podem manter `STARTED`. Nenhum novo estado é introduzido.

## 4. Schema do registro idempotente

O registro `STARTED` possui, no mínimo:

```text
id
environment
operation
target
operationId
payloadHash
state
eventId
correlationId
occurredAt
auditExpiresAt
actorId
createdAt
updatedAt
expiration
```

`payloadHash` é o SHA-256 hexadecimal lowercase da serialização canônica
`{"target":"first-admin"}`, com chaves ordenadas, UTF-8 e
`separators=(",", ":")`.

O registro tem TTL técnico de 24 horas. Ele não persiste dados descobertos do
usuário nem dados pessoais.

## 5. Metadados determinísticos

Para uma nova operação, gerar uma única vez e persistir em `STARTED`:

```text
eventId
correlationId
occurredAt
auditExpiresAt
actorId
```

`operationId`, `eventId` e `correlationId` são UUIDv4 textuais canônicos.
Nenhum deles é regenerado durante retry ou replay.

`occurredAt` é capturado uma única vez em UTC RFC3339, com precisão de
milissegundos e sufixo `Z`. O mesmo valor é usado como timestamp determinístico
do audit event. `createdAt` usa esse instante inicial; `updatedAt` pode mudar em
uma transição de estado.

`auditExpiresAt` é calculado uma única vez a partir de `occurredAt`, em Unix
epoch seconds, seguindo a ADR-015:

```text
dev  = 90 dias
prod = 5 anos
```

O `actorId` original é preservado. Um executor posterior pode aparecer em logs
operacionais sanitizados, mas não substitui a autoria persistida.

## 6. Validação e replay do contexto

Antes de qualquer leitura de negócio ou Cognito, validar:

1. `operationId` como UUIDv4 canônico;
2. identidade física do registro;
3. `environment`, `operation` e `target`;
4. todos os campos obrigatórios e seus tipos;
5. UUIDs e timestamps determinísticos;
6. estado permitido;
7. `payloadHash` contra o payload canônico.

Contexto incompatível falha sem discovery, mutação Cognito, auditoria ou
transição.

## 7. Discovery autoritativo

Em `STARTED`, reconstruir o alvo por:

```text
CONTROL#FIRST_ADMIN_BOOTSTRAP / CONTROL
  → userId
  → USER#<userId> / PROFILE
  → cognitoSub
  → COGNITO#<cognitoSub> / AUTHORIZATION
  → Cognito AdminGetUser
```

Validar marker, `userId`, `role=ADMIN`, status `INVITED` ou `ACTIVE`, USER,
projeção, `authVersion`, `Username` técnico, `sub`, e-mail normalizado e
`email_verified`.

As classificações são exatamente:

```text
NEEDS_VERIFICATION
ALREADY_VERIFIED
RECONCILIATION_REQUIRED
```

Falha técnica inconclusiva de leitura é propagada e mantém `STARTED`.
Incompatibilidade comprovada conduz ao caminho excepcional.

## 8. Única mutação Cognito permitida

Somente `NEEDS_VERIFICATION` autoriza:

```text
AdminUpdateUserAttributes(
  UserPoolId=<userPoolId>,
  Username=<userId técnico>,
  UserAttributes=[
    {"Name": "email_verified", "Value": "true"}
  ]
)
```

Não enviar o atributo `email`. Não executar retry interno nem uma segunda
mutação na mesma invocação.

## 9. Read-back obrigatório

Uma resposta de sucesso de `AdminUpdateUserAttributes` não comprova o efeito.
Depois de resultado bem-sucedido ou ambíguo, repetir o discovery completo.

Somente `ALREADY_VERIFIED`, com a mesma identidade, mesmo `sub` e mesmo e-mail,
confirma funcionalmente o sucesso. `NEEDS_VERIFICATION` mantém o fluxo
retomável em `STARTED`; `RECONCILIATION_REQUIRED` interrompe novas mutações.
Uma leitura inconclusiva segue a classificação de falhas da ADR-025.

## 10. Taxonomia da auditoria

Cada `operationId` possui no máximo um audit event terminal determinístico,
identificado pelo `eventId` persistido.

```text
eventType = FIRST_ADMIN_EMAIL_VERIFICATION
```

O mesmo `eventType` é usado nos dois resultados:

```text
COMPLETED               → result = SUCCESS
RECONCILIATION_REQUIRED → result = FAILURE
```

Para este evento, `FAILURE` significa conclusão excepcional que exige
reconciliação operacional. Não são criados eventos separados para `STARTED`,
chamada Cognito, retry, timeout, read-back ou replay.

## 11. Modelo físico do audit event

O evento reutiliza a tabela `audit-events` e a modelagem da ADR-021:

```text
PK = RESOURCE#USER#<userId>
SK = TS#<occurredAt>#EVENT#<eventId>

GSI1PK = ACTOR#<actorId>
GSI1SK = TS#<occurredAt>#EVENT#<eventId>

GSI2PK = CORRELATION#<correlationId>
GSI2SK = TS#<occurredAt>#EVENT#<eventId>

GSI3PK = PERIOD#<YYYY-MM>
GSI3SK = TS#<occurredAt>#EVENT#<eventId>
```

Campos do evento:

```text
PK
SK
eventId
eventType = FIRST_ADMIN_EMAIL_VERIFICATION
resourceType = USER
resourceId = <userId autoritativo>
actorId = <actorId original>
actorType = OPERATIONAL_WORKFLOW
operationId
occurredAt
result = SUCCESS | FAILURE
correlationId
GSI1PK
GSI1SK
GSI2PK
GSI2SK
GSI3PK
GSI3SK
expiresAt = <auditExpiresAt>
```

O modelo lógico aprovado reconhece `actorType=OPERATIONAL_WORKFLOW`, e a
ADR-025 exige correlação pelo `operationId`, mas o builder atual de
`USER_CREATED` ainda não emite esses dois campos. A implementação futura deve
estender minimamente o builder específico desta operação para incluí-los; não
deve alterar a modelagem física, criar índice ou mudar o builder do bootstrap
sem necessidade.

O evento não precisa de `changes`. Se um builder comum vier a exigir esse
campo, sua definição dependerá de aprovação específica e não poderá carregar
e-mail nem atributos Cognito pessoais.

## 12. Imutabilidade e confirmação semântica

A escrita é append-only, por `PutItem` condicional equivalente a:

```text
attribute_not_exists(PK) AND attribute_not_exists(SK)
```

Não usar `UpdateItem`, overwrite ou `DeleteItem` para reparar um evento.

Depois de toda tentativa de escrita, ou quando a condição indicar que o evento
já existe, executar leitura fortemente consistente pela chave primária. A
confirmação compara todos os campos determinísticos do schema acima. Um evento
somente é confirmado quando é semanticamente idêntico ao esperado.

## 13. Ausência de PII

O registro idempotente, o audit event, resultados e diagnósticos normais não
incluem:

```text
email
fullName
cognitoSub
senha
temporaryPassword
token ou tokens
TOTP
atributos Cognito pessoais
```

Não persistir hash ou representação reversível desses dados. O e-mail pode
existir somente em memória durante a reconciliação. `resourceId=userId` é um
identificador técnico permitido.

## 14. Fluxo `ALREADY_VERIFIED`

```text
STARTED
→ discovery ALREADY_VERIFIED
→ zero mutações Cognito
→ materializar ou reconciliar audit SUCCESS
→ leitura consistente e confirmação semântica
→ COMPLETED
```

A operação é auditada mesmo quando o estado desejado já estava satisfeito.

## 15. Fluxo `NEEDS_VERIFICATION`

```text
STARTED
→ discovery NEEDS_VERIFICATION
→ AdminUpdateUserAttributes(email_verified=true)
→ discovery/read-back ALREADY_VERIFIED
→ materializar ou reconciliar audit SUCCESS
→ leitura consistente e confirmação semântica
→ COMPLETED
```

Se o read-back ainda for `NEEDS_VERIFICATION`, não declarar sucesso e não
repetir a mutação na mesma invocação. A falha original, quando houver, é
propagada e `STARTED` é preservado para retry controlado.

## 16. Regra forte para `COMPLETED`

`STARTED → COMPLETED` somente ocorre depois de:

1. sucesso funcional comprovado por discovery/read-back;
2. audit event `SUCCESS` materializado ou encontrado;
3. leitura consistente do evento;
4. compatibilidade semântica integral confirmada.

Falha recuperável ou inconclusiva da infraestrutura de auditoria mantém
`STARTED`. Incompatibilidade comprovada do evento conduz a
`RECONCILIATION_REQUIRED`. Dúvida de auditoria nunca autoriza repetição cega da
mutação Cognito.

## 17. Regra excepcional para `RECONCILIATION_REQUIRED`

Quando uma incompatibilidade de domínio, identidade ou auditoria determinar o
resultado excepcional, tentar materializar e confirmar o evento `FAILURE` se
isso puder ser feito com segurança.

A confirmação desse evento não é pré-condição absoluta para a transição:

```text
resultado excepcional determinado
→ tentar audit FAILURE
→ audit confirmado ou auditoria ausente/incompatível/indisponível
→ RECONCILIATION_REQUIRED
```

Falha da própria auditoria não deixa artificialmente a operação em `STARTED`.
A trilha de auditoria pode ficar incompleta e exigir investigação, mas o estado
terminal excepcional deve ser preservado. Não gerar um segundo `eventId`.

## 18. Falhas de escrita da auditoria

### Caminho de `SUCCESS`

Em falha explicitamente anterior ao Put, manter `STARTED`, propagar diagnóstico
sanitizado e não transicionar. Em resultado ambíguo:

1. não repetir imediatamente o Put;
2. ler consistentemente o `eventId` esperado;
3. evento compatível confirma a auditoria;
4. ausência confirmada mantém `STARTED` e permite retry posterior;
5. leitura inconclusiva mantém `STARTED`;
6. evento incompatível exige `RECONCILIATION_REQUIRED`.

### Caminho de `FAILURE`

Tentar a mesma reconciliação por leitura consistente. Evento compatível confirma
a auditoria. Ausência, incompatibilidade ou indisponibilidade não bloqueia
`RECONCILIATION_REQUIRED` e não autoriza novo efeito Cognito.

## 19. Audit event incompatível

Se o `eventId` persistido apontar para evento semanticamente incompatível:

- não sobrescrever nem excluir;
- não gerar novo `eventId`;
- não criar outro audit event;
- não executar nova mutação Cognito;
- emitir diagnóstico sanitizado quando possível;
- transicionar para `RECONCILIATION_REQUIRED`.

A incompatibilidade da auditoria é uma causa de reconciliação operacional.

## 20. Replay

### Estado `STARTED`

Após validar integralmente contexto e payload, repetir a reconciliação read-only
e obter o `userId` autoritativo. Consultar consistentemente o audit event
determinístico antes de qualquer possível nova mutação:

- audit `SUCCESS` canônico: não chamar Cognito; reconciliar somente `COMPLETED`;
- audit `FAILURE` canônico: não chamar Cognito; reconciliar somente
  `RECONCILIATION_REQUIRED`;
- audit incompatível: não chamar Cognito; registrar
  `RECONCILIATION_REQUIRED`;
- audit ausente: usar o discovery integral para decidir o próximo passo.

Nunca presumir que uma mutação anterior falhou apenas porque o registro ainda
está em `STARTED`.

### Estados terminais

Replay de `COMPLETED` retorna sucesso sem discovery, auditoria, transição ou
mutação Cognito.

Replay de `RECONCILIATION_REQUIRED` retorna o estado terminal sem discovery,
auditoria, transição, reparo ou mutação Cognito. Reparo de auditoria ausente ou
corrompida pertence a procedimento operacional separado e explicitamente
autorizado.

## 21. Writes idempotentes ambíguos

Falha condicional ou ambígua ao criar `STARTED` exige leitura consistente do
registro. Registro canônico compatível é reutilizado; ausência confirmada
preserva a falha para retry; registro incompatível falha antes de qualquer
efeito. Nunca fabricar outro `operationId`.

Depois de uma transição terminal ambígua, ler consistentemente e validar todo o
contexto:

- estado esperado: considerar confirmado;
- ainda `STARTED` após intenção de `COMPLETED`: não repetir Cognito; audit
  `SUCCESS` confirmado funciona como barreira e o replay tenta somente a
  transição pendente;
- ainda `STARTED` após intenção de `RECONCILIATION_REQUIRED`: não executar
  Cognito; o replay converge somente para o terminal excepcional;
- estado incompatível: interromper efeitos e exigir investigação.

Cada tentativa lógica de transição executa no máximo um `UpdateItem`; read-back
reconcilia resultados condicionais ou ambíguos antes de nova decisão.

## 22. Efeitos proibidos

A operação não pode executar:

```text
AdminCreateUser
AdminDeleteUser
AdminDisableUser
AdminEnableUser
AdminUserGlobalSignOut
AdminSetUserPassword
RESEND
```

Também não altera e-mail, `sub`, senha, MFA, USER, UNIQUE EMAIL, COGNITO
projection, marker singleton ou contador de Administradores. As únicas escritas
permitidas são `email_verified=true`, o registro técnico de idempotência e o
audit event imutável da própria operação.

## 23. Execução operacional e IAM

O repositório implementa o subcomando `verify-first-admin-email`, o workflow
manual `.github/workflows/verify-first-admin-email.yml` e o Terraform
declarativo da capacidade dedicada em `dev`. O workflow usa exclusivamente
`workflow_dispatch` e recebe um único input livre:

```text
operation_id = <UUIDv4 canônico>
```

O `actor_id` não é input e não admite override manual. Ele é derivado pelo
workflow da identidade autenticada no GitHub:

```text
github:<github.actor>@<github.actor_id>
```

O job usa credenciais temporárias OIDC, `aud=sts.amazonaws.com`, subject exato
do Environment `dev-verify-first-admin-email` e a role esperada
`student-manager-github-dev-verify-first-admin-email`. A managed policy esperada
é `student-manager-dev-verify-first-admin-email`.

As permissões declaradas são exatamente:

- Cognito User Pool: `cognito-idp:AdminGetUser` e
  `cognito-idp:AdminUpdateUserAttributes`;
- tabela `users`: `dynamodb:GetItem`;
- tabela `idempotency`: `dynamodb:GetItem`, `dynamodb:PutItem` e
  `dynamodb:UpdateItem`;
- tabela `audit-events`: `dynamodb:GetItem` e `dynamodb:PutItem`.

A role não concede wildcards nem `AdminCreateUser`, `AdminDeleteUser`,
`AdminDisableUser`, `AdminEnableUser`, `AdminSetUserPassword` ou
`AdminUserGlobalSignOut`. O IAM não consegue limitar
`AdminUpdateUserAttributes` ao atributo `email_verified`; os controles
compensatórios são role e Environment dedicados, workflow sem dados de
identidade livres, service restrito ao atributo permitido, reconciliação
obrigatória, read-back, idempotência e auditoria.

O workflow não recebe e-mail, `userId`, `cognitoSub`, nome, senha, token ou MFA.
Ele invoca a CLI uma única vez, sem retry automático, e interpreta:

```text
0       = COMPLETED; workflow bem-sucedido
2       = RECONCILIATION_REQUIRED; workflow em failure e investigação manual
demais  = erro operacional; workflow em failure
```

Um replay manual da mesma operação deve reutilizar o mesmo `operation_id`.

### Estado de disponibilização

A role, a policy e o workflow estão somente implementados declarativamente no
repositório. Eles ainda não estão provisionados ou configurados em `dev`; o
Environment e suas variables também ainda não existem. Nenhuma execução real da
operação foi autorizada.

Antes de qualquer execução real são obrigatórios:

1. merge da implementação;
2. provisionamento Terraform revisado;
3. criação e proteção do Environment;
4. configuração das Environment variables;
5. validações read-only da capacidade;
6. autorização explícita para corrigir a identidade histórica.

Este runbook não provisiona nem autoriza capacidade equivalente em `prod`.

## 24. Matriz mínima de testes do service

A implementação deverá cobrir, no mínimo:

1. UUID e contexto inválidos falhando antes de efeitos;
2. criação e reconciliação ambígua de `STARTED`;
3. preservação dos metadados determinísticos e ausência de PII;
4. replays terminais sem leituras de negócio ou mutação;
5. `ALREADY_VERIFIED` produzindo audit `SUCCESS` sem Cognito write;
6. `NEEDS_VERIFICATION` executando exatamente uma mutação autorizada;
7. read-back obrigatório depois de sucesso ou resultado ambíguo Cognito;
8. read-back verificado produzindo audit `SUCCESS` antes de `COMPLETED`;
9. read-back ainda não verificado preservando `STARTED` sem segunda mutação;
10. incompatibilidade produzindo audit `FAILURE` quando possível e
    `RECONCILIATION_REQUIRED`;
11. auditoria ausente ou indisponível não bloqueando o terminal excepcional;
12. audit incompatível nunca sobrescrito e conduzindo ao terminal excepcional;
13. write ambíguo de audit `SUCCESS` reconciliado por leitura consistente;
14. write ambíguo de audit `FAILURE` não bloqueando o terminal excepcional;
15. `COMPLETED` impossível antes da confirmação semântica do audit `SUCCESS`;
16. replay `STARTED` com audit terminal impedindo nova mutação Cognito;
17. transição terminal ambígua reconciliada por leitura consistente;
18. nenhuma operação Cognito ou escrita de domínio proibida;
19. diagnósticos e eventos sem PII;
20. retenção de 90 dias em `dev` e cinco anos em `prod`.

## Referências

- ADR-015 — Retenção da auditoria e proteção de dados;
- ADR-018 — Idempotência para operações não HTTP;
- ADR-021 — Modelagem física dos índices de auditoria;
- ADR-022 — Acesso operacional via GitHub Actions OIDC;
- ADR-024 — Protocolo do bootstrap do primeiro Administrador;
- ADR-025 — Verificação administrativa do e-mail do primeiro Administrador;
- [Idempotência não HTTP](non-http-idempotency.md).
