# ADR-019 — Recuperação excepcional do único Administrador sem acesso ao TOTP

**Status:** Approved  
**Data:** 2026-08-10

## Contexto

A ADR-014 tornou TOTP MFA obrigatório para `ADMIN` e `OPERATOR`.

Existe um cenário excepcional em que o único Administrador ativo perde acesso ao autenticador TOTP.
Nesse estado, o usuário conhece sua senha, mas não consegue concluir o desafio `SOFTWARE_TOKEN_MFA`
e portanto não consegue entrar na aplicação para realizar uma troca normal do autenticador.

A documentação do Amazon Cognito impõe duas limitações relevantes:

1. `AdminSetUserMFAPreference` não redefine um TOTP existente.
2. Quando MFA é obrigatório no user pool, não é possível simplesmente desativar TOTP para um usuário.

O Cognito também documenta que um novo TOTP substitui o anterior somente depois de
`AssociateSoftwareToken` + `VerifySoftwareToken`.

Portanto, o projeto precisa de um procedimento break-glass que não dependa da sessão da aplicação.

## Objetivos

- recuperar acesso administrativo;
- não reduzir silenciosamente a política global de MFA;
- não armazenar segredos de TOTP;
- preservar o `userId` interno e o histórico de auditoria;
- invalidar a identidade Cognito antiga;
- exigir novo primeiro acesso e novo TOTP;
- usar somente operações controladas e auditáveis;
- ser idempotente e recuperável após falhas parciais.

## Alternativas consideradas

### Opção A — Reduzir temporariamente o MFA do user pool

Fluxo conceitual:

1. mudar MFA de `REQUIRED` para `OPTIONAL`;
2. desativar o TOTP do usuário;
3. restaurar MFA para `REQUIRED`;
4. invalidar sessões;
5. forçar novo setup TOTP.

#### Vantagens

- preserva a identidade Cognito e o `sub`;
- menor quantidade de alterações no DynamoDB.

#### Desvantagens

- altera temporariamente uma política global de segurança;
- falha no meio do processo pode deixar o user pool com MFA menos restritivo;
- exige compensação da própria configuração global;
- cria uma janela operacional indesejável.

### Opção B — Substituir excepcionalmente a identidade Cognito

Fluxo conceitual:

1. validar que o alvo é o único Administrador ativo e que o procedimento foi aprovado;
2. iniciar uma operação idempotente com `operationId`;
3. invalidar sessões da identidade Cognito atual;
4. desabilitar e excluir a identidade Cognito inacessível;
5. criar uma nova identidade Cognito sem envio imediato de convite;
6. capturar o novo `sub`;
7. atualizar transacionalmente a projeção `COGNITO#<sub>` no DynamoDB;
8. preservar o mesmo `USER#<userId>`;
9. incrementar `authVersion`;
10. registrar auditoria de substituição de identidade;
11. enviar o novo convite;
12. exigir senha definitiva e novo setup TOTP.

#### Vantagens

- não reduz a política global de MFA;
- isola o procedimento ao usuário afetado;
- preserva a identidade de negócio `userId`;
- torna explícita a substituição da identidade de autenticação;
- permite auditoria completa.

#### Desvantagens

- o Cognito `sub` muda;
- a identidade Cognito anterior é destruída;
- exige cuidado com retries, alias de e-mail e transação de projeção;
- aumenta a complexidade operacional.

### Opção C — Manter um Administrador de emergência permanente

Um segundo Administrador, com TOTP independente, seria mantido exclusivamente para contingência.

#### Vantagens

- preserva continuidade administrativa;
- evita depender imediatamente de automação externa.

#### Desvantagens

- adiciona uma conta privilegiada permanente;
- exige manutenção, testes periódicos e custódia segura;
- não redefine diretamente o TOTP da conta bloqueada;
- a conta afetada ainda exigirá recuperação ou substituição posterior.

## Decisão proposta

Adotar a **Opção B — substituição excepcional da identidade Cognito**, executada por
workflow manual e protegido do GitHub Actions usando OIDC.

O procedimento será usado somente quando o usuário não conseguir recuperar o TOTP pelo fluxo normal.

## Identidade preservada

O identificador interno da aplicação permanece:

```text
USER#<userId>
```

A identidade Cognito é substituída:

```text
oldCognitoSub → newCognitoSub
```

A projeção de autorização muda de:

```text
COGNITO#<oldSub>
```

para:

```text
COGNITO#<newSub>
```

O histórico de auditoria existente não é reescrito.

## Controle do procedimento

O workflow deve exigir:

- execução manual;
- GitHub Environment específico para recuperação;
- aprovação humana antes da execução;
- OIDC;
- IAM de menor privilégio;
- `operationId` conforme ADR-018;
- justificativa obrigatória;
- `correlationId`;
- confirmação explícita do ambiente e do `userId`.

Nenhuma credencial AWS permanente é utilizada.

## Sequência proposta

