# ADR-023 — Modelagem física da tabela users

**Status:** Approved
**Data:** 2026-08-19

## Contexto

A tabela `users` possui modelo lógico aprovado e é a fonte de verdade da aplicação para perfil, role, status e projeção de autorização.

A documentação canônica v2.5 descreve os seguintes itens:

```text
USER#<userId>
UNIQUE#EMAIL#<normalizedEmail>
COGNITO#<cognitoSub>
CONTROL#ACTIVE_ADMIN_COUNT
```

Também está aprovado o índice:

```text
gsi-all-users-name
```

Entretanto, existe um desalinhamento entre a documentação e a infraestrutura implantada.

A documentação ainda descreve a tabela `users` como possuindo chave primária simples `PK`, enquanto o módulo Terraform `user_store`, seus testes, o Terraform state e a tabela implantada em `dev` utilizam:

```text
PK
SK
```

O índice implantado utiliza:

```text
GSI1PK
GSI1SK
```

A tabela `serverless-student-manager-dev-users` está vazia no momento desta decisão, portanto o contrato físico pode ser refinado antes da criação do primeiro usuário administrativo.

O bootstrap do primeiro Administrador, definido pelas ADR-013, ADR-017 e ADR-018, será o primeiro fluxo a persistir itens nessa tabela e necessita de um contrato físico inequívoco.

## Padrões de acesso

O modelo deve suportar sem `Scan`:

1. consultar usuário por `userId`;
2. consultar projeção de autorização por Cognito `sub`;
3. verificar unicidade e localizar usuário por e-mail normalizado;
4. listar usuários de forma paginada e ordenada por nome;
5. pesquisar usuários por prefixo de nome normalizado;
6. filtrar listagens por `role` e `status`;
7. proteger o contador de Administradores ativos em transações;
8. permitir criação transacional dos itens de provisionamento.

## Alternativas consideradas

### Opção A — Alterar a tabela para chave primária simples

Remover `SK` do módulo Terraform para alinhar a infraestrutura à descrição original da documentação.

#### Vantagens

- corresponde literalmente ao texto original do `data-model.md`;
- modelo físico mais simples.

#### Desvantagens

- exige alteração destrutiva ou substituição da tabela DynamoDB;
- diverge da infraestrutura já implementada e testada;
- reduz flexibilidade para evolução dos itens técnicos;
- não oferece benefício funcional relevante neste momento.

### Opção B — Manter `PK + SK` e formalizar os valores físicos

Manter a infraestrutura existente e definir explicitamente `SK`, `GSI1PK` e `GSI1SK`.

#### Vantagens

- nenhuma alteração destrutiva na infraestrutura;
- alinha documentação, Terraform e implementação;
- torna as operações de leitura e transação inequívocas;
- preserva capacidade de evolução dos itens técnicos;
- segue o padrão já adotado para o item principal de `students`.

#### Desvantagens

- exige atualização da documentação canônica;
- adiciona uma convenção física que deverá ser respeitada por todos os futuros writers da tabela.

## Decisão

Adotar a **Opção B — manter a chave composta `PK + SK` e formalizar os valores físicos**.

## Item principal do usuário

```text
PK = USER#<userId>
SK = PROFILE
```

Atributos de negócio mínimos:

```text
userId
cognitoSub
fullName
normalizedName
email
role
status
authVersion
createdAt
createdBy
updatedAt
updatedBy
```

Campos opcionais continuam seguindo o SRS:

```text
deactivatedAt
deactivatedBy
deactivationReason
```

Para um novo usuário convidado:

```text
role        = ADMIN | OPERATOR
status      = INVITED
authVersion = 1
```

No bootstrap do primeiro Administrador:

```text
role   = ADMIN
status = INVITED
```

O contador de Administradores ativos não é incrementado enquanto o usuário estiver em `INVITED`, conforme ADR-017.

## Normalização de nome

O valor de exibição permanece em:

```text
fullName
```

Para pesquisa e ordenação, o backend gera:

```text
normalizedName
```

A normalização deve ser determinística:

1. normalização Unicode NFKC;
2. remoção de espaços no início e no fim;
3. redução de sequências internas de whitespace para um único espaço;
4. aplicação de Unicode case folding.

O valor original de `fullName` não é substituído.

## Normalização de e-mail

Para unicidade e lookup técnico:

```text
normalizedEmail = trim(email).lower()
```

O e-mail persistido no perfil deve utilizar a forma normalizada.

## Item de unicidade de e-mail

```text
PK = UNIQUE#EMAIL#<normalizedEmail>
SK = UNIQUE
```

Atributos mínimos:

```text
userId
```

A criação utiliza condição de não existência.

O item permite localizar o `userId` por e-mail sem `Scan`.

## Projeção Cognito

```text
PK = COGNITO#<cognitoSub>
SK = AUTHORIZATION
```

Atributos obrigatórios:

```text
userId
role
status
authVersion
```

