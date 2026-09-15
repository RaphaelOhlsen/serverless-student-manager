# ADR-035 — Gerenciamento administrativo de usuários

**Status:** Proposed
**Data:** 2026-09-12

## Contexto

RF-USR-001–008, RF-USR-011/012, RN-USR-001–005 e UC-007/008/010–012/015
exigem administração de usuários sem transformar o bloco em CRUD genérico. As
ADRs 006, 012, 017, 019, 021, 023, 025, 027 e 029 já definem a fronteira de
autorização, idempotência, provisionamento Cognito/DynamoDB, recuperação,
auditoria, modelo físico, verificação de e-mail, ativação e self-profile.

Esta decisão formaliza as operações administrativas restantes. Ela permanece
`Proposed` até implementação e validação dos fluxos; sua aprovação futura não
autoriza deploy, mutação cloud ou execução de recuperação operacional.

As decisões de contrato, consistência e falha de Create/Invite e Resend estão
fechadas nesta proposta. O status somente será promovido conforme a política do
projeto depois da implementação e validação do milestone completo.

## Escopo e superfície HTTP

Todas as rotas administrativas exigem JWT válido e ator `ADMIN` com status
aplicativo `ACTIVE`, resolvidos pela projeção DynamoDB conforme ADR-006.

```http
GET  /users
GET  /users/{userId}
POST /users
POST /users/{userId}/role-change
POST /users/{userId}/deactivation
POST /users/{userId}/reactivation
POST /users/{userId}/invitation/resend
```

Permanecem separados e com os contratos existentes:

```http
GET  /users/me
POST /users/me/activation
```

Não fazem parte da v1: `PATCH /users/{userId}`, alteração administrativa de
e-mail, edição genérica de perfil, `DELETE /users/{userId}` e API/UI de recovery
MFA. O recovery excepcional continua exclusivamente operacional conforme ADR-019.

## Representação pública administrativa

List, detail e respostas com User retornam somente:

```text
userId
fullName
email
role
status
version
createdAt
updatedAt
```

`cognitoSub`, `authVersion`, chaves físicas, campos normalizados, controles,
detalhes Cognito/MFA e metadados de idempotência não são públicos. Detail
inexistente retorna HTTP 404. A listagem retorna HTTP 200 com coleção paginada e
cursor opaco. Serialização de PROFILE histórico sem `version` expõe a versão
lógica `1`.

## Versionamento e autorização

O PROFILE passa a possuir dois contadores independentes:

- `version`: concorrência otimista do recurso administrativo, exposta pela API;
- `authVersion`: epoch interno de identidade/autorização, não exposto pela API
  administrativa.

Novos PROFILEs persistem `version = 1` e `authVersion = 1`. PROFILEs históricos
sem `version` têm versão lógica 1, sem backfill. A primeira mutação administrativa
com `expectedVersion = 1` deve condicionar atomicamente a escrita a:

```text
attribute_not_exists(version) OR version = 1
```

e materializar `version = 2`. Como a atualização também condiciona os demais
estados de origem aplicáveis, somente uma mutação concorrente pode vencer; a
segunda observa a versão materializada e falha.

Toda mutação funcional do PROFILE incrementa `version` exatamente uma vez.
Mudanças que afetam acesso — `INVITED -> ACTIVE`, troca de role, desativação e
reativação — também incrementam `authVersion`. Recovery incrementa somente nos
casos definidos por sua ADR. List, Get, resend e no-op não incrementam nenhum dos
dois valores. O SRS já exige ambos os incrementos na ativação efetiva, mas a
ADR-027 Approved e a capability live preservam `authVersion` e não materializam
`version` nessa transição. `ACTIVATION_CONTRACT_DRIFT=OPEN`: esta proposta não
altera a implementação de `/users/me/activation` nem considera o comportamento
live conforme ao SRS; a correção/reconciliação exige milestone separado.

