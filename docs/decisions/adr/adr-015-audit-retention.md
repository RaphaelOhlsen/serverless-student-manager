# ADR-015 — Retenção da auditoria e proteção de dados

**Status:** Approved

## Decisão

Retenção de `audit-events`:

```text
dev  = 90 dias
prod = 5 anos
```

Cada evento terá `expiresAt` em Unix epoch seconds.

## Retenção excepcional

Um procedimento controlado poderá remover ou estender `expiresAt` para hold legal ou de segurança.

A operação deve registrar:

- motivo;
- responsável;
- data;
- liberação posterior.

As ações de hold também serão auditadas.

## Outras retenções

| Dado | `dev` | `prod` |
|---|---:|---:|
| CloudWatch Logs | 14 dias | 90 dias |
| Idempotência | 24 horas | 24 horas |
| Audit events | 90 dias | 5 anos |
| Seed | temporário | proibido |
| PITR DynamoDB | opcional inicialmente | 35 dias |

`students` e `users` não terão TTL automático.