Essa projeção continua sendo a leitura fortemente consistente utilizada pela autorização, conforme ADR-006.

## Controle de Administradores ativos

```text
PK = CONTROL#ACTIVE_ADMIN_COUNT
SK = CONTROL
activeAdminCount = <inteiro >= 0>
```

`activeAdminCount` é o nome canônico do atributo que armazena a quantidade de usuários com `role = ADMIN` e `status = ACTIVE`.

O item mantém o contador utilizado para proteger o último Administrador ativo.

Usuários `INVITED` não participam do contador.

## gsi-all-users-name

Somente itens `USER#<userId> / PROFILE` participam do índice.

```text
GSI1PK = USERS
GSI1SK = NAME#<normalizedName>#USER#<userId>
```

O sufixo `USER#<userId>` garante unicidade e ordenação determinística quando usuários possuem o mesmo nome.

### Listagem

A consulta utiliza:

```text
GSI1PK = USERS
```

e permite paginação por `Query`, sem `Scan`.

### Pesquisa por prefixo de nome

A aplicação utiliza `begins_with` sobre:

```text
NAME#<normalizedPrefix>
```

no `GSI1SK`.

### Busca por e-mail

Busca exata por e-mail não utiliza o GSI.

O fluxo é:

```text
GetItem UNIQUE#EMAIL#<normalizedEmail> / UNIQUE
  ↓
userId
  ↓
GetItem USER#<userId> / PROFILE
```

### Filtros de role e status

No MVP, filtros de `role` e `status` podem ser aplicados sobre os resultados da `Query` do `gsi-all-users-name`.

Essa decisão evita criar GSIs adicionais antes de existir necessidade comprovada.

Se métricas demonstrarem custo, volume ou comportamento de paginação inadequados, novos access patterns deverão ser avaliados em decisão arquitetural posterior.

## Transação de provisionamento

A criação normal de usuário e o bootstrap do primeiro Administrador utilizam uma única `TransactWriteItems` para persistir:

```text
USER#<userId> / PROFILE
UNIQUE#EMAIL#<normalizedEmail> / UNIQUE
COGNITO#<cognitoSub> / AUTHORIZATION
evento de auditoria
```

A transação utiliza condições de não existência apropriadas e `ClientRequestToken`, conforme ADR-017 e ADR-018.

## Relação com ADR-006

A ADR-006 permanece válida.

A definição:

```text
PK = COGNITO#<sub>
```

passa a ser fisicamente complementada por:

```text
SK = AUTHORIZATION
```

Os atributos da projeção permanecem:

```text
userId
role
status
authVersion
```

## Relação com ADR-017

A ADR-017 permanece válida.

Os itens lógicos definidos nela passam a utilizar as seguintes chaves completas:

```text
USER
PK = USER#<userId>
SK = PROFILE

UNIQUE EMAIL
PK = UNIQUE#EMAIL#<normalizedEmail>
SK = UNIQUE

COGNITO
PK = COGNITO#<sub>
SK = AUTHORIZATION
```

## Relação com ADR-019

A recuperação excepcional do único Administrador preserva:

```text
USER#<userId> / PROFILE
```

e substitui:

```text
COGNITO#<oldSub> / AUTHORIZATION
```

por:

```text
COGNITO#<newSub> / AUTHORIZATION
```

incrementando `authVersion` conforme ADR-019.

## Consequências positivas

- documentação e infraestrutura passam a utilizar o mesmo contrato físico;
- o bootstrap pode ser implementado sem convenções implícitas;
- consultas por `userId`, Cognito `sub` e e-mail utilizam `GetItem`;
- listagem e pesquisa por prefixo de nome utilizam `Query`;
- nenhum fluxo normal depende de `Scan`;
- itens técnicos ficam claramente separados pelo valor de `SK`;
- não é necessária alteração destrutiva da tabela existente.

## Consequências negativas

- todos os writers futuros da tabela `users` devem respeitar as novas convenções;
- `normalizedName` passa a fazer parte do contrato persistido;
- filtros por `role` e `status` no mesmo GSI podem consumir itens que depois são filtrados;
- novos GSIs poderão ser necessários se o volume ou os padrões de acesso crescerem.

## Testes obrigatórios

Devem existir testes para:

1. criação correta de `USER#<userId> / PROFILE`;
2. criação correta de `UNIQUE#EMAIL#<normalizedEmail> / UNIQUE`;
3. criação correta de `COGNITO#<sub> / AUTHORIZATION`;
4. `authVersion = 1` na criação inicial;
5. `GSI1PK = USERS`;
6. composição determinística de `GSI1SK`;
7. normalização determinística de nome;
8. normalização de e-mail;
9. rejeição de e-mail duplicado;
10. lookup por `userId`;
11. lookup por `cognitoSub`;
12. lookup por e-mail;
13. listagem paginada pelo GSI;
14. pesquisa por prefixo de nome;
15. ausência de incremento do contador de Administradores ativos para usuário `INVITED`.