Role, status e `authVersion` no PROFILE e em
`COGNITO#<sub> / AUTHORIZATION` devem permanecer iguais. A autorização funcional
consulta essa projeção; claims antigos não preservam privilégios removidos.

## Máquina de estados

```text
INVITED -> ACTIVE <-> INACTIVE
```

- somente `/users/me/activation` executa `INVITED -> ACTIVE`;
- deactivation administrativa executa `ACTIVE -> INACTIVE`;
- reactivation administrativa executa `INACTIVE -> ACTIVE`;
- `DISABLED` é estado técnico Cognito, não status de domínio;
- não existe status `DELETED`.

## Ordem comum, concorrência e no-op

Para writes HTTP:

1. autorizar o ator;
2. validar e claimar a idempotência;
3. retornar replay `COMPLETED` antes de nova leitura ou validação de versão;
4. carregar consistentemente o alvo, quando aplicável;
5. validar `expectedVersion`;
6. aplicar restrições de self-administration;
7. validar estado e políticas de domínio;
8. escolher no-op, reconciliação ou mutação efetiva;
9. executar efeitos externos conforme a saga da operação.

`expectedVersion` é JSON integer >= 1; boolean, null, float e string são
inválidos. Versão obsoleta retorna HTTP 409 `USER_VERSION_CONFLICT`. Restrições
de último Admin permanecem condições transacionais, nunca read-then-write.

Uma nova request que já encontra o valor desejado e versão atual pode concluir
como no-op 200, sem mudar versão, authVersion, timestamps ou auditoria de domínio,
somente quando o contrato da operação o permite. Deactivation não admite no-op
para nova chave contra `INACTIVE`: retorna `409 USER_STATE_CONFLICT`. Divergência
entre DynamoDB e Cognito segue caminho de reconciliação, não uma falsa mutação.

## Proteção do último Administrador

`CONTROL#ACTIVE_ADMIN_COUNT / CONTROL` permanece canônico. Uma única
`TransactWriteItems` condiciona `activeAdminCount > 1` e decrementa o contador em:

- role change de `ACTIVE ADMIN` para `OPERATOR`;
- deactivation de `ACTIVE ADMIN`.

O contador é incrementado em:

- role change de `ACTIVE OPERATOR` para `ADMIN`;
- reactivation de `ADMIN`;
- activation `INVITED -> ACTIVE` quando a role é `ADMIN`.

Role change de usuário `INVITED` ou `INACTIVE` não altera o contador. A condição
atômica impede que duas operações concorrentes removam o último Admin ativo.

## Create e convite

```http
POST /users
Idempotency-Key: <UUID>

{
  "fullName": "Nome do usuário",
  "email": "usuario@example.com",
  "role": "ADMIN"
}
```

Sucesso retorna HTTP 201 com o User público em `INVITED`, `version = 1` e
`authVersion = 1` interno. Esse sucesso somente é retornado quando a identidade
Cognito foi reconciliada, a transação DynamoDB foi confirmada, o `RESEND`
retornou sucesso conhecido e a saga chegou a `COMPLETED`. O fluxo segue ADR-017:

1. claim idempotente e `userId` estável;
2. `AdminCreateUser` com `Username=userId`, `SUPPRESS` e
   `ForceAliasCreation=false`;
3. reconciliação do `cognitoSub` por `AdminGetUser` quando necessário;
4. uma única transação com PROFILE, `UNIQUE#EMAIL`, AUTHORIZATION,
   `USER_INVITED` e avanço durável da saga para `DDB_COMMITTED`;
5. convite por `RESEND`;
6. conclusão idempotente somente quando o resultado permitido estiver definido.

O contrato de futuras criações da ADR-025 é preservado: `email` normalizado e
`email_verified=true` são enviados ao Cognito. Isso não confirma a conta nem
remove `NEW_PASSWORD_REQUIRED` ou MFA. A operação normal não usa a trava singleton
do primeiro Admin e não altera `ACTIVE_ADMIN_COUNT`.

