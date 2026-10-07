# Versão documental canônica

**Projeto:** Serverless Student Manager
**Versão:** 3.4 — Frontend First Release Completed
**Data:** 2026-10-07
**Status:** Canônica — frontend funcional, hosting e primeiro release dev concluídos

## Escopo desta versão

Esta versão consolida:

- SRS v1.2 com MFA e rastreabilidade atualizados;
- ADR-001 a ADR-030 aprovadas;
- modelos físicos de dados;
- autenticação, autorização e MFA;
- bootstrap do primeiro Administrador;
- consistência e compensação Cognito ↔ DynamoDB;
- idempotência HTTP e não HTTP;
- recuperação excepcional do único Administrador sem TOTP;
- retenção da auditoria;
- observabilidade;
- testes;
- CI/CD com OIDC;
- rollback em camadas;
- Terraform remote state;
- organização final dos módulos Terraform;
- estratégia de tags;
- runbooks operacionais;
- guia canônico de leitura;
- manifesto com SHA-256;
- contrato público real das 18 operações HTTP em OpenAPI 3.1;
- lint local e CI dedicado com Redocly, sem credenciais AWS ou deploy;
- hosting frontend de `dev` com S3 privado, CloudFront, OAC, security headers
  gerenciados, fallback controlado de SPA e cache por classe de objeto;
- IAM mínimo para publicação e rollback do frontend, sem permissão de exclusão
  de objetos;
- infraestrutura de hosting aplicada e convergente em `dev`;
- workflow e helper testável de release, smoke e rollback automático do frontend;
- primeiro release real do frontend em `dev` concluído com sucesso.

## Mudanças principais em relação à v3.3

1. A repository variable `TERRAFORM_STATE_BUCKET` foi configurada com o bucket
   real e validado do backend Terraform de `dev`.
2. O workflow `Frontend Release` foi executado por `workflow_dispatch` na
   `main`, run `37595125892`, para o commit
   `93aa33817088a7a7475d9848669d7b24dcf1ab2d`.
3. O primeiro release publicou assets fingerprinted antes de `index.html`,
   preservou cache imutável para assets e `no-cache` para o entry point e
   registrou `commit-sha` no objeto `index.html`.
4. A invalidação CloudFront `I2DBEP9CTXHE403LPZT90C2PUE` concluiu com apenas
   `/` e `/index.html`.
5. Frontend smoke, asset smoke, security headers e `GET /health` passaram; a
   API respondeu HTTP 200.
6. `PREVIOUS_INDEX_VERSION = NONE` foi o comportamento esperado para o primeiro
   release. Nenhum rollback foi necessário.
7. Nenhum upload S3 ou invalidação CloudFront manual foi executado; não houve
   `DeleteObject`, `sync --delete`, Terraform apply ou alteração em produção.
8. O marco funcional do frontend permanece encerrado e não foi reaberto. O item
   de pipeline de deploy que estava deferred naquele fechamento foi concluído
   posteriormente neste milestone operacional.

## Estado de implementação desta baseline

O frontend funcional permanece 100% concluído. O contrato público da API está
versionado, o hosting de `dev` está implantado e o primeiro release real do
frontend foi concluído com sucesso pela automação oficial.

O fechamento operacional do hosting/release está registrado em
`FRONTEND-RELEASE-MILESTONE-CLOSURE.md`.

CSP específica, domínio próprio, produção, Playwright/E2E automatizado amplo,
auditoria WCAG completa e refinamentos visuais permanecem fora desta baseline.
Isso não declara o projeto inteiro como 100% concluído.

## Regra de precedência

Esta versão substitui documentalmente a v3.3 como fonte de verdade para a engenharia.
