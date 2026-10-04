# Versão documental canônica

**Projeto:** Serverless Student Manager  
**Versão:** 3.0 — Frontend Functional Complete
**Data:** 2026-10-04
**Status:** Canônica — frontend funcional completo; engenharia do projeto continua

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

## Mudanças principais em relação à v2.9

1. O marco funcional do frontend foi encerrado na baseline
   `5f6794974ff7ce062cde8ee949f97862f50abc4b`.
2. Auth, Students, Users Admin, Audit Viewer e a integração de navegação/sessão
   possuem evidências automatizadas e E2E integradas aprovadas.
3. O fechamento está registrado em `FRONTEND-MILESTONE-CLOSURE.md`.
4. Polish visual/acessibilidade avançada e automações de DevOps permanecem
   explicitamente adiados e não bloqueiam o marco funcional.

## Estado de implementação desta baseline

O frontend funcional está 100% concluído. Isso não declara o projeto inteiro
como 100% concluído; a engenharia do projeto e os itens adiados continuam.

## Regra de precedência

Esta versão substitui documentalmente a v2.9 como fonte de verdade para a engenharia.