O body é um objeto estrito: `fullName`, `email` e `role` são os três campos
obrigatórios; campos extras, chaves JSON duplicadas, null e tipos inválidos são
rejeitados. `role` aceita somente `ADMIN` ou `OPERATOR`.

`fullName` aceita Unicode e é normalizado por NFKC, trim e redução de whitespace
interno a um espaço. O valor após essa normalização deve conter de 2 a 150
caracteres, não pode ser vazio nem conter caracteres de controle. A representação
pública preserva a capitalização do valor normalizado; case folding é aplicado
somente ao campo técnico de busca `normalizedName`.

`email` é submetido ao validador sintático genérico da aplicação, sem tornar
regras específicas de Student autoridade para User. Depois de trim, sua forma
normalizada em lowercase deve ser válida, não vazia e possuir no máximo 254
caracteres. Nenhuma nova dependência é exigida por esta decisão. O hash idempotente
usa operação, `fullName` normalizado, e-mail normalizado e role, sem guardar PII
bruta no registro técnico.

Timeout de `AdminCreateUser` exige `AdminGetUser` antes de repetir. Não se cria
segunda identidade. Falha DynamoDB definitivamente conhecida após criação
Cognito usa apenas a compensação aprovada na ADR-017: não envia convite, tenta
`AdminDeleteUser` e, se necessário, `AdminDisableUser` com alerta/reconciliação.
`AdminDeleteUser` não é capacidade funcional do produto.

### Saga e atomicidade de Create/Invite

As fases semânticas mínimas são:

```text
CLAIMED
COGNITO_CREATED
DDB_COMMITTED
INVITATION_DISPATCHING
INVITATION_SENT
COMPLETED
RECONCILIATION_REQUIRED
```

Um estado interno retryable pode representar falha comprovadamente não aplicada,
sem ampliar a máquina pública. O claim preserva `userId`, `eventId` e
`correlationId` para todos os retries da mesma operação.

O avanço `COGNITO_CREATED -> DDB_COMMITTED` integra a mesma
`TransactWriteItems` que grava, com condições de ownership/não existência:

1. PROFILE;
2. `UNIQUE#EMAIL`;
3. `COGNITO#<sub> / AUTHORIZATION`;
4. auditoria `USER_INVITED`;
5. transição idempotente da saga para `DDB_COMMITTED`, protegida por CAS.

Não se usa CAS posterior como arquitetura principal, evitando que o domínio esteja
committed enquanto o estado durável ainda indique a fase anterior.
`CONTROL#ACTIVE_ADMIN_COUNT` não participa dessa transação.

Antes de chamar externamente o `RESEND`, a saga deve avançar por CAS para
`INVITATION_DISPATCHING`. Sucesso conhecido permite avançar para
`INVITATION_SENT` e então `COMPLETED`. Quando tecnicamente viável, auditoria do
sucesso de envio e conclusão idempotente são persistidas atomicamente depois de
`INVITATION_SENT`, sem repetir o side effect Cognito.

Falha determinística com evidência de que o `RESEND` não foi aplicado mantém o
User `INVITED`, registra estado retryable seguro e retorna HTTP 503
`INVITATION_DELIVERY_FAILED`. A mesma `Idempotency-Key` pode retomar apenas a etapa
de convite; não repete Cognito create nem a transação de domínio.

Timeout, conexão interrompida, resposta inconclusiva ou processo retomado em
`INVITATION_DISPATCHING` representam resultado potencialmente aplicado. A saga
vai para `RECONCILIATION_REQUIRED` e retorna HTTP 503
`INVITATION_DELIVERY_UNCERTAIN`. A mesma chave reproduz semanticamente esse estado
e nunca executa outro `RESEND`. O User permanece `INVITED` e a operação não promete
entrega exactly-once.

## Role change

