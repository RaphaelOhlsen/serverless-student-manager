# Serverless Student Manager — Documentação canônica

**Versão:** 3.2 — Frontend Hosting Infrastructure Declared
**Data:** 2026-10-06
**Status:** Hosting frontend declarado em Terraform — release ainda não implementada

## Objetivo

Este diretório é a fonte de verdade documental do **Serverless Student Manager**.

## Navegação

- [Mapa da documentação](serverless-student-manager-ordem-de-leitura.md)
- [Arquitetura](architecture/architecture-overview.md)
- [Requisitos](requirements/srs.md)
- [ADRs e registro de decisões](decisions/decision-register.md)
- [Contrato público OpenAPI 3.1](api/openapi.yaml)

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
`5f6794974ff7ce062cde8ee949f97862f50abc4b`. As evidências, o escopo concluído e
os itens de polish/DevOps explicitamente adiados estão no
[registro formal de fechamento](FRONTEND-MILESTONE-CLOSURE.md).

A engenharia do projeto continua além do marco funcional do frontend.

As 18 operações HTTP públicas atualmente implementadas estão versionadas em
[`api/openapi.yaml`](api/openapi.yaml). O contrato representa os envelopes de
erro legados e canônicos que coexistem no runtime, sem normalização retroativa.

A infraestrutura de hosting do frontend em `dev` está declarada em Terraform:
bucket S3 privado e versionado, CloudFront com OAC, HTTPS, security headers
gerenciados, cache separado para assets fingerprinted e fallback controlado de
SPA. A infraestrutura ainda não foi aplicada e o workflow de release ainda não
foi criado.

## Próximo marco

1. implementar o workflow de release e rollback do frontend em `dev`;
2. executar o primeiro deploy, smoke e validação de rollback;
3. adicionar CI do frontend e Playwright;
4. continuar os marcos operacionais sem reabrir o fechamento funcional.

## Estrutura documental

```text
docs/
├── README.md
├── api/
│   └── openapi.yaml
├── DOCUMENTATION-VERSION.md
├── FRONTEND-MILESTONE-CLOSURE.md
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
