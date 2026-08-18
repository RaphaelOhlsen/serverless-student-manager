# Versão documental canônica

**Projeto:** Serverless Student Manager  
**Versão:** 2.5 — Engineering Ready
**Data:** 2026-08-18
**Status:** Canônica — engenharia em andamento

## Escopo desta versão

Esta versão consolida:

- SRS v1.2 com MFA e rastreabilidade atualizados;
- ADR-001 a ADR-022 aprovadas;
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

## Mudanças principais em relação à v2.4

1. ADR-022 aprovada — acesso operacional controlado via GitHub Actions OIDC.
2. Roles operacionais separadas por capacidade e por ambiente.
3. Bootstrap do primeiro Administrador isolado da role de deploy.
4. Recuperação break-glass isolada por ambiente e por GitHub Environment.
5. Reutilização do provider OIDC existente, sem criação de um segundo provider.
6. Subjects OIDC exatos e imutáveis, sem wildcards.
7. Módulo Terraform `operational_access` incorporado à arquitetura.
8. Decision Register atualizado para ADR-001 a ADR-022.
9. Manifesto SHA-256 atualizado para a versão documental v2.5.

## Regra de precedência

Esta versão substitui documentalmente a v2.4 como fonte de verdade para a engenharia.
