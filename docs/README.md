# Serverless Student Manager — Documentação canônica

**Versão:** 2.8 — Engineering Ready
**Data:** 2026-08-28
**Status:** Engenharia em andamento — ADR-001 a ADR-025 aprovadas

## Objetivo

Este diretório é a fonte de verdade documental do **Serverless Student Manager**.

O projeto demonstra a construção de uma aplicação serverless profissional na AWS utilizando:

- React e TypeScript;
- Python e AWS Lambda;
- Amazon API Gateway HTTP API;
- Amazon DynamoDB;
- Amazon Cognito;
- Terraform;
- GitHub Actions;
- Amazon CloudWatch.

## Situação atual

Estão concluídos e aprovados:

- definição do produto;
- SRS;
- perfis `ADMIN` e `OPERATOR`;
- requisitos de alunos e usuários;
- autenticação e autorização;
- MFA TOTP;
- modelos físicos DynamoDB;
- auditoria;
- idempotência HTTP;
- idempotência não HTTP com `operationId`;
- bootstrap do primeiro Administrador;
- consistência e compensação Cognito ↔ DynamoDB;
- recuperação excepcional do único Administrador;
- ambientes `dev` e `prod`;
- remote state Terraform;
- CI/CD com GitHub Actions e OIDC;
- observabilidade;
- testes;
- retenção;
- rollback em camadas;
- organização dos módulos Terraform;
- ADR-001 a ADR-025.

A implementação está em andamento, com infraestrutura `dev`, autenticação Cognito, Students API inicial, HTTP API, idempotência e armazenamento de auditoria sendo materializados conforme as decisões arquiteturais aprovadas.

## Próximo marco

1. implementar a ADR-025 para futuras criações do primeiro Administrador;
2. implementar a operação operacional `verify-first-admin-email` e sua capacidade OIDC dedicada em `dev`;
3. reconciliar o primeiro Administrador histórico e confirmar `email_verified=true`;
4. validar de forma read-only a prontidão do alias de e-mail para autenticação;
5. retomar a autenticação do frontend React e evoluir os demais fluxos da aplicação.

## Estrutura documental

```text
docs/
├── README.md
├── DOCUMENTATION-VERSION.md
├── ENGINEERING-READINESS.md
├── AUDIT-REPORT.md
├── MANIFEST.md
├── overview.md
├── requirements/
│   └── srs.md
├── decisions/
│   ├── decision-register.md
│   ├── pending-decisions.md
│   └── adr/
│       ├── adr-001-...
│       └── adr-024-...
├── architecture/
├── operations/
├── references.md
├── serverless-student-manager-ordem-de-leitura.md
└── serverless-student-manager-ordem-de-leitura.png
```

## Regra

Não manter cópias antigas paralelas dentro do repositório.

A pasta `docs/` desta versão e o `AGENTS.md` da raiz formam a fonte de verdade para a engenharia.
