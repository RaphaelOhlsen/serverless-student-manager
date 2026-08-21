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

## Escopos de provisionamento

### Provisionamento normal de usuário

O provisionamento normal segue as ADRs aplicáveis ao fluxo comum e preserva a transação de quatro itens descrita abaixo. Ele não cria nem utiliza `CONTROL#FIRST_ADMIN_BOOTSTRAP / CONTROL`.

### Bootstrap do primeiro Admin

O bootstrap inicial segue o protocolo especial da ADR-024. Sua transação contém cinco itens:

```text
Put USER#<userId> / PROFILE
Put UNIQUE#EMAIL#<normalizedEmail> / UNIQUE
Put COGNITO#<sub> / AUTHORIZATION
Put CONTROL#FIRST_ADMIN_BOOTSTRAP / CONTROL
Put AUDIT USER_CREATED
```

O marker singleton é permanente. Em concorrência, a operação que não obtiver o marker deverá reconciliar o estado e compensar somente a identidade Cognito que ela própria criou, quando essa propriedade puder ser comprovada com segurança.

## Sequência normal

### Etapa 1 — Contexto idempotente

- validar autorização do ator;
- validar payload;
- normalizar e-mail;
- iniciar ou reutilizar o contexto idempotente aplicável: fluxos HTTP seguem diretamente a ADR-012; operações não HTTP seguem a ADR-018; o bootstrap do primeiro Admin segue a ADR-018 especializada pela ADR-024;
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

### Etapa 3 — Persistir estado interno no provisionamento normal

Executar uma única `TransactWriteItems` para:

```text
Put USER#<userId>
Put UNIQUE#EMAIL#<normalizedEmail>
Put COGNITO#<sub>
Put AUDIT creation-success
```

Usar condições de não existência para os registros únicos.

Usar `ClientRequestToken` derivado do contexto técnico da operação. No bootstrap do primeiro Admin, a ADR-024 determina `ClientRequestToken = operationId` e inclui o marker como quinto item.

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

As regras de correção e reconstrução desta seção permanecem válidas para o provisionamento normal quando todos os vínculos puderem ser comprovados inequivocamente.

No bootstrap do primeiro Admin, qualquer combinação parcial ou incompatível dos cinco itens — USER, UNIQUE EMAIL, COGNITO projection, marker `CONTROL#FIRST_ADMIN_BOOTSTRAP / CONTROL` e audit event — não será corrigida silenciosamente pela criação isolada de um item. O fluxo interromperá novos efeitos, reconciliará conforme ADR-024 e usará `RECONCILIATION_REQUIRED` quando aplicável.

### Cognito existe e DynamoDB não existe

Se a identidade pertence comprovadamente à mesma operação:

- tentar concluir a transação DynamoDB;
- não enviar convite antes da conclusão.

No bootstrap do primeiro Admin, antes de repetir a transação quando Cognito existe e a persistência não foi confirmada:

- ler e reconciliar o marker singleton;
- se o marker estiver ausente, a mesma operação poderá seguir a política de retry seguro;
- se o marker for compatível com o mesmo `operationId` e `userId`, reconciliar os cinco itens;
- se o marker pertencer a outra operação, não tentar materializar o bootstrap e compensar somente a identidade Cognito própria quando isso for seguro.

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
- no provisionamento normal, reconstruir a projeção somente se `USER#<userId>` e Cognito puderem ser correlacionados inequivocamente;
- no bootstrap do primeiro Admin, não reconstruir automaticamente a projeção isolada; reconciliar os cinco itens e usar `RECONCILIATION_REQUIRED` quando aplicável;
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

Depois da expiração do registro idempotente original do bootstrap, `resume-first-admin-invitation` poderá reenviar o convite somente para o mesmo primeiro Admin com `role = ADMIN`, `status = INVITED` e identidade integralmente reconciliada. Essa retomada não cria nem modifica USER, UNIQUE EMAIL, COGNITO projection, marker ou identidade Cognito.

A operação é diferente da recuperação da ADR-019, exclusiva para um `ADMIN` `ACTIVE` que perdeu acesso ao TOTP.

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
