# Versão documental canônica

**Projeto:** Serverless Student Manager  
**Versão:** 2.4 — Engineering Ready
**Data:** 2026-08-18
**Status:** Canônica — engenharia em andamento

## Escopo desta versão

Esta versão consolida:

- SRS v1.2 com MFA e rastreabilidade atualizados;
- ADR-001 a ADR-021 aprovadas;
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

## Mudanças principais em relação à v2.3

1. ADR-021 aprovada — modelagem física dos índices de auditoria.
2. `gsi-period-time` definido com bucket mensal `PERIOD#<YYYY-MM>`.
3. Chaves físicas de `gsi-actor-time`, `gsi-correlation-time` e `gsi-period-time` formalizadas.
4. Projeção `INCLUDE` adotada para os GSIs de auditoria.
5. Modelo de dados de `audit-events` atualizado.
6. Decision Register atualizado para ADR-001 a ADR-021.
7. Manifesto SHA-256 atualizado para a versão documental v2.4.

## Regra de precedência

Esta versão substitui documentalmente a v2.3 como fonte de verdade para a engenharia.
