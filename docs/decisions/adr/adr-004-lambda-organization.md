# ADR-004 — Organização das funções Lambda

**Status:** Approved  
**Data:** 2026-07-30

## Alternativas

1. Uma função por operação.
2. Uma função para toda a API.
3. Uma função por domínio.

## Decisão

Utilizar uma função Lambda por domínio:

```text
students-api
users-api
audit-api
```

Cada função atenderá múltiplas rotas do próprio domínio.

## Consequências positivas

- Separação de responsabilidades.
- IAM mais específico que em uma função única.
- Menos complexidade operacional que uma função por endpoint.
- Possibilidade de separar funções no futuro.

## Consequências negativas

- Uma alteração implanta a função inteira do domínio.
- Uma falha interna pode afetar várias rotas do domínio.
- Código compartilhado precisa ser bem organizado.

## Observação

Não serão usados Lambda Layers inicialmente. Dependências compartilhadas serão empacotadas com cada função.
