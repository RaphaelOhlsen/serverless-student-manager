# Serverless Student Manager — Ordem canônica de leitura

**Versão:** 2.3 — Engineering Ready

Antes de qualquer implementação, o Codex deve ler `../AGENTS.md`.

## 1. Contexto

1. `README.md`
2. `DOCUMENTATION-VERSION.md`
3. `ENGINEERING-READINESS.md`
4. `overview.md`

## 2. Requisitos e governança

5. `requirements/srs.md`
6. `decisions/decision-register.md`
7. `decisions/pending-decisions.md`

## 3. ADRs

8. `decisions/adr/adr-001-monorepo.md`
9. `decisions/adr/adr-002-frontend-hosting.md`
10. `decisions/adr/adr-003-api-gateway-http-api.md`
11. `decisions/adr/adr-004-lambda-organization.md`
12. `decisions/adr/adr-005-dynamodb-modeling.md`
13. `decisions/adr/adr-006-authentication-authorization.md`
14. `decisions/adr/adr-007-environments.md`
15. `decisions/adr/adr-008-terraform-remote-state.md`
16. `decisions/adr/adr-009-cicd-oidc.md`
17. `decisions/adr/adr-010-observability.md`
18. `decisions/adr/adr-011-testing-strategy.md`
19. `decisions/adr/adr-012-idempotency.md`
20. `decisions/adr/adr-013-first-admin-bootstrap.md`
21. `decisions/adr/adr-014-mfa-security.md`
22. `decisions/adr/adr-015-audit-retention.md`
23. `decisions/adr/adr-016-terraform-modules.md`
24. `decisions/adr/adr-017-cognito-dynamodb-provisioning-consistency.md`
25. `decisions/adr/adr-018-non-http-idempotency.md`
26. `decisions/adr/adr-019-sole-admin-mfa-recovery.md`
27. `decisions/adr/adr-020-rollback-strategy.md`

## 4. Arquitetura consolidada

28. `architecture/architecture-overview.md`
29. `architecture/data-model.md`
30. `architecture/security.md`
31. `architecture/deployment-and-cicd.md`
32. `architecture/observability.md`
33. `architecture/diagrams.md`

## 5. Operação

34. `operations/cognito-dynamodb-compensation.md`
35. `operations/non-http-idempotency.md`
36. `operations/sole-admin-mfa-recovery.md`
37. `operations/rollback-strategy.md`

## 6. Apoio e auditoria

38. `references.md`
39. `AUDIT-REPORT.md`
40. `MANIFEST.md`

## Leitura rápida para orientação

```text
AGENTS.md
  → docs/README.md
  → docs/overview.md
  → docs/requirements/srs.md
  → docs/decisions/decision-register.md
  → ADRs aplicáveis
  → docs/architecture/architecture-overview.md
```

A imagem `serverless-student-manager-ordem-de-leitura.png` é apoio visual.
