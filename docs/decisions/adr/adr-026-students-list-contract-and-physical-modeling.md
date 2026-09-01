# ADR-026 — Contrato de listagem e modelagem física de Students

**Status:** Approved  
**Data:** 2026-09-01

## Contexto

O SRS aprova listagem paginada de estudantes, pesquisa case-insensitive por
prefixo de nome e filtro por status. A tabela `students` já possui os índices
`gsi-status-name` e `gsi-all-name`, mas a documentação ainda não define:

- o contrato HTTP de `GET /students`;
- a composição física das chaves desses índices;
- o envelope público da listagem;
- o formato e as regras de validação do cursor opaco.

Sem essas definições, backend, infraestrutura e frontend precisariam adotar
convenções implícitas e potencialmente incompatíveis.

## Escopo

Esta ADR decide exclusivamente a listagem e a pesquisa por prefixo de nome em:

```http
GET /students
```

Criação, atualização, desativação, reativação, exclusão e consulta exata por
matrícula permanecem fora deste escopo.

## Autenticação e autorização

A rota utiliza o JWT Authorizer da HTTP API e recebe o Cognito access token em:

```http
Authorization: Bearer <access-token>
```

Após a validação do JWT, o backend:

1. extrai o Cognito `sub` exclusivamente do contexto autenticado;
2. executa leitura fortemente consistente na tabela `users`:

   ```text
   PK = COGNITO#<sub>
   SK = AUTHORIZATION
   ```

3. exige `status = ACTIVE`;
4. permite somente `role = ADMIN` ou `role = OPERATOR`.

Identidade ausente, inativa ou com role não permitida recebe HTTP `403`. A
ausência ou invalidade do token recebe HTTP `401` pelo JWT Authorizer.

O cursor não participa dessa decisão de autorização e nunca pode ampliar o
conjunto de dados permitido ao usuário.

## Contrato HTTP

### Query parameters

Somente os parâmetros abaixo são aceitos. Parâmetros desconhecidos recebem
HTTP `400`.

| Parâmetro | Obrigatório | Regra |
|---|---:|---|
| `limit` | Não | Inteiro decimal entre `1` e `100`; padrão `20`. |
| `cursor` | Não | Cursor opaco v1 emitido por uma resposta anterior. |
| `status` | Não | `ACTIVE`, `INACTIVE` ou `ALL`; padrão `ACTIVE`. |
| `namePrefix` | Não | Prefixo de nome normalizado pelo backend; de 1 a 150 caracteres antes da normalização. |

Não existem aliases ou parâmetros duplicados. Valores repetidos para o mesmo
parâmetro são inválidos e recebem HTTP `400`.

`status` é case-sensitive e aceita somente os três valores canônicos. Antes de
consultar o índice, `namePrefix` utiliza a mesma normalização determinística
adotada no projeto para nomes:

1. Unicode NFKC;
2. remoção de espaços no início e no fim;
3. redução de sequências internas de whitespace para um único espaço;
4. Unicode case folding.

Um `namePrefix` fornecido que resulte vazio após normalização é inválido.

### Resposta

Uma resposta bem-sucedida usa HTTP `200` e o envelope:

```json
{
  "items": [
    {
      "studentId": "018f0f2e-example",
      "registrationNumber": "MAT-0001",
      "fullName": "Nome do estudante",
      "status": "ACTIVE"
    }
  ],
  "nextCursor": "<opaque>",
  "hasMore": true
}
```

Cada item contém somente:

- `studentId`;
- `registrationNumber`;
- `fullName`;
- `status`.

O envelope não expõe `PK`, `SK`, chaves de GSI, `LastEvaluatedKey` nem campos
físicos internos.

Quando não há resultados:

```json
{
  "items": [],
  "nextCursor": null,
  "hasMore": false
}
```

`hasMore` permanece no contrato porque o SRS exige indicação explícita da
existência de mais resultados. Ele é derivado de `nextCursor`:

```text
hasMore = nextCursor != null
```

Não pode existir resposta com valores contraditórios entre esses dois campos.

## Ordenação e modelagem física

Somente itens principais `STUDENT#<studentId> / PROFILE` participam dos índices.
Itens técnicos de unicidade não recebem chaves de listagem.

