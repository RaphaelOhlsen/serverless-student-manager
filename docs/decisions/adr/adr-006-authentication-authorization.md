# ADR-006 — Autenticação e autorização

**Status:** Approved  
**Data:** 2026-07-30

## Decisão

- Amazon Cognito autentica usuários, gerencia senhas e emite tokens.
- O frontend envia o access token no cabeçalho `Authorization`.
- API Gateway HTTP API usa JWT Authorizer.
- As Lambdas verificam `token_use = access`.
- O `sub` identifica a identidade autenticada.
- A tabela `users` é a fonte de verdade para perfil e status.
- Cognito Groups não serão usados inicialmente.

## Projeção de autorização

```text
PK = COGNITO#<sub>
userId
role
status
authVersion
```

A Lambda autoriza com uma leitura fortemente consistente desse item.

## Respostas

- `401`: token ausente, inválido ou expirado.
- `403`: identidade válida, porém não provisionada, inativa ou sem permissão.

## Consequência principal

Mudanças de perfil e status passam a valer sem depender da expiração de claims antigas do Cognito.