```http
POST /users/{userId}/role-change
Idempotency-Key: <UUID>

{"expectedVersion": 1, "role": "OPERATOR"}
```

O alvo não pode ser o próprio ator, inclusive em no-op. Role deve ser `ADMIN` ou
`OPERATOR`. Mesma role com versão atual retorna HTTP 200 no-op.

Uma mudança efetiva usa uma transação com:

1. PROFILE: role, `version + 1`, `authVersion + 1`, updatedAt/updatedBy;
2. AUTHORIZATION: role e `authVersion + 1`;
3. alteração opcional de `ACTIVE_ADMIN_COUNT`;
4. `USER_ROLE_CHANGED / SUCCESS`;
5. conclusão idempotente com a resposta pública.

## Deactivation

```http
POST /users/{userId}/deactivation
Idempotency-Key: <UUID>

{"expectedVersion": 1}
```

O body é um objeto estrito contendo somente `expectedVersion`, JSON integer >= 1.
Para uma nova intenção, somente target `ACTIVE` é elegível: `INVITED` ou
`INACTIVE` retorna `409 USER_STATE_CONFLICT`, e target inexistente retorna 404.
Não existe lifecycle no-op de Deactivation para uma nova chave. A recuperação de
uma operação parcial pertence somente à sua `Idempotency-Key` original.

Antes de claim/replay, o backend autentica o ator, reconcilia sua autorização
funcional, exige `ACTIVE ADMIN`, valida a request e proíbe self-deactivation.
Uma self-deactivation não cria operação válida `COMPLETED`. Depois do claim,
replay exato `COMPLETED` retorna o resultado terminal antes de nova leitura do
target ou validação da versão. Nova operação lê consistentemente o target e
valida versão, estado e projeções antes de qualquer mutação.

A saga fail-closed possui as fases duráveis mínimas:

```text
CLAIMED -> DOMAIN_COMMITTED -> SIGNOUT_COMPLETED -> DISABLE_COMPLETED -> COMPLETED
```

1. A mesma `TransactWriteItems` que muda PROFILE e AUTHORIZATION de `ACTIVE`
   para `INACTIVE`, incrementa `version`/`authVersion`, decrementa opcionalmente
   `ACTIVE_ADMIN_COUNT` sob condição e insere `USER_DEACTIVATED / SUCCESS`
   exatamente uma vez também avança a operação para `DOMAIN_COMMITTED` por CAS.
2. Após `DOMAIN_COMMITTED`, chama `AdminUserGlobalSignOut` com `Username=userId`;
   sucesso conhecido é persistido como `SIGNOUT_COMPLETED`.
3. Após `SIGNOUT_COMPLETED`, chama `AdminDisableUser` com `Username=userId`;
   sucesso conhecido é persistido como `DISABLE_COMPLETED`.
4. Após `DISABLE_COMPLETED`, persiste `COMPLETED` e a resposta terminal necessária
   ao replay; somente então retorna HTTP 200 com o User público `INACTIVE` e a
   nova `version`, sem expor `authVersion`.

Depois de `DOMAIN_COMMITTED`, a autorização funcional já está bloqueada pelas
projeções DynamoDB. Retry da mesma chave nunca repete PROFILE, AUTHORIZATION,
contador ou auditoria de domínio, nem faz rollback ou reativação automática.
Timeout não é inferido pelo PROFILE: a fase durável governa a retomada.

Resultado ambíguo de transporte/timeout em `AdminUserGlobalSignOut` não prova
sucesso. A mesma chave pode chamar sign-out novamente com semântica at-least-once;
somente resposta bem-sucedida avança para `SIGNOUT_COMPLETED`. Resultado ambíguo
de `AdminDisableUser` exige `AdminGetUser` read-only para reconciliar a mesma
identidade (`Username=userId` e `sub` coerente com o domínio). `Enabled=false`
confirma disable e permite `DISABLE_COMPLETED`; `Enabled=true` permite repetir
disable pela mesma operação. User ausente, identidade incompatível ou leitura
inconclusiva não são sucesso e exigem reconciliação operacional. Não se recria
identidade nem se procura por e-mail.

