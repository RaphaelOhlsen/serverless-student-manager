# ADR-022 — Acesso operacional controlado via GitHub Actions OIDC

**Status:** Approved
**Data:** 2026-08-18

## Contexto

O projeto possui operações administrativas que não devem ser expostas por endpoints públicos e que exigem acesso temporário à AWS por GitHub Actions OIDC.

Entre essas operações estão:

- bootstrap do primeiro Administrador, conforme ADR-013;
- compensação e reconciliação Cognito ↔ DynamoDB, conforme ADR-017;
- recuperação excepcional do único Administrador sem acesso ao TOTP, conforme ADR-019;
- futuras operações excepcionais de auditoria e retenção que exijam acesso operacional controlado.

A ADR-009 definiu roles de deploy por ambiente, mas essas roles não devem receber permissões operacionais privilegiadas apenas por conveniência.

A ADR-016 reservou o módulo Terraform `operational_access`, porém ainda não definiu sua topologia IAM concreta.

A ADR-019 também exige GitHub Environment específico para recuperação, aprovação humana, OIDC e IAM de menor privilégio.

Esta ADR define como as identidades operacionais serão separadas das identidades de deploy e como o provider OIDC existente será reutilizado.

## Alternativas consideradas

### Opção A — Reutilizar as roles de deploy

Adicionar às roles `student-manager-github-*-deploy` as permissões necessárias para bootstrap, reconciliação e recuperação.

Vantagens:

- menor quantidade de recursos IAM;
- nenhuma nova trust policy.

Desvantagens:

- mistura deploy e operações administrativas privilegiadas;
- amplia desnecessariamente o blast radius das roles de CI/CD;
- viola o objetivo de menor privilégio das ADR-013 e ADR-019.

### Opção B — Uma role operacional compartilhada por ambiente

Criar uma role operacional separada da role de deploy para cada ambiente, permitindo nela todos os procedimentos administrativos excepcionais.

Vantagens:

- separa deploy de operação;
- quantidade reduzida de roles;
- reutiliza o provider OIDC existente.

Desvantagens:

- bootstrap, recuperação break-glass e outras operações compartilham o mesmo conjunto de privilégios;
- uma operação menos sensível recebe permissões necessárias a operações mais destrutivas.

### Opção C — Roles operacionais separadas por capacidade e ambiente

Criar roles distintas para capacidades operacionais sensíveis, mantendo separação também por ambiente.

Exemplos conceituais:

```text
student-manager-github-dev-bootstrap-admin
student-manager-github-dev-admin-recovery
student-manager-github-prod-admin-recovery
```

Cada role terá trust policy e policy IAM próprias, limitadas à operação correspondente.

Vantagens:

- menor privilégio mais rigoroso;
- menor blast radius;
- permite GitHub Environments, aprovações e políticas diferentes por operação;
- facilita auditoria de quem assumiu qual capacidade operacional.

Desvantagens:

- maior número de roles e policies;
- mais configuração de GitHub Environments e workflows.

### Opção D — Uma role operacional genérica com autorização dinâmica

Criar uma única role e tentar restringir cada procedimento por session tags, condições IAM ou parâmetros fornecidos pelo workflow.

Vantagens:

- reduz quantidade de roles;
- pode permitir políticas dinâmicas no futuro.

Desvantagens:

- aumenta significativamente a complexidade de IAM;
- torna a revisão de segurança menos direta;
- adiciona mecanismos desnecessários para o tamanho atual do projeto.

## Decisão

Adotar a **Opção C — roles operacionais separadas por capacidade e ambiente**.

As roles operacionais serão independentes das roles de deploy definidas pela ADR-009.

Cada capacidade operacional sensível terá:

- trust policy própria;
- policy IAM própria;
- menor privilégio compatível com a operação;
- separação por ambiente;
- possibilidade de GitHub Environment e aprovação específicos.

O provider OIDC do GitHub Actions já criado no bootstrap será reutilizado; nenhum segundo provider OIDC será criado.

A implementação inicial deverá contemplar as capacidades necessárias para:

- bootstrap do primeiro Administrador;
- recuperação excepcional do único Administrador sem TOTP.

Novas capacidades operacionais somente deverão reutilizar uma role existente quando exigirem o mesmo conjunto de privilégios e a mesma fronteira de aprovação.

## GitHub Environments e subjects OIDC

Os GitHub Environments operacionais iniciais serão:

```text
dev-bootstrap-admin
dev-admin-recovery
prod-admin-recovery
```

O projeto continuará usando o subject imutável do GitHub OIDC baseado em `owner_id` e `repository_id`.

Formato base:

```text
repo:<owner>@<owner_id>/<repository>@<repository_id>
```

Para jobs associados a GitHub Environment, as trust policies usarão subjects exatos no formato:

```text
repo:<owner>@<owner_id>/<repository>@<repository_id>:environment:<environment>
```

Consequentemente, cada capacidade operacional somente poderá assumir sua própria role quando o workflow estiver associado ao GitHub Environment correspondente.

O bootstrap inicial será implementado em `dev` por meio de `dev-bootstrap-admin`.

A recuperação break-glass será isolada por ambiente por meio de:

```text
dev-admin-recovery
prod-admin-recovery
```

Não será permitido wildcard no valor de `sub`.


## Proteção atual dos GitHub Environments

Os GitHub Environments `dev-admin-recovery` e `prod-admin-recovery` exigem reviewer obrigatório e possuem `can_admins_bypass = false`.

Como o repositório possui atualmente um único colaborador com permissão administrativa, `RaphaelOhlsen` é o reviewer obrigatório e `prevent_self_review = false`.

Essa configuração mantém uma etapa explícita de aprovação manual, mas não fornece aprovação independente por segunda pessoa.

Como hardening futuro, quando houver um segundo colaborador confiável, os environments de recovery deverão migrar para `prevent_self_review = true` com reviewer independente.
