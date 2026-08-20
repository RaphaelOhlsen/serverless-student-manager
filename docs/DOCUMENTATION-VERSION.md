# Versão documental canônica

**Projeto:** Serverless Student Manager  
**Versão:** 2.7 — Engineering Ready
**Data:** 2026-08-20
**Status:** Canônica — engenharia em andamento

## Escopo desta versão

Esta versão consolida:

- SRS v1.2 com MFA e rastreabilidade atualizados;
- ADR-001 a ADR-024 aprovadas;
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

## Mudanças principais em relação à v2.6

1. ADR-024 aprovada — protocolo determinístico e trava singleton do bootstrap do primeiro Admin.
2. `operationId`, `userId`, `eventId` e `correlationId` do bootstrap definidos como UUIDv4 canônicos.
3. `ClientRequestToken = operationId`, sem transformação e sem persistência duplicada do token.
4. Marker permanente `CONTROL#FIRST_ADMIN_BOOTSTRAP / CONTROL` incorporado ao modelo físico de `users`.
5. Transação do bootstrap ampliada para cinco itens e reconciliação obrigatória dos cinco itens.
6. Registro idempotente do bootstrap ampliado com metadados determinísticos de evento, auditoria e ator.
7. `createdBy` e `updatedBy` alinhados ao `actorId` original.
8. Timestamps do bootstrap padronizados em UTC RFC3339 com precisão de milissegundos e sufixo `Z`.
9. Operação `resume-first-admin-invitation` definida para retomar o convite do primeiro Admin `INVITED` reconciliado.
10. Marker singleton mantém a proteção mesmo após o TTL de 24 horas do registro idempotente.

## Regra de precedência

Esta versão substitui documentalmente a v2.6 como fonte de verdade para a engenharia.
