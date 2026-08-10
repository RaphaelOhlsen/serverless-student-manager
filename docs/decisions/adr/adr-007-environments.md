# ADR-007 — Estratégia de ambientes

**Status:** Approved  
**Data:** 2026-07-30

## Alternativas

1. Um único ambiente.
2. `dev` e `prod` na mesma conta.
3. Uma conta por ambiente.

## Decisão

Manter `dev` e `prod` na mesma conta AWS, com recursos separados.

```text
AWS Account
├── student-manager-dev-*
└── student-manager-prod-*
```

## Regras

- Dados, Cognito, APIs, Lambdas, tabelas, logs e estados não serão compartilhados.
- O projeto pode iniciar somente com `dev`.
- `prod` será criado quando a aplicação estiver pronta para publicação.
- Dados de produção não serão copiados para desenvolvimento.
- Tags identificarão projeto, ambiente e gerenciamento por Terraform.

## Risco aceito

A conta continua sendo uma fronteira compartilhada. O isolamento por conta poderá ser adotado futuramente.