Se Cognito não puder ser concluído/reconciliado na execução após
`DOMAIN_COMMITTED`, o User permanece funcionalmente `INACTIVE`, sem HTTP 200.
Retorna HTTP 503 `USER_DEACTIVATION_RECONCILIATION_REQUIRED`, sanitizado, e a
retomada usa a mesma chave. Uma nova chave que encontra target `INACTIVE`
retorna `409 USER_STATE_CONFLICT`; não adota, reclassifica nem completa uma saga
parcial anterior. O `COMPLETED` exato reproduz o resultado original sem novo
sign-out, disable, audit ou decremento de contador.

O PROFILE registra `deactivatedAt` e `deactivatedBy` conforme o SRS. A request não
possui motivo, portanto não cria `deactivationReason`. A reativação remove esses
metadados de estado corrente; o histórico permanece no evento imutável.

## Reactivation

```http
POST /users/{userId}/reactivation
Idempotency-Key: <UUID>

{"expectedVersion": 2}
```

A saga:

1. claima a idempotência;
2. reconcilia Cognito e exige identidade preservada e estado compatível;
3. executa `AdminEnableUser`;
4. transaciona PROFILE/AUTHORIZATION para `ACTIVE`, incrementa
   version/authVersion, incrementa opcionalmente o contador, insere
   `USER_REACTIVATED / SUCCESS` e persiste a fase/conclusão durável;
5. retorna HTTP 200 e User público.

Se Cognito estiver habilitado e a transação falhar, AUTHORIZATION permanece
`INACTIVE`, mantendo bloqueio funcional, e o retry retoma a saga. Reativação
preserva userId, cognitoSub, senha, email/email_verified e TOTP/MFA; não é novo
convite, activation ou reset. Para usuário anteriormente ativo, o estado Cognito
normal esperado é `CONFIRMED`; incompatibilidades exigem reconciliação técnica.

## Resend invitation

```http
POST /users/{userId}/invitation/resend
Idempotency-Key: <UUID>

{"expectedVersion": 1}
```

O alvo deve estar `INVITED` e na versão atual. Sucesso retorna HTTP 204 sem body.
Resend não muda PROFILE, role, status, version, authVersion ou contador. Replay
exato não envia outro e-mail; uma nova chave representa novo resend intencional.

Como Cognito não oferece confirmação observável de entrega exactly-once, resultado
ambíguo de `RESEND` não autoriza envio automático adicional. A operação persiste
estado de reconciliação/resultado incerto e registra auditoria honesta; não afirma
entrega que não possa provar.

O body é um objeto estrito contendo somente `expectedVersion`, que deve ser JSON
integer >= 1; boolean, null, float e string são inválidos. A saga possui as fases
semânticas mínimas:

```text
CLAIMED
DISPATCHING
SENT
COMPLETED
RECONCILIATION_REQUIRED
```

Um estado interno retryable é permitido para falha comprovadamente não aplicada.
Depois de autorizar o ator e resolver replay, a operação lê consistentemente o
target, valida versão e estado `INVITED` e reconcilia a identidade. Antes do side
effect, executa CAS para `DISPATCHING`; sucesso conhecido permite CAS para `SENT`
e depois auditoria/conclusão durável.

Falha determinística comprovadamente não aplicada retorna HTTP 503
`INVITATION_DELIVERY_FAILED`. A mesma chave pode retomar com segurança, mas deve
revalidar target, versão, estado e identidade antes da nova tentativa. Resultado
ambíguo ou retomada em `DISPATCHING` avança para `RECONCILIATION_REQUIRED`, retorna
HTTP 503 `INVITATION_DELIVERY_UNCERTAIN` e a mesma chave não dispara novo
`RESEND`.

