# Serverless Student Manager — Documentação canônica

**Versão:** 3.4 — Frontend First Release Completed
**Data:** 2026-10-07
**Status:** Frontend funcional, hosting e primeiro release dev concluídos

## Objetivo

Este diretório é a fonte de verdade documental do **Serverless Student Manager**.

## Navegação

- [Mapa da documentação](serverless-student-manager-ordem-de-leitura.md)
- [Arquitetura](architecture/architecture-overview.md)
- [Requisitos](requirements/srs.md)
- [ADRs e registro de decisões](decisions/decision-register.md)
- [Contrato público OpenAPI 3.1](api/openapi.yaml)
- [Fechamento funcional do frontend](FRONTEND-MILESTONE-CLOSURE.md)
- [Fechamento de hosting e release do frontend](FRONTEND-RELEASE-MILESTONE-CLOSURE.md)

O diretório `docs/` pode ser aberto como um Vault do Obsidian opcional; os
arquivos Markdown versionados continuam sendo a fonte canônica.

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
- resolução autenticada e self-service do próprio perfil;
- criação transacional e idempotente de aluno;
- ADR-001 a ADR-030.

O **Frontend Functional Milestone** está `COMPLETE` na baseline
`5f6794974ff7ce062cde8ee949f97862f50abc4b`. As evidências e o escopo funcional
estão no [registro formal de fechamento](FRONTEND-MILESTONE-CLOSURE.md).

O **Frontend Hosting and Release Milestone** também está `COMPLETE` em `dev`.
O hosting S3 privado + CloudFront está implantado e convergente, a automação de
release está operacional e o primeiro deploy real foi concluído com sucesso pelo
workflow oficial no run `37595125892`, release SHA
`93aa33817088a7a7475d9848669d7b24dcf1ab2d`. As evidências estão no
[registro de fechamento de hosting/release](FRONTEND-RELEASE-MILESTONE-CLOSURE.md).

A engenharia do projeto continua além desses marcos.

As 18 operações HTTP públicas atualmente implementadas estão versionadas em
[`api/openapi.yaml`](api/openapi.yaml). O contrato representa os envelopes de
erro legados e canônicos que coexistem no runtime, sem normalização retroativa.

## Próximo marco

1. selecionar o próximo bloco de engenharia sem reabrir os milestones fechados;
2. adicionar CI frontend dedicado e Playwright/E2E automatizado amplo quando
   priorizados;
3. continuar os marcos operacionais e de produção separadamente.

## Estrutura documental

```text
docs/
├── README.md
├── api/
│   └── openapi.yaml
├── DOCUMENTATION-VERSION.md
├── FRONTEND-MILESTONE-CLOSURE.md
├── FRONTEND-RELEASE-MILESTONE-CLOSURE.md
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
│       └── adr-030-...
├── architecture/
├── operations/
├── references.md
├── serverless-student-manager-ordem-de-leitura.md
└── serverless-student-manager-ordem-de-leitura.png
```

## Regra

Não manter cópias antigas paralelas dentro do repositório.

A pasta `docs/` desta versão e o `AGENTS.md` da raiz formam a fonte de verdade para a engenharia.
