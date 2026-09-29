# ADR-037 — Contrato da Audit Query API

**Status:** Approved
**Data:** 2026-09-28

## Contexto

O SRS exige que somente Administradores consultem o histórico de auditoria e
permite filtrar eventos por intervalo de datas, recurso, tipo de evento, ator,
resultado e identificador de correlação. A ADR-004 atribui esse domínio à
`audit-api`; as ADR-005, ADR-015 e ADR-021 já definem a tabela append-only, sua
retenção, os índices físicos, os buckets mensais UTC e a proibição de `Scan` nos
fluxos normais.

Esta decisão define o contrato HTTP público sem alterar o modelo físico, a
retenção ou a taxonomia histórica de eventos.

## Decisão

### Rota e fronteira do domínio

A consulta pública de auditoria utilizará a Lambda dedicada `audit-api` e a rota:

```http
GET /audit-events
```

Não haverá endpoint separado de histórico de Student neste milestone. O
histórico de um aluno será consultado pela rota geral:

```http
GET /audit-events?resourceType=STUDENT&resourceId=<studentId>&from=<timestamp>&to=<timestamp>
```

Endpoints de conveniência poderão ser avaliados futuramente sob decisão própria.

### Autenticação e autorização

A rota terá JWT Authorizer no API Gateway e aceitará somente access token do
Cognito com `token_use=access`. A aplicação resolverá o `sub` na projeção de
autorização do DynamoDB e reconciliará essa projeção com o perfil do usuário.

Somente usuário com `status = ACTIVE` e `role = ADMIN` poderá consultar. O
comportamento público será:

- token ausente, inválido ou expirado: `401 UNAUTHORIZED`;
- `OPERATOR` autenticado: `403 FORBIDDEN`;
- usuário `INVITED` ou `INACTIVE`: `403 FORBIDDEN`;
- projeção ausente ou estado inconsistente: falha fechada com `403 FORBIDDEN`.

Esta decisão não altera a política de sessão ou a semântica de `authVersion`.

### Parâmetros de consulta

`from` e `to` são obrigatórios. Ambos devem ser timestamps RFC3339 canônicos em
UTC, por exemplo `2026-09-01T00:00:00Z` ou a forma fracionária canônica já usada
pelo projeto. Deve valer `from <= to`, e o intervalo solicitado não pode exceder
366 dias.

Parâmetros opcionais:

```text
resourceType
resourceId
eventType
actorId
result
correlationId
limit
cursor
```

Regras:

- `resourceType` aceita somente `STUDENT` ou `USER`;
- `result` aceita somente `SUCCESS` ou `FAILURE`;
- `resourceId` exige `resourceType`;
- `resourceType` sem `resourceId` é permitido como filtro posterior sobre o
  access pattern temporal;
- `eventType`, `actorId` e `correlationId` usam correspondência exata;
- `eventType` preserva o valor armazenado, sem normalização;
- parâmetros desconhecidos, repetidos, malformados ou não suportados retornam
  `400 INVALID_REQUEST`.

### Limite e paginação

`limit` representa o número máximo de eventos públicos retornados:

```text
default = 50
minimum = 1
maximum = 100
```

Valor inválido retorna `400 INVALID_REQUEST`. Quando filtros posteriores à
`Query` eliminarem itens, a implementação poderá consumir páginas adicionais do
DynamoDB até preencher a página pública ou atingir o fim da consulta. Deve
existir um limite interno defensivo contra amplificação ilimitada de leitura; a
constante exata é detalhe de implementação e não pode violar o contrato público.

O cursor será opaco, URL-safe, versionado, validado estruturalmente e vinculado
à consulta original. Não exige persistência no servidor, não é artefato de
autorização e não contém credenciais. Clientes não podem depender de sua
representação interna.

O cursor deverá carregar informação suficiente para retomada determinística,
conceitualmente incluindo versão, fingerprint da consulta, access pattern
selecionado, bucket corrente quando aplicável, posição de continuação no
DynamoDB e estado de ordenação necessário. Os nomes dos campos serializados são
detalhes de implementação.

O vínculo inclui, no mínimo:

```text
from
to
resourceType
resourceId
eventType
actorId
result
correlationId
limit
selected access path
```

