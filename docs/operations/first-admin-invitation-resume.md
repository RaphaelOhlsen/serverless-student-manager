# Runbook — Retomada do convite do primeiro Administrador

**Status:** Approved
**Data:** 2026-08-20
**ADRs relacionadas:** ADR-013, ADR-017, ADR-018, ADR-022 e ADR-024

## Objetivo

Definir o protocolo operacional de implementação de `resume-first-admin-invitation`, usado para retomar o convite do primeiro Administrador sem repetir o bootstrap inicial.

Este runbook detalha a ADR-024 sem alterar suas decisões arquiteturais. A operação não substitui a recuperação excepcional de MFA da ADR-019, aplicável ao único Administrador `ACTIVE` sem TOTP utilizável.

## Escopo

```text
operation = resume-first-admin-invitation
target    = first-admin
```

Identidade física do registro idempotente:

```text
NONHTTP#<environment>#resume-first-admin-invitation#first-admin#<operationId>
```

Retenção:

```text
TTL = 24 horas
```

Máquina de estados:

```text
STARTED → COMPLETED
STARTED → RECONCILIATION_REQUIRED
```

`COMPLETED` e `RECONCILIATION_REQUIRED` são terminais para essa operação.

## Schema do registro idempotente

O registro possui os seguintes atributos obrigatórios:

```text
id
environment
operation
target
operationId
payloadHash
state
correlationId
actorId
createdAt
updatedAt
expiration
```

Esta operação não persiste no registro idempotente:

```text
userId
eventId
occurredAt
auditExpiresAt
cognitoSub
originalBootstrapOperationId
fullName
email
```

O operador não fornece `userId`. Ele é descoberto autoritativamente a cada execução em `STARTED` a partir do singleton marker. Sua ausência no schema permite representar `marker` ausente ou malformado como `RECONCILIATION_REQUIRED` sem fabricar um identificador de usuário.

## Identificadores, autoria e tempo

O `operationId`:

- é um UUIDv4 textual canônico;
- pertence à operação de retomada;
- é gerado somente para uma execução nova;
- é reutilizado em retries e replays da mesma operação;
- deve ser diferente do `operationId` original registrado no singleton marker.

Se `resume.operationId == marker.operationId`, não executar `RESEND` nem transicionar para `RECONCILIATION_REQUIRED`. A igualdade viola o contrato da nova operação: propagar a falha de validação e manter o registro idempotente de resume em `STARTED`. Uma nova tentativa lógica deve usar um novo `operationId` UUIDv4.

`RECONCILIATION_REQUIRED` é reservado a inconsistências comprovadas no estado do primeiro Administrador, do Cognito ou do DynamoDB. A igualdade entre os dois `operationId` não é uma inconsistência de domínio.

O `correlationId` é um UUIDv4 gerado somente na criação do novo `STARTED`, persistido no registro e reutilizado em todos os replays. Nenhum UUID é gerado em replay.

O `actorId` é capturado no novo `STARTED` e preservado. Um executor posterior não substitui a autoria original.

`createdAt` é imutável. `updatedAt` muda somente em transições de estado. Ambos seguem a convenção UTC RFC3339 do protocolo, com precisão de milissegundos e sufixo `Z`.

## Payload lógico e hash

O payload lógico é exatamente:

```json
{"target":"first-admin"}
```

A serialização canônica usa JSON com chaves ordenadas, `separators=(",", ":")`, codificação UTF-8 e nenhum espaço adicional. `payloadHash` é o SHA-256 hexadecimal lowercase dessa representação.

Não entram no payload:

- `operationId`;
- `userId`;
- e-mail;
- nome completo;
- `cognitoSub`;
- `operationId` original do bootstrap.

Embora `operation` e `target` também componham a identidade física, `payloadHash` é mantido conforme o protocolo geral de idempotência não HTTP da ADR-018.

## Resultado

A implementação expõe semanticamente:

```text
ResumeInvitationResult
  operation_id
  state
  replayed
```

Os estados de resultado permitidos são:

```text
COMPLETED
RECONCILIATION_REQUIRED
```

O resultado não contém `user_id`: o marker pode estar ausente ou inválido, portanto não existe `userId` confiável em todos os terminais. Um replay terminal também não deve reler dados de negócio apenas para reconstruir o resultado.

## Descoberta autoritativa do primeiro Administrador

O operador não fornece `userId`, e-mail, nome completo ou `cognitoSub`.

A cadeia obrigatória de descoberta é:

```text
CONTROL#FIRST_ADMIN_BOOTSTRAP / CONTROL
  → userId
  → USER#<userId> / PROFILE
  → cognitoSub
  → COGNITO#<sub> / AUTHORIZATION
  → Cognito AdminGetUser
```

Antes de qualquer `RESEND`, confirmar:

1. singleton marker estruturalmente válido;
2. USER existente;
3. `USER.role == ADMIN`;
4. `USER.status == INVITED` ou `ACTIVE`;
5. `cognitoSub` válido;
6. projeção Cognito existente;
7. projeção apontando para o mesmo `userId`;
8. role e status compatíveis entre USER e projeção;
9. identidade Cognito existente;
10. `sub` retornado pelo Cognito igual ao persistido;
11. e-mail do Cognito compatível com o USER.

Esta operação não exige leitura de UNIQUE EMAIL.

## Administrador ACTIVE

