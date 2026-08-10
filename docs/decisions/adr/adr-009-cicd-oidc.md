# ADR-009 — CI/CD com GitHub Actions e OIDC

**Status:** Approved  
**Data:** 2026-07-30

## Alternativas

1. Access keys permanentes em GitHub Secrets.
2. Uma função IAM compartilhada.
3. Uma função IAM por ambiente usando OIDC.

## Decisão

Utilizar OIDC com duas funções IAM:

```text
student-manager-github-dev-deploy
student-manager-github-prod-deploy
```

## Fluxo

- Pull requests executam validações sem alterar a AWS.
- Merge na `main` implanta automaticamente em `dev`.
- Implantação em `prod` é manual e usa GitHub Environment.
- Produção promove um commit previamente validado.
- Não haverá access keys permanentes no GitHub.

## Segurança

- `contents: read` e `id-token: write` apenas quando necessários.
- Relações de confiança restritas ao repositório e ambiente corretos.
- Actions externas fixadas por SHA completo.
- Controle de concorrência por ambiente.
- Terraform usa `plan -out` e aplica o plano salvo.

## Refinamento posterior

A estratégia de rollback e recuperação de deploy foi formalizada na **ADR-020**.

Produção continua protegida por GitHub Environment e aprovação humana. Dentro de um deploy já aprovado,
uma falha imediata no smoke test pode restaurar automaticamente apenas a release da aplicação
(frontend e aliases Lambda) para o estado capturado antes do deploy. Infraestrutura e dados não são
revertidos automaticamente.
