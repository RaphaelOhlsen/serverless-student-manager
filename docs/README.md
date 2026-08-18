# Serverless Student Manager — Documentação canônica

**Versão:** 2.4 — Engineering Ready
**Data:** 2026-08-18
**Status:** Engenharia em andamento — ADR-001 a ADR-021 aprovadas

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
- ADR-001 a ADR-021.

A implementação está em andamento, com infraestrutura `dev`, autenticação Cognito, Students API inicial, HTTP API, idempotência e armazenamento de auditoria sendo materializados conforme as decisões arquiteturais aprovadas.

## Próximo marco

1. concluir os controles de acesso operacional via OIDC;
2. implementar o bootstrap seguro do primeiro Administrador;
3. evoluir o backend para os demais fluxos de alunos e usuários;
4. implementar o frontend React;
5. concluir observabilidade, testes end-to-end, hardening e preparação de `prod`.

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
│       └── adr-021-...
├── architecture/
├── operations/
├── references.md
├── serverless-student-manager-ordem-de-leitura.md
└── serverless-student-manager-ordem-de-leitura.png
```

## Regra

Não manter cópias antigas paralelas dentro do repositório.

A pasta `docs/` desta versão e o `AGENTS.md` da raiz formam a fonte de verdade para a engenharia.
