# ADR-005 — Estratégia de modelagem do DynamoDB

**Status:** Approved  
**Data:** 2026-07-30

## Alternativas

1. Single-table design para todos os domínios.
2. Uma tabela por domínio.
3. Modelo híbrido.

## Decisão

Utilizar uma tabela por domínio:

```text
students
users
audit-events
```

A modelagem física será orientada pelos padrões de acesso.

## Regras aprovadas

- Nenhum fluxo normal dependerá de `Scan`.
- Matrícula e e-mail de aluno terão unicidade transacional.
- Listagens utilizarão paginação por cursor opaco.
- Auditoria ficará separada e append-only.
- IAM será limitado por função e tabela.

## Detalhes adicionais

Os modelos físicos das tabelas `students`, `users` e `audit-events` estão aprovados.
