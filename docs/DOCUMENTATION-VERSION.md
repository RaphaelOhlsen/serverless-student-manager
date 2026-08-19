# Versão documental canônica

**Projeto:** Serverless Student Manager  
**Versão:** 2.6 — Engineering Ready
**Data:** 2026-08-19
**Status:** Canônica — engenharia em andamento

## Escopo desta versão

Esta versão consolida:

- SRS v1.2 com MFA e rastreabilidade atualizados;
- ADR-001 a ADR-023 aprovadas;
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

## Mudanças principais em relação à v2.5

1. ADR-023 aprovada — modelagem física da tabela `users`.
2. Chave composta `PK + SK` formalizada para a tabela `users`.
3. Item principal definido como `USER#<userId> / PROFILE`.
4. Itens técnicos de unicidade de e-mail e projeção Cognito receberam chaves físicas completas.
5. `gsi-all-users-name` formalizado com `GSI1PK = USERS` e ordenação por nome normalizado.
6. Convenções de `normalizedName` e `normalizedEmail` formalizadas.
7. Modelo físico alinhado ao módulo Terraform, testes, state e tabela já implantada.
8. Decision Register atualizado para ADR-001 a ADR-023.
9. Manifesto SHA-256 atualizado para a versão documental v2.6.

## Regra de precedência

Esta versão substitui documentalmente a v2.5 como fonte de verdade para a engenharia.
