# ADR-029 — Resolução autenticada do próprio perfil

**Status:** Approved
**Data:** 2026-09-04

## Contexto

Após login concluído ou restauração de uma sessão Cognito, o frontend possui um
access token, mas não consegue determinar canonicamente se o usuário da
aplicação está `INVITED` ou `ACTIVE`. Inferir esse estado localmente ou a partir
de claims do Cognito violaria a ADR-006, pois a tabela `users` é a fonte de
verdade para role e status.

`POST /users/me/activation` permite a autoativação de `INVITED`, enquanto
operações de negócio como `GET /students` exigem `ACTIVE`. Falta uma leitura
self-service que permita ao frontend escolher o fluxo correto, inclusive após
restauração de sessão, sem ampliar o acesso operacional do usuário convidado.

## Decisão

Adicionar à `users-api` o endpoint autenticado e estritamente self-service:

```http
GET /users/me
Authorization: Bearer <access-token>
```

A rota usa o JWT Authorizer da HTTP API, aceita somente access token e extrai o
Cognito `sub` exclusivamente do contexto JWT validado. Não aceita body, query
parameters ou identificador de usuário e nunca permite consultar outro
`userId`.

## Autorização e exceção de onboarding

`GET /users/me` permite somente:

- `role = ADMIN | OPERATOR`;
- `status = INVITED | ACTIVE`.

A exceção funcional para `INVITED` fica limitada a:

```text
GET  /users/me
POST /users/me/activation
```

Todas as operações de negócio continuam exigindo `ACTIVE`, inclusive
`GET /students`. `INACTIVE` não pode acessar `GET /users/me` e recebe tratamento
fail-closed. A rota de self-profile não concede acesso a qualquer outro recurso
ou identidade.

## Fonte canônica e reconciliação

O backend executa leituras fortemente consistentes na tabela `users`:

1. lê `COGNITO#<sub> / AUTHORIZATION`;
2. obtém dessa projeção o `userId` autoritativo;
3. lê `USER#<userId> / PROFILE`;
4. exige que PROFILE e AUTHORIZATION concordem em `userId`, `role`, `status` e
   `authVersion`;
5. exige que `PROFILE.cognitoSub` seja igual ao `sub` autenticado.

AUTHORIZATION fornece `userId`, `role`, `status` e `authVersion`. PROFILE
fornece `fullName` e `email`, além dos valores usados na reconciliação. Todos os
campos públicos vêm do DynamoDB.

O endpoint não consulta Cognito. Não cria outra fonte de dados, sincronização ou
duplicação e não valida estado de senha ou MFA. A autenticação já concluída e o
JWT Authorizer formam a fronteira de identidade desta leitura.

## Contrato HTTP

Uma requisição válida e reconciliada retorna `200 OK`:

```json
{
  "userId": "identificador-interno",
  "fullName": "Nome do usuário",
  "email": "usuario@example.com",
  "role": "ADMIN",
  "status": "INVITED",
  "authVersion": 1
}
```

Regras do contrato:

- `role` é `ADMIN` ou `OPERATOR`;
- `status` é `INVITED` ou `ACTIVE`;
- `authVersion` é um JSON integer maior ou igual a `1`;
- a resposta contém somente os seis campos mostrados;
- informações de MFA, senha, tokens, `cognitoSub`, campos normalizados, chaves
  físicas e atributos internos não são expostos.

## Erros seguros

Erros utilizam o envelope canônico:

```json
{
  "error": "FORBIDDEN",
  "message": "Forbidden"
}
```

| Situação | Status | Código |
|---|---:|---|
| JWT ausente, inválido, expirado ou `token_use != access` | `401` | `UNAUTHORIZED` |
| Body ou query parameters presentes | `400` | `INVALID_REQUEST` |
| AUTHORIZATION ausente | `403` | `FORBIDDEN` |
| PROFILE ausente ou vínculo inconsistente | `403` | `FORBIDDEN` |
| Role diferente de `ADMIN`/`OPERATOR` | `403` | `FORBIDDEN` |
| Status diferente de `INVITED`/`ACTIVE`, inclusive `INACTIVE` | `403` | `FORBIDDEN` |
| Falha interna inesperada | `500` | `INTERNAL_ERROR` |

Ausência ou inconsistência de identidade não retorna `404`, para não revelar
estado de provisionamento. Respostas não expõem `sub`, dados internos, nomes de
recursos AWS, tokens, stack traces ou detalhes de infraestrutura.

## Dados, índices e IAM

A decisão reutiliza os dois itens e o access pattern já aprovados nas ADR-006 e
ADR-023. Não exige alteração do modelo DynamoDB, novo índice ou escrita.

A role da `users-api` já possui `dynamodb:GetItem` restrito à tabela `users`.
Não é necessária nova ação IAM nem acesso Cognito.

## Consequências para o frontend

Depois de login concluído ou sessão restaurada, o frontend consulta
`GET /users/me` antes de escolher a tela protegida:

```text
INVITED -> tela de ativação
ACTIVE  -> área operacional
```

Após ativação bem-sucedida, o frontend pode usar o resultado `ACTIVE` e resolver
novamente o perfil quando necessário. O frontend não infere role ou status a
partir de estado local ou claims Cognito. Router ou gerenciador global de estado
não são exigidos por esta decisão.

## Consequências positivas

- restauração de sessão resolve o estado atual de forma canônica;
- a exceção de onboarding permanece mínima e explícita;
- nenhuma operação de negócio é liberada para `INVITED`;
- projeções inconsistentes e usuários `INACTIVE` falham de forma fechada;
- não há nova dependência de Cognito, índice ou permissão IAM.

## Consequências negativas

- toda entrada autenticada exige duas leituras consistentes na tabela `users`;
- a `users-api` passa a manter um contrato público adicional;
- frontend e backend devem tratar falhas de resolução antes da área operacional.

## Relação com decisões anteriores

- **ADR-006 permanece válida:** Cognito autentica e o DynamoDB define role e
  status atuais. Esta ADR especifica a leitura self-service dessa fonte.
- **ADR-023 permanece válida:** são reutilizados os itens físicos PROFILE e
  AUTHORIZATION sem alteração de modelo ou índices.
- **ADR-027 é refinada:** sua afirmação de que a ativação era a única exceção
  para `INVITED` passa a ser lida com esta decisão. As únicas exceções são
  `GET /users/me` e `POST /users/me/activation`; a ativação continua sendo a
  única delas que altera estado.
- **ADR-026 permanece válida:** `GET /students` continua exigindo usuário
  `ACTIVE`.

## Impacto de implementação após aprovação

Uma implementação posterior deverá adicionar rota, serviço de reconciliação e
testes à `users-api`, registrar `GET /users/me` com JWT no API Gateway e
reutilizar as permissões DynamoDB existentes. Implementação, release e deploy
permanecem fora do escopo desta decisão documental.
