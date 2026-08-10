# ADR-012 — Idempotência

**Status:** Approved

## Contexto

Retries após timeout ou falha de rede não podem duplicar alunos, usuários, convites ou eventos.

## Decisão

Todas as operações de escrita exigirão:

```http
Idempotency-Key: <uuid>
```

O backend utilizará Powertools for AWS Lambda e uma tabela técnica DynamoDB compartilhada.

## Regras

- TTL: 24 horas.
- `GET` não exige chave.
- mesma chave + mesmo payload: retorna resultado anterior;
- mesma chave + payload diferente: `409 Conflict`;
- duplicata simultânea: bloqueada enquanto a primeira execução está em andamento;
- escopo interno inclui ambiente, usuário, operação e chave;
- payload validado por hash;
- nenhum dado pessoal completo será armazenado.

## DynamoDB

Transações de negócio também usarão `ClientRequestToken` quando aplicável.


## Refinamento posterior

A idempotência de operações não HTTP foi formalizada na **ADR-018**.

- API HTTP: `Idempotency-Key`;
- bootstrap, seed e utilitários operacionais: `operationId`.

Ambos seguem o mesmo modelo conceitual e reutilizam a infraestrutura técnica de idempotência.