### gsi-status-name

```text
GSI1PK = STATUS#<status>
GSI1SK = NAME#<normalizedName>#STUDENT#<studentId>
```

`ACTIVE` e `INACTIVE` utilizam esse índice. A partition key é escolhida pelo
backend a partir do filtro `status` validado.

### gsi-all-name

```text
GSI2PK = ALL
GSI2SK = NAME#<normalizedName>#STUDENT#<studentId>
```

`status=ALL` utiliza esse índice e sua partition key constante.

### Regras de consulta

- Toda listagem utiliza DynamoDB `Query`; `Scan` é proibido.
- A ordenação padrão usa a sort key em ordem ascendente.
- O sufixo `STUDENT#<studentId>` resolve empates de nomes de modo determinístico.
- A pesquisa por prefixo adiciona `begins_with` à sort key:

  ```text
  NAME#<normalizedPrefix>
  ```

- O backend, e nunca o cursor, escolhe tabela, índice e partition key.

## Cursor opaco v1

### Significado de opacidade

“Opaco” significa que a estrutura interna do cursor não faz parte do contrato
do cliente. O cliente deve apenas devolver o valor recebido. Base64 URL-safe é
somente encoding: não fornece confidencialidade e não transforma o cursor em
segredo.

O cursor não é uma fronteira de autenticação ou autorização.

### Payload lógico

Antes do encoding, o payload lógico v1 contém exatamente:

```json
{
  "v": 1,
  "status": "ACTIVE",
  "namePrefix": "ana",
  "position": {
    "studentId": "identificador",
    "normalizedName": "nome normalizado"
  }
}
```

Quando a consulta não possui `namePrefix`, o campo existe com valor JSON
`null`.

Não são permitidos campos ausentes ou desconhecidos. O payload contém somente:

- versão;
- filtros normalizados necessários para vincular o cursor à consulta;
- posição lógica mínima da última página.

Não contém `limit`, PK, SK, chaves de GSI, `LastEvaluatedKey`, token, role,
status do usuário autenticado ou dados pessoais além do nome normalizado que já
determina a posição do item retornado.

`limit` não integra o cursor e pode mudar, dentro dos limites válidos, entre
páginas da mesma consulta.

### Encoding

O documento JSON usa UTF-8 e é codificado com Base64 URL-safe sem padding. O
backend emite as chaves JSON na ordem mostrada para produzir representação
determinística. Clientes não podem depender dessa estrutura ou decodificá-la
como parte do contrato.

### Vínculo com filtros

O backend primeiro resolve defaults e normaliza a consulta atual. Em seguida,
os valores efetivos de `status` e `namePrefix` devem ser exatamente iguais aos
valores contidos no cursor.

Reutilizar o cursor com outro status ou outro prefixo recebe HTTP `400`. O
cursor não pode substituir os filtros atuais.

### Validação

Recebem HTTP `400`:

- versão desconhecida;
- Base64 URL-safe inválido ou com padding;
- UTF-8 ou JSON inválido;
- payload que não seja objeto;
- campo ausente, duplicado ou desconhecido;
- tipo ou valor inválido;
- `status` diferente de `ACTIVE`, `INACTIVE` ou `ALL`;
- `namePrefix` diferente do filtro normalizado atual;
- `studentId` vazio, maior que 128 caracteres ou contendo caracteres fora de
  letras ASCII, dígitos, `_` e `-`;
- `normalizedName` vazio, maior que 512 bytes em UTF-8, com caractere de
  controle ou que não esteja na forma normalizada canônica;
- cursor incompatível com os filtros atuais.

O backend reconstrói o `ExclusiveStartKey` exclusivamente a partir da posição
lógica validada e das convenções desta ADR. Para `ACTIVE` e `INACTIVE`, ele
reconstrói as chaves de `gsi-status-name`; para `ALL`, as de `gsi-all-name`.

Uma alteração arbitrária da posição pode, no máximo, avançar ou reposicionar a
consulta dentro da mesma partition key já autorizada e selecionada pelo
servidor. Ela não pode escolher tabela, índice ou partition key, alterar
status/namePrefix, ampliar autorização ou acessar outro domínio.

### Integridade e autenticidade

O cursor v1 não utiliza HMAC.

