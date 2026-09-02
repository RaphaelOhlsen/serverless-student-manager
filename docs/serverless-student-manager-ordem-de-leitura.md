# Serverless Student Manager — Ordem canônica de leitura

**Versão:** 2.8 — Engineering Ready

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
28. `decisions/adr/adr-021-audit-index-modeling.md`
29. `decisions/adr/adr-022-operational-access-oidc.md`
30. `decisions/adr/adr-023-users-physical-modeling.md`
31. `decisions/adr/adr-024-first-admin-bootstrap-execution-protocol.md` — Approved
32. `decisions/adr/adr-025-first-admin-email-verification.md` — Approved
33. `decisions/adr/adr-026-students-list-contract-and-physical-modeling.md` — Approved
34. `decisions/adr/adr-027-user-activation-after-first-sign-in.md` — Approved
35. `decisions/adr/adr-028-lambda-application-release-via-github-actions.md` — Approved

## 4. Arquitetura consolidada

36. `architecture/architecture-overview.md`
37. `architecture/data-model.md`
38. `architecture/security.md`
39. `architecture/deployment-and-cicd.md`
40. `architecture/observability.md`
41. `architecture/diagrams.md`

## 5. Operação

42. `operations/cognito-dynamodb-compensation.md`
43. `operations/non-http-idempotency.md`
44. `operations/first-admin-email-verification.md`
45. `operations/first-admin-invitation-resume.md`
46. `operations/sole-admin-mfa-recovery.md`
47. `operations/rollback-strategy.md`

## 6. Apoio e auditoria

48. `references.md`
49. `AUDIT-REPORT.md`
50. `MANIFEST.md`

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
