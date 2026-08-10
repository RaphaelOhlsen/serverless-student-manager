# ADR-013 — Bootstrap do primeiro Administrador

**Status:** Approved

## Contexto

A administração de usuários exige um Administrador, mas o primeiro ambiente ainda não possui nenhum.

## Decisão

Criar o primeiro Administrador com utilitário Python controlado, acionado por workflow manual do GitHub Actions.

## Fluxo

```text
infraestrutura implantada
  → workflow manual
  → OIDC assume função IAM temporária
  → Cognito cria identidade
  → Cognito envia senha temporária
  → DynamoDB cria registros internos
  → auditoria registra o bootstrap
```

## Regras

- não existe endpoint público para bootstrap;
- nenhuma senha no Terraform, GitHub ou DynamoDB;
- operação idempotente;
- compensação se Cognito e DynamoDB ficarem inconsistentes;
- acesso excepcional limitado por ambiente;
- primeiro login usa `NEW_PASSWORD_REQUIRED`.

## Seed de desenvolvimento

Carga fictícia de usuários e alunos é separada, versionada, idempotente e permitida somente em `dev`.

## Refinamento posterior

A sequência de consistência entre Cognito e DynamoDB foi refinada pela **ADR-017 — Consistência de provisionamento entre Cognito e DynamoDB**.

O processo aprovado passa a criar a identidade no Cognito com envio de mensagem suprimido, persistir a projeção e os registros de negócio no DynamoDB e somente então enviar o convite ao usuário.
