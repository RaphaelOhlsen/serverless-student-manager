# Procedimento operacional — Idempotência não HTTP

**Status:** Approved  
**Data:** 2026-08-10  
**ADR relacionada:** ADR-018

## Objetivo

Padronizar a idempotência de scripts, CLIs e workflows que produzem efeitos persistentes sem utilizar uma requisição HTTP.

## Convenção

Toda operação de escrita não HTTP recebe:

```text
operationId
```

O valor deve ser criado antes da primeira tentativa e preservado durante retries.

## Exemplos

### Bootstrap do primeiro Administrador

```text
environment = dev
operation   = bootstrap-admin
target      = first-admin
operationId = <uuid>
```

### Seed de desenvolvimento

```text
environment = dev
operation   = seed-dev-data
target      = dataset-v1
operationId = <uuid>
```

### Retomada do convite do primeiro Administrador

```text
environment = dev
operation   = resume-first-admin-invitation
target      = first-admin
operationId = <uuid-v4 próprio da retomada>
```

Essa operação reutiliza o mesmo `operationId` em todos os retries da mesma retomada.

Fluxo normal:

```text
STARTED → COMPLETED
```

Fluxo excepcional:

```text
STARTED → RECONCILIATION_REQUIRED
```

`COMPLETED` e `RECONCILIATION_REQUIRED` são terminais para essa operação.

As transições são validadas por `operation`. Isso não torna `STARTED → COMPLETED` uma transição global.

Ela se aplica somente ao primeiro Admin `INVITED` com marker, USER, projeção e identidade Cognito reconciliados. Não substitui a recuperação da ADR-019 para o único Admin `ACTIVE` sem TOTP.

### Reset administrativo de MFA

```text
environment = prod
operation   = reset-user-mfa
target      = USER#<userId>
operationId = <uuid>
```

## Regras para GitHub Actions

O workflow deve:

1. gerar ou receber o `operationId`;
2. expor o valor às etapas da mesma execução;
3. reutilizar o mesmo valor em retries controlados;
4. registrar apenas o identificador técnico e `correlationId`;
5. nunca colocar senha, token ou PII completa em logs.

## Regras para CLIs e scripts

A ferramenta deve aceitar `--operation-id` quando a repetição controlada for necessária.

Se o valor não for fornecido em uma nova operação, a ferramenta pode gerar um UUID.

O valor gerado deve ser exibido ao operador de forma segura para permitir retry da mesma operação.

## Conflito de payload

Se um `operationId` existente for reutilizado com payload incompatível:

```text
resultado = conflito de idempotência
efeito    = nenhum novo efeito persistente
```

A ferramenta deve terminar com erro explícito e seguro.

## Retenção

O estado técnico segue a retenção da ADR-012:

```text
TTL = 24 horas
```

Uma ferramenta que exija janela maior deve possuir decisão específica antes da implementação.

## Observabilidade

Eventos recomendados:

```text
operation.started
operation.replayed
operation.completed
operation.failed
operation.idempotency_conflict
```

Os eventos devem incluir:

- `environment`;
- `operation`;
- `operationId`;
- `correlationId`;
- identificador técnico do alvo quando permitido.

Não incluir PII completa.