```text
manual approval
  ↓
operationId
  ↓
validar USER#userId
  ↓
confirmar role=ADMIN + status=ACTIVE
  ↓
confirmar condição excepcional
  ↓
capturar oldSub
  ↓
AdminUserGlobalSignOut(old identity)
  ↓
AdminDisableUser(old identity)
  ↓
AdminDeleteUser(old identity)
  ↓
AdminCreateUser(new identity, SUPPRESS)
  ↓
capturar newSub
  ↓
TransactWriteItems
  ├── delete COGNITO#oldSub
  ├── put COGNITO#newSub
  ├── update USER#userId
  │     cognitoSub = newSub
  │     authVersion += 1
  └── append audit event
  ↓
RESEND invitation
  ↓
NEW_PASSWORD_REQUIRED
  ↓
MFA_SETUP
  ↓
novo TOTP
```

## Regras de segurança

- o fluxo não pode ser exposto como endpoint público;
- somente ferramenta operacional pode executar a substituição;
- o e-mail deve continuar pertencendo ao mesmo usuário de negócio;
- a operação não pode alterar `role`;
- a operação não pode alterar o contador de Administradores ativos;
- a nova identidade permanece associada ao mesmo `userId`;
- o antigo `sub` deve constar apenas na auditoria da substituição, nunca como identidade ativa;
- tokens da identidade antiga devem ser invalidados;
- nenhum segredo TOTP será armazenado;
- nenhum TOTP será gerado pelo operador;
- o usuário configurará o novo TOTP pessoalmente no primeiro acesso.

## Idempotência

A operação usa `operationId` conforme ADR-018.

Retries devem ser capazes de reconhecer os estados:

```text
OLD_IDENTITY_ACTIVE
OLD_IDENTITY_REMOVED
NEW_IDENTITY_CREATED
DYNAMODB_REBOUND
INVITATION_SENT
COMPLETED
```

Uma execução repetida não pode criar múltiplas identidades de recuperação.

## Falhas e reconciliação

### Falha antes da exclusão da identidade antiga

Nenhuma substituição ocorreu. Retry seguro.

### Falha após exclusão e antes da criação

O usuário já estava sem acesso.
Retry deve continuar da etapa de criação usando o mesmo `operationId`.

### Nova identidade criada, DynamoDB ainda aponta para `oldSub`

A nova identidade permanece sem autorização funcional.

O workflow deve concluir a transação DynamoDB antes de enviar o convite.

### DynamoDB atualizado, convite falha

Não fazer rollback da nova identidade.

O usuário permanece em estado de recuperação pendente e o convite pode ser reenviado.

### Estado ambíguo

Interromper automação destrutiva adicional, gerar alerta operacional e exigir reconciliação.

## Auditoria

Evento obrigatório:

```text
ADMIN_MFA_IDENTITY_RECOVERY
```

Campos técnicos mínimos:

```text
userId
oldCognitoSub
newCognitoSub
operationId
correlationId
actorType = OPERATIONAL_WORKFLOW
reason
occurredAt
result
```

E-mail, senha, TOTP e tokens não devem ser gravados no evento.

## Relação com ADRs anteriores

- ADR-006: mantém DynamoDB como fonte de verdade de `role` e `status`;
- ADR-013: reutiliza o padrão de criação Cognito sem convite imediato;
- ADR-014: mantém TOTP obrigatório;
- ADR-017: reutiliza o padrão Cognito → DynamoDB → convite;
- ADR-018: usa `operationId` para idempotência não HTTP.

Se aprovada, esta ADR formaliza a exceção em que o `sub` pode mudar sem alterar o `userId`.

## Consequências

### Positivas

- nenhum relaxamento global de MFA;
- recuperação independente da sessão da aplicação;
- identidade de negócio preservada;
- procedimento totalmente auditável;
- compatível com OIDC e menor privilégio.

### Negativas

- `sub` não é permanente ao longo de toda a vida do `userId` em cenário break-glass;
- requer lógica explícita de reconciliação;
- exige testes cuidadosos de falha por etapa;
- procedimento é destrutivo sobre a identidade Cognito anterior.

## Testes obrigatórios

1. recuperação completa;
2. retry antes da exclusão;
3. retry após exclusão;
4. falha na criação da nova identidade;
5. falha na transação DynamoDB;
6. falha no envio do convite;
7. tentativa de recuperação de `OPERATOR`;
8. tentativa contra Administrador inativo;
9. tentativa com `operationId` reutilizado com parâmetros diferentes;
10. validação de que tokens antigos não autorizam chamadas;
11. primeiro acesso da nova identidade;
12. novo `MFA_SETUP` e TOTP;
13. auditoria completa da substituição.

## Referências

- Amazon Cognito — TOTP software token MFA:
  https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-mfa-totp.html
- AdminSetUserMFAPreference:
  https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_AdminSetUserMFAPreference.html
- SoftwareTokenMfaSettingsType:
  https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_SoftwareTokenMfaSettingsType.html
- AssociateSoftwareToken:
  https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_AssociateSoftwareToken.html
- Token revocation / AdminUserGlobalSignOut:
  https://docs.aws.amazon.com/cognito/latest/developerguide/token-revocation.html
