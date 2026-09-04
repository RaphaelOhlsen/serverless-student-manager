# Versão documental canônica

**Projeto:** Serverless Student Manager  
**Versão:** 2.8 — Engineering Ready
**Data:** 2026-09-04
**Status:** Canônica — engenharia em andamento

## Escopo desta versão

Esta versão consolida:

- SRS v1.2 com MFA e rastreabilidade atualizados;
- ADR-001 a ADR-029 aprovadas;
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

## Mudanças principais em relação à v2.7

1. ADR-025 aprovada — verificação administrativa do e-mail do primeiro Administrador.
2. Futuras criações do primeiro Admin passam a definir `email_verified=true`, preservando `MessageAction=SUPPRESS` e `ForceAliasCreation=false`.
3. A identidade histórica não verificada será reconciliada pela operação separada `verify-first-admin-email`, sem reutilizar o replay do bootstrap.
4. A operação preserva `userId`, `Username`, Cognito `sub`, e-mail, senha temporária e fluxo de MFA.
5. A única alteração Cognito permitida é definir `email_verified=true` na identidade existente após reconciliação completa.
6. `verify-first-admin-email` utiliza idempotência própria com `STARTED`, `COMPLETED` e `RECONCILIATION_REQUIRED`.
7. A capacidade OIDC dedicada em `dev` possui CLI, workflow e Terraform declarativo implementados no repositório; role/policy, GitHub Environment e variables ainda dependem de provisionamento e configuração.
8. O login exclusivo por e-mail no frontend permanece bloqueado até a reconciliação histórica e a validação read-only da prontidão do alias.
9. ADR-026 aprovada — contrato HTTP, autorização funcional, índices e cursor v1 para `GET /students`.
10. ADR-027 aprovada — ativação autenticada e idempotente após o primeiro login.
11. ADR-028 aprovada — releases de código Lambda pelo GitHub Actions e alias `live`.
12. ADR-029 aprovada — `GET /users/me` resolve canonicamente o próprio perfil e limita a exceção `INVITED` às rotas de self-profile e ativação.

## Estado de implementação desta baseline

Em 2026-08-31, a implementação no repositório inclui a role/policy declarativa,
o workflow manual e a cobertura de CI/testes de `verify-first-admin-email`.
Nenhum desses registros documenta provisionamento em AWS, criação do GitHub
Environment ou execução da correção histórica; essas etapas permanecem
separadas e sujeitas a revisão e autorização explícitas.

## Regra de precedência

Esta versão substitui documentalmente a v2.7 como fonte de verdade para a engenharia.