Encoding Base64 URL-safe combinado com validação estrutural não prova
autenticidade. Essa limitação é aceita porque:

- o cursor não concede autorização;
- tabela, índice e partition key são escolhidos pelo servidor;
- filtros são vinculados e comparados após normalização;
- somente uma posição lógica composta por valores já observáveis é aceita;
- manipulação não permite atravessar a partition key da consulta.

HMAC ou outro mecanismo de integridade deverá ser reconsiderado se o cursor
passar a carregar dados sensíveis, controlar uma fronteira de segurança ou
autorização, selecionar partições ou produzir impacto além da navegação dentro
do conjunto já autorizado.

## Busca por matrícula

`GET /students` não aceita matrícula como parâmetro.

O requisito de consulta exata por matrícula permanece válido, mas será atendido
por operação e contrato separados. Esta ADR não define rota, parâmetros ou
implementação para essa consulta.

## Semântica HTTP

| Situação | Status |
|---|---:|
| Lista retornada, inclusive vazia | `200` |
| Parâmetro inválido ou desconhecido | `400` |
| Cursor inválido ou incompatível | `400` |
| Token ausente ou inválido | `401` |
| Identidade ausente, inativa ou sem role permitida | `403` |
| Throttling | `429` |
| Falha interna inesperada | `500` |

Erros seguem a estrutura canônica do SRS e não expõem cursor decodificado,
chaves físicas, tokens, stack traces ou detalhes de infraestrutura.

## Impacto de implementação após aprovação

Uma implementação futura deverá:

- adicionar `GET /students` com autorização JWT;
- implementar autorização funcional pela projeção da tabela `users`;
- adicionar as chaves físicas decididas aos writers de estudantes;
- consultar os GSIs com `Query` e paginação por cursor;
- conceder à Lambda `dynamodb:Query` somente nos índices necessários e
  `dynamodb:GetItem` somente na tabela `users`;
- cobrir validação, autorização, índices, ordenação, paginação e erros com
  testes unitários e Terraform diretamente relacionados.

Esta ADR define o contrato para implementação posterior. Implementação,
migração de dados e alteração de infraestrutura continuam sujeitas ao fluxo de
engenharia e às autorizações aplicáveis.

## Consequências positivas

- contrato HTTP e físico deixam de depender de convenções implícitas;
- listagem e prefixo usam `Query`, nunca `Scan`;
- ordenação é estável para nomes repetidos;
- cursor não expõe chaves físicas;
- autorização funcional permanece independente do cursor;
- os dois GSIs já declarados são reutilizados.

## Consequências negativas

- writers futuros devem manter os quatro atributos de GSI;
- Base64 URL-safe não oferece confidencialidade nem autenticidade;
- cursores v1 podem ser reposicionados por clientes, embora sem ampliar acesso;
- alterações no formato exigirão nova versão de cursor;
- itens existentes sem as chaves de GSI não aparecerão na listagem até eventual
  migração explicitamente planejada.

## Testes obrigatórios após aprovação

1. autorização para `ADMIN` e `OPERATOR` ativos;
2. `403` para projeção ausente, status inativo ou role não permitida;
3. defaults e limites de `limit`;
4. validação estrita dos query parameters;
5. listagem `ACTIVE`, `INACTIVE` e `ALL` pelos índices corretos;
6. ordenação e desempate por `studentId`;
7. pesquisa por prefixo normalizado;
8. lista vazia com envelope consistente;
9. emissão e consumo de cursor v1;
10. rejeição de cursor malformado, desconhecido, alterado ou incompatível;
11. reconstrução segura do `ExclusiveStartKey` sem aceitar chaves físicas;
12. ausência de `Scan`;
13. ausência de chaves físicas e dados internos na resposta;
14. rota JWT e permissões IAM mínimas.

## Relação com decisões anteriores

- ADR-003 permanece válida: HTTP API com JWT Authorizer.
- ADR-005 permanece válida: modelagem por access pattern, `Query` e cursor
  opaco, sem `Scan`.
- ADR-006 permanece válida: Cognito autentica e a tabela `users` define role e
  status atuais.
- ADR-023 fornece a normalização de nome reutilizada por esta decisão, sem
  alterar o modelo físico de `users`.