Replay `COMPLETED` retorna HTTP 204 antes de nova leitura de target/version e não
repete o side effect. Uma chamada posterior a este endpoint com nova
`Idempotency-Key` é uma nova intenção administrativa e, se as precondições ainda
forem válidas, pode executar outro `RESEND`, mesmo após uma intenção anterior ter
terminado incerta. Mais de uma mensagem é aceitável apenas como consequência
dessa nova intenção explícita, nunca de retry automático.

## Idempotência e resultados incertos

Todas as writes usam `Idempotency-Key` UUID, TTL de 24 horas e namespaces:

- `create-user`;
- `change-user-role`;
- `deactivate-user`;
- `reactivate-user`;
- `resend-user-invitation`.

Para `create-user`, o hash inclui operação, `fullName` normalizado, e-mail
normalizado e role. Para `resend-user-invitation`, inclui operação, target userId e
expectedVersion. Mesma chave/request `COMPLETED` retorna status/body original; request
diferente usa `IDEMPOTENCY_KEY_REUSED`; execução em andamento usa
`OPERATION_IN_PROGRESS`. Cleanup ocorre apenas quando o efeito é definitivamente
não aplicado.

Sagas persistem fases suficientes para retomar side effects Cognito sem duplicar
identidade, convite ou auditoria. A idempotência durável é a fonte de verdade para
resultado incerto; leitura isolada de PROFILE não prova conclusão.

## Listagem, busca e paginação

`GET /users` usa `gsi-all-users-name`, ordenação por nome e cursor opaco:

| Parâmetro | Regra |
|---|---|
| `limit` | Inteiro decimal de 1 a 100; padrão 20. |
| `cursor` | Cursor opaco v1 emitido pela API. |
| `namePrefix` | Prefixo validado e normalizado como na ADR-023. |
| `email` | E-mail exato validado e normalizado como na ADR-023. |
| `role` | `ADMIN`, `OPERATOR` ou `ALL`; padrão `ALL`. |
| `status` | `INVITED`, `ACTIVE`, `INACTIVE` ou `ALL`; padrão `ALL`. |

`namePrefix` e `email` são mutuamente exclusivos. Parâmetros desconhecidos,
repetidos ou incompatíveis são inválidos. Busca por email usa `UNIQUE#EMAIL` e
depois PROFILE; prefixo usa `gsi-all-users-name`. A resposta contém exatamente
`items` e `nextCursor`, sendo `nextCursor` string opaca ou null.

Quando role/status forem filtros posteriores à Query, o serviço continua consumindo
páginas DynamoDB até preencher o limite solicitado ou esgotar a fonte. O cursor
representa a posição realmente consumida; uma página intermediária vazia após
filtro não significa fim. Limites devem seguir as convenções das APIs existentes.
Nenhum GSI novo é necessário para este contrato.

## Auditoria e privacidade

Eventos finais de sucesso:

- `USER_INVITED`;
- `USER_ROLE_CHANGED`;
- `USER_DEACTIVATED`;
- `USER_REACTIVATED`;
- `USER_INVITATION_RESENT`.

Seguem ADR-021, com target userId, ator, correlationId, timestamp, result e
transições de role/status/version quando aplicáveis. Não contêm senha temporária,
email completo desnecessário, token, segredo TOTP, código MFA ou hash de PII.
`USER_INVITED` integra a transação de criação do domínio e significa somente que
o User foi criado em `INVITED`; não afirma entrega do e-mail.
`USER_INVITATION_RESENT` é gravado somente após sucesso conhecido do `RESEND` e
inclui actorId, target userId, correlationId, timestamp/result e a versão observada
quando aplicável. Falhas, compensações e reconciliation devem manter semântica
observável honesta.
Tentativas administrativas negadas exigidas por RF-USR-011 são registradas pelo
mecanismo operacional sem revelar se um alvo inacessível existe.

