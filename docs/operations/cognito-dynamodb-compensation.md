# Procedimento operacional — Compensação Cognito ↔ DynamoDB

**Status:** Approved  
**Data:** 2026-08-10

## Objetivo

Definir como detectar, recuperar e compensar inconsistências durante o provisionamento de usuários administrativos.

## Estado desejado

Um usuário administrativo provisionado deve possuir, de forma coerente:

```text
Cognito user
  └── sub
       ↓
DynamoDB
  ├── USER#<userId>
  ├── UNIQUE#EMAIL#<normalizedEmail>
  └── COGNITO#<sub>
```

Enquanto aguarda primeiro acesso, o status de negócio é `INVITED`.

## Sequência normal

### Etapa 1 — Contexto idempotente

- validar autorização do ator;
- validar payload;
- normalizar e-mail;
- iniciar/reutilizar estado da ADR-012;
- gerar ou recuperar o mesmo `userId`.

### Etapa 2 — Criar identidade Cognito sem convite

Executar `AdminCreateUser` com:

```text
Username            = <userId>
MessageAction       = SUPPRESS
ForceAliasCreation  = false
email               = <email>
```

Capturar o atributo `sub`.

### Etapa 3 — Persistir estado interno

Executar uma única `TransactWriteItems` para:

```text
Put USER#<userId>
Put UNIQUE#EMAIL#<normalizedEmail>
Put COGNITO#<sub>
Put AUDIT creation-success
```

Usar condições de não existência para os registros únicos.

Usar `ClientRequestToken` derivado do contexto técnico da operação.

### Etapa 4 — Enviar convite

Somente após a confirmação da transação:

```text
AdminCreateUser
MessageAction = RESEND
```

Falha nessa etapa não invalida o provisionamento.

## Matriz de falhas

| Etapa | Situação | Ação |
|---|---|---|
| Cognito create | falha definitiva | encerrar; nenhum DynamoDB de negócio foi criado |
| Cognito create | timeout/resultado ambíguo | `AdminGetUser(userId)` e reconciliar |
| Cognito create | username já existe | consultar identidade; nunca adotar automaticamente usuário incompatível |
| DynamoDB | condição de e-mail único falha | excluir usuário Cognito recém-criado |
| DynamoDB | erro definitivo | excluir usuário Cognito |
| DynamoDB | resultado ambíguo | verificar estado; retry idempotente quando seguro |
| Cognito delete | falha | tentar disable e emitir alerta |
| Convite `RESEND` | falha | manter `INVITED`; auditar; permitir novo reenvio |

## Regras de reconciliação

### Cognito existe e DynamoDB não existe

Se a identidade pertence comprovadamente à mesma operação:

- tentar concluir a transação DynamoDB;
- não enviar convite antes da conclusão.

Se não for possível comprovar:

- desabilitar a identidade;
- gerar alerta;
- exigir análise operacional.

### DynamoDB existe e Cognito não existe

Esse estado não deve ocorrer no fluxo normal proposto.

Se detectado:

- não criar uma nova identidade automaticamente sem verificar o contexto idempotente;
- gerar alerta;
- reconciliar com base no `userId`, e-mail normalizado e evento de auditoria.

### Ambos existem, mas projeção `COGNITO#<sub>` falta

- bloquear autorização;
- reconstruir a projeção somente se `USER#<userId>` e Cognito puderem ser correlacionados inequivocamente;
- registrar a correção em auditoria operacional.

## Convite e status

A entrega de e-mail é separada da consistência da identidade.

Se `RESEND` falhar:

```text
Cognito       = existe
DynamoDB      = consistente
status        = INVITED
convite       = pendente de reenvio
```

RF-USR-008 é o mecanismo normal de recuperação.

## Observabilidade

Eventos recomendados:

```text
user.provisioning.started
user.cognito.created
user.persistence.completed
user.invitation.sent
user.invitation.failed
user.provisioning.compensation.started
user.provisioning.compensation.completed
user.provisioning.compensation.failed
user.provisioning.reconciliation.required
```

Métricas recomendadas:

```text
UserProvisioningSuccess
UserProvisioningFailure
UserProvisioningCompensationFailure
UserInvitationFailure
UserProvisioningReconciliationRequired
```

Nenhuma métrica ou log deve conter PII completa.

## Runbook para compensação incompleta

Quando `AdminDeleteUser` e `AdminDisableUser` não puderem concluir:

1. registrar correlation ID e `userId`;
2. emitir alarme operacional;
3. impedir qualquer tentativa de convite;
4. não criar outra identidade para o mesmo contexto;
5. operador autorizado verifica Cognito e DynamoDB;
6. após reconciliação, registrar resultado no audit trail.

## Testes de caos/falha

Simular em `dev`:

- timeout depois de `AdminCreateUser`;
- `TransactionCanceledException`;
- falha de condição de unicidade;
- erro 5xx no DynamoDB;
- falha em `AdminDeleteUser`;
- falha em `RESEND`;
- retry após resposta perdida.
