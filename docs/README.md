# Serverless Student Manager — Documentação canônica

**Versão:** 2.3 — Engineering Ready  
**Data:** 2026-08-10  
**Status:** Arquitetura inicial concluída — ADR-001 a ADR-020 aprovadas

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
- ADR-001 a ADR-020.

A implementação do frontend, backend e infraestrutura da aplicação ainda não começou.

## Próximo marco

1. restaurar esta versão no repositório;
2. executar auditoria somente leitura com o Codex;
3. obter resultado `APROVADO PARA ENGENHARIA`;
4. criar o esqueleto do monorepo;
5. configurar ferramentas de qualidade;
6. iniciar `infra/bootstrap`.

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
│       └── adr-020-...
├── architecture/
├── operations/
├── references.md
├── serverless-student-manager-ordem-de-leitura.md
└── serverless-student-manager-ordem-de-leitura.png
```

## Regra

Não manter cópias antigas paralelas dentro do repositório.

A pasta `docs/` desta versão e o `AGENTS.md` da raiz formam a fonte de verdade para a engenharia.
