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

## Implementação operacional versionada

A CLI expõe comandos separados para o bootstrap inicial e para a retomada. A retomada é executada por:

```bash
python -m tools.bootstrap_admin resume-first-admin-invitation \
  --operation-id <UUIDv4> \
  --actor-id <actor>
```

O workflow versionado é `.github/workflows/resume-first-admin-invitation.yml` e possui somente o trigger `workflow_dispatch`. O operador fornece apenas `operation_id`; não fornece `userId`, e-mail, nome completo ou `cognitoSub`. No GitHub Actions, o ator é derivado automaticamente como:

```text
github:<github.actor>@<github.actor_id>
```

O job usa o GitHub Environment `dev-resume-first-admin-invitation`. A role e a policy dedicadas, definidas em Terraform, aplicadas e verificadas na AWS, são, respectivamente:

```text
student-manager-github-dev-resume-first-admin-invitation
student-manager-dev-resume-first-admin-invitation
```

Essa role de menor privilégio define:

- `cognito-idp:AdminGetUser` e `cognito-idp:AdminCreateUser` no User Pool; `AdminCreateUser` é necessário para `MessageAction=RESEND`;
- `dynamodb:GetItem` na tabela `users`;
- `dynamodb:GetItem`, `dynamodb:PutItem` e `dynamodb:UpdateItem` na tabela de idempotência.

Não são concedidos:

- `cognito-idp:AdminDeleteUser`;
- `cognito-idp:AdminDisableUser`;
- `cognito-idp:AdminUserGlobalSignOut`;
- `dynamodb:TransactWriteItems`;
- `dynamodb:DeleteItem`;
- `dynamodb:Query`;
- `dynamodb:Scan`;
- acesso à tabela `audit-events`;
- acesso à tabela `students`.

A trust policy efetiva da role foi verificada na AWS: permite somente `sts:AssumeRoleWithWebIdentity` pelo provider OIDC do GitHub, exige audience `sts.amazonaws.com` e restringe o `sub` ao Environment `dev-resume-first-admin-invitation` por correspondência exata, sem wildcard. A policy efetiva e seu attachment à role também foram verificados, sem `Action="*"` ou `Resource="*"`.

## Bootstrap inicial operacional

O workflow versionado `.github/workflows/bootstrap-first-admin.yml` usa `workflow_dispatch`, o Environment `dev-bootstrap-admin` e a role `student-manager-github-dev-bootstrap-admin`. Seus inputs são:

```text
operation_id
full_name
email
```

O ator não é um input e é derivado pelo workflow como `github:<github.actor>@<github.actor_id>`. A CLI executada é:

```bash
python -m tools.bootstrap_admin bootstrap-first-admin \
  --operation-id <UUIDv4> \
  --actor-id <actor> \
  --full-name <full-name> \
  --email <email>
```

`full_name` e `email` são inputs de `workflow_dispatch`; eles não são secrets. As proteções implementadas evitam logging e propagação desnecessária: os valores são enviados ao step por variáveis de ambiente, não são ecoados e não aparecem em summary, outputs, concurrency ou `role-session-name`.

## Segurança dos workflows

Os dois workflows declaram somente:

```yaml
permissions:
  contents: read
  id-token: write
```

As Actions externas são fixadas por SHA completo. A autenticação AWS usa OIDC, sem credenciais AWS estáticas, com `mask-aws-account-id=true`.

Os nomes das sessões são:

```text
bootstrap-first-admin-${{ github.run_id }}
resume-first-admin-invitation-${{ github.run_id }}
```

Eles não incluem PII nem `operationId`. As configurações de concorrência são `bootstrap-first-admin-dev` e `resume-first-admin-invitation-dev`, ambas com `cancel-in-progress=false` e `timeout-minutes=10`. Não há retry automático.

A CLI preserva os seguintes códigos de saída no job:

```text
0 = terminal bem-sucedido
1 = erro
2 = RECONCILIATION_REQUIRED
```

Os códigos `1` e `2` deixam o job não-verde.

## GitHub Environments e configuração operacional

Os Environments `dev-bootstrap-admin` e `dev-resume-first-admin-invitation` já foram criados e estão protegidos. O estado externo confirmado de ambos é:

```text
required reviewer                    = RaphaelOhlsen
prevent_self_review                  = false
can_admins_bypass                    = false
wait timer                           = none
custom deployment branch/tag policy = none
secrets                              = 0
```

As oito variables configuradas e verificadas em `dev-bootstrap-admin` são:

```text
AWS_ROLE_ARN
AWS_REGION
APP_ENVIRONMENT
COGNITO_USER_POOL_ID
USERS_TABLE_NAME
AUDIT_TABLE_NAME
IDEMPOTENCY_TABLE_NAME
AUDIT_RETENTION_DAYS
```

As seis variables configuradas e verificadas em `dev-resume-first-admin-invitation` são:

```text
AWS_ROLE_ARN
AWS_REGION
APP_ENVIRONMENT
COGNITO_USER_POOL_ID
USERS_TABLE_NAME
IDEMPOTENCY_TABLE_NAME
```

Não há variables extras nem Environment secrets nos dois Environments. Os nomes configurados correspondem exatamente aos contratos dos respectivos workflows.

## Estado de operacionalização

Implementado e versionado:

- CLI de bootstrap;
- CLI de retomada;
- workflows operacionais;
- definição Terraform da role e policy de retomada;
- GitHub Environments criados e protegidos.

Estado externo confirmado:

- `dev-bootstrap-admin` protegido;
- `dev-resume-first-admin-invitation` criado e protegido;
- apply Terraform da capacidade de retomada concluído com `3 added, 0 changed, 0 destroyed`;
- pós-apply convergente: `No changes. Your infrastructure matches the configuration.`;
- role, policy, trust OIDC e attachment da retomada verificados na AWS;
- variables completas e verificadas: `8/8` no bootstrap e `6/6` na retomada;
- ambos sem Environment secrets.

Ainda pendente:

1. executar operacionalmente os workflows quando houver necessidade autorizada;
2. validar o comportamento end-to-end dessas execuções.

Os dois workflows estão tecnicamente prontos para `workflow_dispatch`, mas nenhum deles foi executado nesta validação operacional. Isso não significa que o bootstrap tenha sido realizado, que a retomada tenha sido acionada, que um primeiro Administrador tenha sido criado ou que um convite tenha sido enviado. O escopo inicial permanece restrito a `dev`; `prod` continua fora desta implementação enquanto não existir capacidade equivalente de bootstrap inicial em `prod`.

## Referências

- ADR-013 — Bootstrap seguro do primeiro Administrador;
- ADR-017 — Consistência Cognito ↔ DynamoDB no provisionamento;
- ADR-018 — Idempotência para operações não HTTP;
- ADR-022 — Acesso operacional via GitHub Actions OIDC;
- ADR-024 — Protocolo de execução do bootstrap do primeiro Administrador;
- ADR-019 — Recuperação excepcional do único Administrador sem TOTP, capacidade distinta desta retomada.