Cursor usado com filtros ou `limit` diferentes, malformado, incompatível,
estruturalmente inválido ou de versão não suportada retorna
`400 INVALID_CURSOR`. O cursor não torna a representação física do DynamoDB um
contrato público.

### Ordenação

A ordem pública é determinística e decrescente:

1. `occurredAt DESC`;
2. `eventId DESC` como desempate.

A sort key existente contém timestamp e `eventId`. Consultas temporais com mais
de um mês processam buckets do mês UTC mais novo para o mais antigo e apresentam
uma única linha do tempo global decrescente.

### Seleção do access pattern

Cada request selecionará exatamente um access pattern primário, nesta prioridade:

1. `correlationId` → `gsi-correlation-time`;
2. `resourceType + resourceId` → tabela base `audit-events`;
3. `actorId` → `gsi-actor-time`;
4. caso contrário → `gsi-period-time`.

O intervalo obrigatório `[from, to]` limita a sort key em todos os access
patterns. Outros filtros fornecidos são aplicados depois da `Query`. Índices não
serão intersectados. Não haverá `Scan`, novo GSI ou nova tabela.

Exemplos:

- `correlationId + actorId`: Query pelo índice de correlação e filtro posterior
  por `actorId`;
- recurso + `eventType`: Query pela partição do recurso e filtro posterior por
  `eventType`;
- `actorId + result`: Query pelo índice de ator e filtro posterior por `result`;
- datas + `resourceType`: Query pelos buckets mensais e filtro posterior por
  `resourceType`.

### Intervalos com múltiplos meses

O access pattern temporal derivará todos e somente os buckets UTC `YYYY-MM` que
intersectem `[from, to]`. A consulta começa pelo bucket mais novo. Os buckets de
borda recebem limites temporais precisos; buckets intermediários podem usar o
mês completo. Nenhum bucket fora do intervalo será consultado.

### Resposta pública

Uma consulta válida retorna `200`:

```json
{
  "items": [
    {
      "eventId": "...",
      "eventType": "STUDENT_UPDATED",
      "resourceType": "STUDENT",
      "resourceId": "...",
      "actorId": "...",
      "occurredAt": "2026-09-28T14:30:00.000Z",
      "result": "SUCCESS",
      "correlationId": "..."
    }
  ],
  "nextCursor": null
}
```

Cada item expõe exatamente:

```text
eventId
eventType
resourceType
resourceId
actorId
occurredAt
result
correlationId
```

Não serão expostos neste milestone `changes`, `reason`, `actorType`,
`operationId`, `observedVersion` ou `expiresAt`. Também não serão expostos `PK`,
`SK`, chaves `GSIxPK/GSIxSK`, nomes de infraestrutura AWS ou detalhes internos do
DynamoDB.

Consulta válida sem eventos retorna:

```json
{
  "items": [],
  "nextCursor": null
}
```

Esse caso usa `200`, nunca `404`.

### Sem hidratação

A API retorna somente o resumo estável já projetado pelos GSIs. Não haverá
hidratação de eventos neste milestone e o fluxo normal não requer `GetItem` na
tabela de auditoria. Uma futura capacidade de detalhe poderá decidir hidratação
separadamente.

Essa fronteira evita expor campos opcionais específicos de produtores e o motivo
em texto livre.

### Erros

Os erros desta rota seguem o envelope de RF-ERR-001 e definem, no mínimo:

- `400 INVALID_REQUEST` para parâmetros inválidos;
- `400 INVALID_CURSOR` para cursor inválido ou incompatível;
- `401 UNAUTHORIZED` para ausência ou invalidade de autenticação;
- `403 FORBIDDEN` para identidade autenticada sem autorização;
- `500 INTERNAL_ERROR` para falha inesperada.

Respostas não expõem tabelas, índices, ARNs, stack traces, erros brutos do
DynamoDB ou detalhes internos do cursor. Esta decisão não cria uma nova
arquitetura global de erros nem normaliza retroativamente endpoints existentes;
a normalização global do envelope permanece uma lacuna separada do projeto.

### Leituras, idempotência e taxonomia

Consultas bem-sucedidas em `GET /audit-events` não geram eventos de auditoria
neste milestone porque:

- a Lambda permanece estritamente read-only sobre `audit-events`;
- evita-se crescimento recursivo causado pela leitura da própria auditoria;
- nenhum requisito canônico atual exige auditar leituras bem-sucedidas.

