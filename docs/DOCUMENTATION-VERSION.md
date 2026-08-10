# Versão documental canônica

**Projeto:** Serverless Student Manager  
**Versão:** 2.3 — Engineering Ready  
**Data:** 2026-08-10  
**Status:** Canônica — pronta para auditoria final do Codex e início da engenharia após aprovação humana

## Escopo desta versão

Esta versão consolida:

- SRS v1.2 com MFA e rastreabilidade atualizados;
- ADR-001 a ADR-020 aprovadas;
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

## Mudanças principais em relação à v2.2

1. SRS atualizado para MFA obrigatório e nova rastreabilidade.
2. ADR-017 aprovada — consistência Cognito ↔ DynamoDB.
3. ADR-018 aprovada — `operationId` para operações não HTTP.
4. ADR-019 aprovada — recuperação excepcional do único Administrador sem TOTP.
5. ADR-020 aprovada — rollback em camadas.
6. Inclusão e aprovação dos runbooks correspondentes.
7. Atualização de AGENTS.md, Decision Register, ordem de leitura e auditoria.

## Regra de precedência

Esta versão substitui documentalmente a v2.2 como fonte de verdade para a engenharia.
