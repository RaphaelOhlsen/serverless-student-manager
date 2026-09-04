# Versão documental canônica

**Projeto:** Serverless Student Manager  
**Versão:** 2.9 — Engineering Ready
**Data:** 2026-09-04
**Status:** Canônica — engenharia em andamento

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

## Mudanças principais em relação à v2.8

1. ADR-030 aprovada — contrato canônico de `POST /students`.
2. Criação exige ADMIN/OPERATOR `ACTIVE`, JWT e `Idempotency-Key` UUID.
3. Request, resposta `201`, normalização, validação e conflitos foram definidos.
4. Perfil, reservas de matrícula/e-mail e `STUDENT_CREATED / SUCCESS` usam uma
   única `TransactWriteItems`.
5. As reservas usam `SK = UNIQUE`, garantem unicidade concorrente e referenciam
   o `studentId`.
6. O fluxo reutiliza ADR-012/Powertools, com replay exato e
   `ClientRequestToken` determinístico.
7. IAM mínimo da `students-api` deverá permitir somente a transação e o acesso
   técnico necessário à idempotência, sem Cognito ou novos índices/tabelas.

## Estado de implementação desta baseline

A ADR-030 consolida somente a decisão documental. Backend, rota, IAM,
infraestrutura, release, integração frontend e teste E2E de criação ainda não
foram implementados ou executados por esta baseline.

## Regra de precedência

Esta versão substitui documentalmente a v2.8 como fonte de verdade para a engenharia.