A taxonomia de tentativas negadas permanece fora do escopo e segue como decisão
transversal pendente.

Idempotência não se aplica ao `GET`, que não possui efeitos colaterais e não usa
`Idempotency-Key`.

Os valores históricos de `eventType` não serão renomeados ou normalizados. A API
poderá retornar exatamente os valores armazenados, incluindo:

```text
STUDENT_CREATED
STUDENT_UPDATED
STUDENT_DEACTIVATED
STUDENT_REACTIVATED
USER_CREATED
USER_INVITED
USER_ACTIVATED
USER_ROLE_CHANGED
USER_DEACTIVATED
USER_REACTIVATED
USER_INVITATION_RESENT
FIRST_ADMIN_EMAIL_VERIFICATION
```

Novos tipos poderão aparecer sem redesenho da rota. A distinção entre
`USER_CREATED` e `USER_INVITED` não é resolvida aqui.

### IAM e infraestrutura

A futura `audit-api` será read-only. Permissões mínimas esperadas:

- tabela `users`: `dynamodb:GetItem` para reconciliação de autorização e perfil;
- tabela base `audit-events`: `dynamodb:Query` para histórico por recurso;
- GSIs usados pelo contrato: `dynamodb:Query` nos respectivos ARNs.

Não serão concedidos à função:

```text
dynamodb:PutItem
dynamodb:UpdateItem
dynamodb:DeleteItem
dynamodb:TransactWriteItems
dynamodb:Scan
```

Como não há hidratação, `dynamodb:GetItem` na tabela de auditoria não será
concedido. Qualquer expansão exige novo gate explícito.

A implementação futura usará `backend/audit-api`, uma Lambda dedicada e o HTTP
API, JWT Authorizer, tabela `audit-events` e tabela `users` existentes. Não haverá
novo serviço AWS, tabela, GSI, migração do modelo DynamoDB ou mudança no modelo
do Cognito.

### Privacidade

A resposta pública não expõe senhas, tokens, segredos ou códigos MFA, detalhes
completos de infraestrutura, chaves físicas do DynamoDB nem metadados
operacionais internos dos produtores. A exclusão deliberada de `changes` e do
motivo em texto livre reduz o risco de exposição de dados pessoais.

## Consequências

### Positivas

- satisfaz histórico de Student e consulta geral com uma única rota;
- preserva a fronteira dedicada da `audit-api` e IAM somente leitura;
- reutiliza os índices e projeções aprovados sem migração;
- mantém paginação, ordenação e retomada determinísticas;
- impede exposição de campos heterogêneos ou potencialmente sensíveis.

### Negativas

- consultas temporais longas exigem fan-out mensal limitado;
- filtros posteriores podem exigir páginas adicionais do DynamoDB;
- o resumo público não oferece detalhes de mudanças ou motivos;
- o cursor multi-bucket exige estado de continuação mais complexo.

## Testes obrigatórios para a implementação

1. `ACTIVE ADMIN` autorizado e `OPERATOR`, `INVITED` e `INACTIVE` proibidos;
2. JWT ausente ou inválido rejeitado;
3. validação estrita de parâmetros, intervalo máximo e combinações;
4. seleção prioritária de correlação, recurso, ator e período;
5. ausência de `Scan` e interseção de índices;
6. ordenação decrescente e desempate por `eventId`;
7. fan-out mensal limitado aos buckets do intervalo;
8. paginação opaca vinculada aos filtros e ao `limit`;
9. preenchimento da página pública após filtros sob limite interno defensivo;
10. resposta vazia `200` e envelope público exato;
11. exclusão de campos internos, físicos e sensíveis;
12. IAM sem escrita, `Scan` ou `GetItem` na tabela de auditoria;
13. Terraform da Lambda, integração, rota JWT e permissões mínimas;
14. E2E real em `dev` para autorização, access patterns e paginação.

## Relação com decisões anteriores

- mantém a Lambda de domínio `audit-api` da ADR-004;
- mantém tabela separada, append-only, paginação opaca e ausência de `Scan` da
  ADR-005;
- mantém a retenção da ADR-015;
- reutiliza a composição modular da ADR-016;
- aplica sem alteração as chaves, GSIs, projeções e buckets mensais da ADR-021.
