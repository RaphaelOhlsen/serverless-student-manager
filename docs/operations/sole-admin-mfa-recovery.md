# Runbook — Recuperação excepcional do único Administrador sem TOTP

**Status:** Approved  
**Data:** 2026-08-10

## Objetivo

Recuperar acesso administrativo quando um Administrador não possui mais o autenticador TOTP
e não existe um fluxo normal de recuperação utilizável.

## Pré-condições

- ADR-019 aprovada;
- usuário de negócio existe;
- usuário possui `role=ADMIN`;
- usuário está `ACTIVE`;
- usuário é o único Administrador ativo do sistema, condição validada pelo workflow antes de qualquer alteração destrutiva no Cognito;
- recuperação normal não é possível;
- solicitante possui autorização operacional;
- workflow foi aprovado manualmente;
- `operationId` definido;
- justificativa informada.

## Bloqueios

Abortar se:

- ambiente não estiver explicitamente informado;
- usuário não for `ADMIN`;
- usuário estiver inativo;
- existir mais de um Administrador ativo; nesse caso, utilizar o procedimento administrativo normal de recuperação/reset de MFA;
- o workflow não conseguir confirmar que o alvo é o único Administrador ativo antes de qualquer alteração destrutiva no Cognito;
- houver divergência entre `USER#userId` e `COGNITO#sub`;
- já existir outra recuperação em andamento;
- o `operationId` conflitar com outro payload;
- não for possível identificar inequivocamente a identidade Cognito atual.

## Passos

### 1. Inspeção

Ler:

```text
USER#<userId>
COGNITO#<oldSub>
```

Consultar a identidade correspondente no Cognito.

### 2. Invalidar sessões

Executar:

```text
AdminUserGlobalSignOut
```

### 3. Retirar identidade antiga

Executar:

```text
AdminDisableUser
AdminDeleteUser
```

Registrar o avanço do estado idempotente.

### 4. Criar identidade de substituição

Executar `AdminCreateUser` usando o mesmo vínculo de negócio e sem envio de mensagem:

```text
MessageAction = SUPPRESS
ForceAliasCreation = false
```

Capturar:

```text
newSub
```

### 5. Reassociar DynamoDB

Transação:

```text
Delete COGNITO#oldSub
Put    COGNITO#newSub
Update USER#userId
       cognitoSub = newSub
       authVersion = authVersion + 1
Put    audit event
```

Nenhuma alteração de `role`, `status` ou contador de Administradores ativos.

### 6. Enviar convite

Somente depois da confirmação da transação:

```text
AdminCreateUser
MessageAction = RESEND
```

### 7. Primeiro acesso

Usuário completa:

```text
senha temporária
  → NEW_PASSWORD_REQUIRED
  → senha definitiva
  → MFA_SETUP
  → AssociateSoftwareToken
  → VerifySoftwareToken
  → novo TOTP
```

## Resultado esperado

```text
USER#userId        = preservado
role               = ADMIN
status             = ACTIVE
cognitoSub          = newSub
COGNITO#oldSub      = removido
COGNITO#newSub      = ativo
authVersion         = incrementado
old Cognito user    = removido
new Cognito user    = ativo após onboarding
audit               = registrado
```

## Observabilidade

Métricas recomendadas:

```text
AdminMfaRecoveryStarted
AdminMfaRecoveryCompleted
AdminMfaRecoveryFailed
AdminMfaRecoveryReconciliationRequired
```

Logs devem conter apenas identificadores técnicos e nunca senha, TOTP ou token.

## Pós-condições

Depois da recuperação:

1. confirmar que a identidade antiga não autentica;
2. confirmar que a nova identidade resolve para o mesmo `userId`;
3. confirmar `role=ADMIN`;
4. confirmar `status=ACTIVE`;
5. confirmar novo TOTP;
6. confirmar evento de auditoria;
7. encerrar o `operationId` como `COMPLETED`.