Falhas técnicas e reconciliation não exigem novos eventos de auditoria de domínio.
A observabilidade existente deve emitir logs estruturados sem PII e métricas para,
no mínimo, Create/Invite em reconciliation, Resend em reconciliation e falha de
compensação de Create. Não se registram request body, e-mail completo, senha
temporária, resposta Cognito bruta, Authorization ou access/ID/refresh tokens.
Este milestone não cria SNS, e-mail ou novo canal de alerta; a ausência desse novo
transporte não bloqueia sua conclusão.

## Erros

O envelope existente é reutilizado. Códigos já aprovados permanecem:
`INVALID_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `IDEMPOTENCY_KEY_REUSED`,
`OPERATION_IN_PROGRESS` e `INTERNAL_ERROR`. O contrato administrativo acrescenta
nomes específicos somente onde a distinção é funcional:

| Situação | HTTP | Code |
|---|---:|---|
| User inexistente | 404 | `USER_NOT_FOUND` |
| Versão obsoleta | 409 | `USER_VERSION_CONFLICT` |
| E-mail reservado | 409 | `USER_EMAIL_CONFLICT` |
| Role change do próprio ator | 403 | `FORBIDDEN` |
| Self-deactivation | 403 | `FORBIDDEN` |
| Remoção do último Admin ativo | 409 | `LAST_ACTIVE_ADMIN_CONFLICT` |
| Estado alvo incompatível | 409 | `USER_STATE_CONFLICT` |
| Deactivation após commit de domínio com Cognito ainda não reconciliado | 503 | `USER_DEACTIVATION_RECONCILIATION_REQUIRED` |
| Entrega conclusivamente não realizada | 503 | `INVITATION_DELIVERY_FAILED` |
| Resultado de entrega potencialmente aplicado | 503 | `INVITATION_DELIVERY_UNCERTAIN` |
| Reconciliação necessária/falha técnica | 500 | `INTERNAL_ERROR` |

Nenhum erro expõe Cognito, chaves físicas, cancellation reasons ou PII.

## Infraestrutura e frontend

As rotas reutilizam Users Lambda, alias live, HTTP API e JWT Authorizer. Não são
esperadas tabelas ou GSIs novos. IAM deve crescer por capacidade e menor privilégio:
Query/transações DynamoDB e somente `AdminCreateUser`, `AdminGetUser`,
`AdminDisableUser`, `AdminEnableUser` e `AdminUserGlobalSignOut` onde necessários.
`AdminDeleteUser` fica restrito à compensação técnica aprovada.

A futura UI ADMIN oferece list, busca/filtros, detail, invite, role change,
deactivate/reactivate e resend. Writes carregam detail fresco, usam version e UUID
idempotente, impedem double-submit e tratam conflito. Restrições visuais de self e
último Admin complementam, sem substituir, a autoridade do backend.

## Consequências

- A v1 implementa apenas capacidades sustentadas pelo SRS.
- Concorrência de negócio e epoch de autorização deixam de compartilhar um campo.
- PROFILEs históricos evoluem sem backfill destrutivo.
- Sagas Cognito/DynamoDB exigem fases duráveis e reconciliação explícita.
- O número de ações de cada transação permanece muito abaixo do limite de 100 de
  `TransactWriteItems`.
- ADR-019 permanece o único break-glass do único Admin; nenhuma API de recovery é
  criada.

## Alternativas rejeitadas

- CRUD/PATCH genérico: introduz capacidades não aprovadas.
- Usar somente `authVersion`: mistura concorrência pública e epoch de segurança.
- Proteger último Admin por leitura prévia: falha sob concorrência.
- Concluir lifecycle antes dos efeitos Cognito: reporta sucesso incompleto.
- Inferir sucesso pela ausência/presença do PROFILE: ignora fases externas.
- Exactly-once de convite: Cognito não fornece prova observável dessa garantia.
