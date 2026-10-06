# Versão documental canônica

**Projeto:** Serverless Student Manager  
**Versão:** 3.1 — OpenAPI API Contract
**Data:** 2026-10-06
**Status:** Canônica — contrato público OpenAPI versionado; engenharia do projeto continua

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
- manifesto com SHA-256.
- contrato público real das 18 operações HTTP em OpenAPI 3.1;
- lint local e CI dedicado com Redocly, sem credenciais AWS ou deploy.

## Mudanças principais em relação à v3.0

1. `docs/api/openapi.yaml` passa a versionar as 18 operações públicas reais.
2. O contrato preserva `CanonicalError` e `LegacyError`, incluindo
   `EMAIL_ALREADY_EXISTS` no runtime de Users.
3. `redocly.yaml` aplica `recommended-strict` e o workflow dedicado executa lint
   sem AWS, OIDC, deploy ou mutações externas.
4. O marco funcional do frontend permanece encerrado e não foi reaberto.

## Estado de implementação desta baseline

O frontend funcional permanece 100% concluído e o contrato público da API está
versionado. Isso não declara o projeto inteiro como 100% concluído; a engenharia
do projeto e os itens adiados continuam.

## Regra de precedência

Esta versão substitui documentalmente a v3.0 como fonte de verdade para a engenharia.
