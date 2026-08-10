# ADR-011 — Estratégia de testes

**Status:** Approved

## Contexto

Testes locais não são suficientes para comprovar integrações reais entre Cognito, API Gateway, Lambda, IAM e DynamoDB.

## Decisão

Adotar estratégia de testes em camadas.

## Backend

- `pytest`;
- `pytest-cov`;
- Botocore `Stubber`;
- cobertura mínima de 80%.

## Frontend

- Vitest;
- React Testing Library;
- Mock Service Worker;
- cobertura mínima de 70%.

## API

- OpenAPI como contrato;
- lint/validação com Redocly CLI.

## Terraform

- `terraform fmt -check`;
- `terraform validate`;
- TFLint;
- `terraform test` com mocks quando aplicável.

## Integração e E2E

- integração real no ambiente `dev`;
- Playwright para E2E;
- smoke tests após deploy;
- fluxos críticos obrigatórios independentemente da cobertura.

## Pull requests

PRs executam validações sem alterar a AWS.

## Produção

Produção exige integração/E2E aprovados e aprovação manual.

## Refinamento posterior

A **ADR-020** usa smoke tests pós-deploy como gate operacional. Uma falha imediata no smoke de produção,
dentro de um workflow previamente aprovado, pode disparar rollback automático somente da release da
aplicação, seguido de novo smoke test.
