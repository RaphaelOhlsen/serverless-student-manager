# Serverless Student Manager

**Documento:** Visão geral do projeto  
**Versão:** 2.7
**Data:** 2026-08-20
**Status:** Aprovado

## 1. Visão geral

O **Serverless Student Manager** é uma aplicação web para gerenciamento de alunos de uma única instituição de ensino.

É um projeto de portfólio técnico destinado a demonstrar arquitetura serverless na AWS, engenharia de software, infraestrutura como código, segurança, testes automatizados, observabilidade e CI/CD.

O objetivo não é apenas implementar um CRUD, mas demonstrar o ciclo completo de concepção, arquitetura, desenvolvimento, implantação e operação.

## 2. Perfis do MVP

- `ADMIN`: alunos, usuários, desativação, reativação, gestão de perfis e auditoria.
- `OPERATOR`: cadastro, consulta, listagem, pesquisa e atualização de alunos.

O sistema deve manter pelo menos um Administrador ativo.

## 3. Escopo principal

- autenticação com Amazon Cognito;
- autorização por perfil no backend;
- MFA TOTP obrigatório;
- gerenciamento de alunos;
- gerenciamento de usuários administrativos;
- desativação lógica;
- auditoria imutável;
- idempotência nas operações de escrita;
- API documentada com OpenAPI;
- infraestrutura com Terraform;
- CI/CD com GitHub Actions e OIDC;
- acesso operacional controlado com roles IAM separadas por capacidade e ambiente;
- observabilidade com CloudWatch;
- testes em camadas;
- rollback em camadas;
- runbooks para compensação, idempotência operacional e recuperação de MFA.

## 4. Fora do MVP

- acesso do aluno;
- notas, frequência, turmas e disciplinas;
- gestão financeira;
- aplicativo móvel nativo;
- multi-tenancy;
- busca textual avançada;
- exclusão física pela interface;
- Grafana, Prometheus e OpenTelemetry como requisitos obrigatórios.

## 5. Stack aprovada

| Camada | Tecnologia |
|---|---|
| Frontend | React + TypeScript |
| Backend | Python + AWS Lambda |
| API | Amazon API Gateway HTTP API |
| Identidade | Amazon Cognito |
| Persistência | Amazon DynamoDB |
| Frontend hosting | S3 privado + CloudFront |
| Infraestrutura | Terraform |
| CI/CD | GitHub Actions + OIDC |
| Observabilidade | Amazon CloudWatch |
| E2E | Playwright |

## 6. Arquitetura resumida

```text
Usuário
  ↓
CloudFront
  ↓
S3 privado — React SPA
  ├── autenticação → Cognito
  └── access token → API Gateway HTTP API
                         ↓
                   JWT Authorizer
                         ↓
        ┌────────────────┼────────────────┐
        ↓                ↓                ↓
   students-api      users-api        audit-api
        ↓                ↓                ↓
    students           users         audit-events
        └──────────── idempotency ────────────┘

CloudWatch recebe logs, métricas, dashboards e alarmes.
GitHub Actions usa OIDC para deploy e operações manuais privilegiadas.
Roles operacionais são separadas das roles de deploy e usam GitHub Environments específicos.
Terraform gerencia a infraestrutura.
```

## 7. Princípios

- serverless first;
- security by design;
- least privilege;
- infraestrutura como código;
- documentação como fonte de verdade;
- observabilidade desde o início;
- automação;
- simplicidade;
- evolução incremental;
- revisão humana para decisões críticas.