Se todas as provas forem consistentes e `USER.status == ACTIVE`:

```text
STARTED → COMPLETED
RESEND = 0
```

O onboarding já foi concluído. Se o estado `ACTIVE` estiver acompanhado de qualquer incompatibilidade, executar:

```text
STARTED → RECONCILIATION_REQUIRED
```

## Administrador INVITED

Se todas as provas forem consistentes e `USER.status == INVITED`, executar no máximo uma vez por invocação:

```text
AdminCreateUser
MessageAction = RESEND
```

Quando o Cognito confirmar sucesso:

```text
STARTED → COMPLETED
```

## Falhas de RESEND

Se `RESEND` retornar `UserNotFoundException`, existe incompatibilidade comprovada entre os dados persistidos e o Cognito:

```text
STARTED → RECONCILIATION_REQUIRED
```

Para qualquer outra falha, incluindo:

- `CodeDeliveryFailureException`;
- `TooManyRequestsException`;
- `LimitExceededException`;
- `InternalErrorException`;
- timeout;
- erro de transporte;
- resultado potencialmente ambíguo;

não transicionar. Propagar a exceção e manter o registro em `STARTED`. Uma nova invocação com o mesmo `operationId` pode executar `RESEND` novamente.

A garantia é at-least-once, não exactly-once. Cada invocação executa no máximo um `RESEND`.

## Falhas e inconsistências de leitura

Uma inconsistência comprovada de domínio resulta em:

```text
STARTED → RECONCILIATION_REQUIRED
```

Uma falha técnica ou inconclusiva de leitura é propagada e mantém `STARTED`.

Exemplos:

- `AdminGetUser` com `UserNotFoundException`: inconsistência comprovada;
- timeout de `AdminGetUser`: falha técnica inconclusiva;
- `GetItem` com item ausente ou estruturalmente incompatível: inconsistência comprovada;
- timeout ou falha de transporte de `GetItem`: falha técnica inconclusiva.

## Transições CAS

As transições reutilizam o hardening de CAS do protocolo:

1. executar no máximo uma tentativa de `UpdateItem`;
2. após `ConditionalCheckFailedException` ou resultado potencialmente ambíguo, realizar uma leitura consistente;
3. considerar a intenção satisfeita somente quando `next_state` estiver confirmado;
4. propagar o erro se o estado não estiver confirmado;
5. nunca executar um segundo `UpdateItem` na mesma transição lógica.

As transições desta operação são:

```text
STARTED → COMPLETED
STARTED → RECONCILIATION_REQUIRED
```

## Replay

Para `COMPLETED`, retornar imediatamente o resultado terminal com `replayed=true`, sem RESEND, leituras de negócio ou geração de UUID.

Para `RECONCILIATION_REQUIRED`, retornar imediatamente o resultado terminal com `replayed=true`, sem RESEND, leituras de negócio ou geração de UUID.

Para `STARTED`, antes de qualquer leitura de negócio, validar estruturalmente o registro idempotente existente e confirmar que seu `payloadHash` é compatível com o payload canônico `{"target":"first-admin"}`. Payload incompatível deve falhar antes de ler marker, USER, projeção ou Cognito, sem `RESEND` e sem transição de negócio.

Depois dessas validações, revalidar integralmente marker, USER, projeção Cognito e identidade Cognito antes de qualquer novo `RESEND`. A autoria e o `correlationId` persistidos permanecem inalterados.

## Auditoria

A ADR-024 exige que a capacidade seja auditável, mas ainda não define um `eventType` de domínio para o reenvio.

Nesta implementação inicial:

- não criar novo item em `audit-events`;
- não inventar `eventType`;
- manter rastreabilidade pelo registro técnico de idempotência e pelo workflow operacional autenticado via GitHub OIDC.

Um evento de domínio poderá ser adicionado quando sua taxonomia estiver formalmente definida.

## Acesso operacional e escopo inicial

A role `dev-bootstrap-admin` não é a role final desta capacidade. Ela contém privilégios adicionais, incluindo exclusão e desabilitação no Cognito e `TransactWriteItems`.

Na etapa de operacionalização serão criados:

- uma role dedicada de menor privilégio para leitura dos itens necessários em users, `AdminGetUser`, `AdminCreateUser` usado para `RESEND` e operações necessárias na tabela de idempotência;
- um GitHub Environment dedicado.

Os nomes finais da role e do environment ainda não são definidos neste runbook. Nenhuma alteração Terraform faz parte desta etapa documental.

O escopo inicial é `dev`. `prod` permanece fora desta implementação enquanto não existir capacidade equivalente de bootstrap inicial nesse ambiente.

## Entrypoint futuro

A ferramenta deve expor comandos explícitos:

```text
bootstrap-first-admin
resume-first-admin-invitation
```

Não usar uma flag que altere silenciosamente a semântica do bootstrap inicial.

## Referências

- ADR-013 — Bootstrap seguro do primeiro Administrador;
- ADR-017 — Consistência Cognito ↔ DynamoDB no provisionamento;
- ADR-018 — Idempotência para operações não HTTP;
- ADR-022 — Acesso operacional via GitHub Actions OIDC;
- ADR-024 — Protocolo de execução do bootstrap do primeiro Administrador;
- ADR-019 — Recuperação excepcional do único Administrador sem TOTP, capacidade distinta desta retomada.
