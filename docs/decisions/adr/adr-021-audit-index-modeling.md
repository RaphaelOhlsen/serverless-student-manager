# ADR-021 — Modelagem física dos índices de auditoria

**Status:** Approved
**Data:** 2026-08-18

## Contexto

A tabela `audit-events` possui modelo lógico aprovado com chave composta:

```text
PK = RESOURCE#<resourceType>#<resourceId>
SK = TS#<occurredAt>#EVENT#<eventId>
```

Também foram aprovados os índices:

```text
gsi-actor-time
gsi-correlation-time
gsi-period-time
```

Entretanto, os atributos físicos desses índices e a estratégia de particionamento temporal ainda não haviam sido definidos.

Os requisitos de auditoria determinam consultas por:

- recurso;
- intervalo de datas;
- ator responsável;
- correlation ID;
- tipo de ação;
- resultado.

O MVP atende uma única instituição de pequeno ou médio porte.

A retenção aprovada é:

```text
dev  = 90 dias
prod = 5 anos
```

Nenhum fluxo normal deve depender de `Scan`.

## Alternativas consideradas

### Opção A — Partição temporal global

```text
GSI3PK = PERIOD#ALL
GSI3SK = TS#<occurredAt>#EVENT#<eventId>
```

#### Vantagens

- consulta temporal simples;
- uma única `Query` pode abranger todo o histórico.

#### Desvantagens

- todos os eventos temporais convergem para a mesma partition key lógica;
- aumenta o risco de concentração de carga;
- escala pior conforme o volume cresce.

### Opção B — Bucket diário

```text
GSI3PK = PERIOD#<YYYY-MM-DD>
GSI3SK = TS#<occurredAt>#EVENT#<eventId>
```

#### Vantagens

- distribui bem os eventos ao longo do tempo;
- reduz a quantidade de itens por partition key.

#### Desvantagens

- consultas de períodos longos exigem muitas `Query`;
- 90 dias exigiriam até 90 buckets em `dev`;
- cinco anos podem gerar grande fan-out de consultas.

### Opção C — Bucket mensal

```text
GSI3PK = PERIOD#<YYYY-MM>
GSI3SK = TS#<occurredAt>#EVENT#<eventId>
```

#### Vantagens

- evita uma única partição temporal global;
- mantém baixo o número de buckets consultados;
- é adequado ao volume inicial esperado;
- simplifica consultas mensais e intervalos de datas comuns;
- permite evolução futura para sharding se necessário.

#### Desvantagens

- todos os eventos de um mês compartilham a mesma partition key lógica;
- consultas atravessando meses exigem mais de uma `Query`;
- crescimento significativo poderá exigir sharding.

### Opção D — Bucket mensal com write sharding desde o início

Exemplo:

```text
GSI3PK = PERIOD#<YYYY-MM>#SHARD#<n>
GSI3SK = TS#<occurredAt>#EVENT#<eventId>
```

#### Vantagens

- maior distribuição de escrita;
- reduz risco de concentração excessiva de carga em volumes elevados.

#### Desvantagens

- toda consulta temporal precisa consultar todos os shards;
- aumenta a complexidade da aplicação e da paginação;
- adiciona complexidade desnecessária para o volume inicial do MVP.

## Decisão proposta

Adotar a **Opção C — bucket mensal**, sem sharding inicial.

```text
GSI3PK = PERIOD#<YYYY-MM>
GSI3SK = TS#<occurredAt>#EVENT#<eventId>
```

Essa estratégia oferece o melhor equilíbrio para o volume inicial do MVP entre distribuição de escrita, simplicidade de consulta e quantidade de buckets consultados.

Se métricas de produção demonstrarem concentração excessiva de carga, a estratégia poderá evoluir para bucket mensal com sharding por meio de uma decisão arquitetural posterior.

## Chave principal

```text
PK = RESOURCE#<resourceType>#<resourceId>
SK = TS#<occurredAt>#EVENT#<eventId>
```

O `eventId` no final da sort key garante unicidade mesmo quando dois eventos possuem o mesmo `occurredAt`.

## gsi-actor-time

```text
GSI1PK = ACTOR#<actorId>
GSI1SK = TS#<occurredAt>#EVENT#<eventId>
```

## gsi-correlation-time

```text
GSI2PK = CORRELATION#<correlationId>
GSI2SK = TS#<occurredAt>#EVENT#<eventId>
```

## gsi-period-time

```text
GSI3PK = PERIOD#<YYYY-MM>
GSI3SK = TS#<occurredAt>#EVENT#<eventId>
```

O valor `<YYYY-MM>` é calculado a partir de `occurredAt` em UTC.

Exemplo:

```text
occurredAt = 2026-08-18T13:25:40.123Z
GSI3PK     = PERIOD#2026-08
```

O índice permite selecionar eventos por período sem utilizar `Scan`.

## Consultas atravessando meses

Uma consulta que atravesse mais de um mês deverá consultar cada bucket mensal necessário.

Exemplo:

```text
intervalo = 2026-07-20 até 2026-09-05

buckets:
  PERIOD#2026-07
  PERIOD#2026-08
  PERIOD#2026-09
```

A camada de aplicação deverá:

1. determinar os buckets necessários;
2. executar `Query` em cada bucket;
3. aplicar os limites temporais apropriados em cada consulta;
4. combinar os resultados;
5. preservar a ordenação temporal;
6. aplicar paginação por cursor opaco.

Nenhum `Scan` será utilizado.

## Filtros adicionais

Filtros por:

```text
eventType
result
resourceType
```

serão aplicados após a seleção inicial pelo access pattern mais seletivo disponível.

Caso esses filtros se tornem access patterns de alto volume no futuro, novos índices somente serão criados após medição e decisão arquitetural.

## Projeção dos GSIs

Os três GSIs utilizarão:

```text
projection_type = INCLUDE
```

Os atributos de resumo necessários às consultas serão projetados quando não fizerem parte das próprias chaves do índice:

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

O atributo `changes` não será projetado nos GSIs inicialmente.

Quando detalhes completos forem necessários, a aplicação poderá recuperar o evento original usando a chave primária `PK` + `SK`.

## TTL

A tabela utilizará o atributo:

```text
expiresAt
```

como TTL em Unix epoch seconds.

A retenção será:

```text
dev  = 90 dias
prod = 5 anos
```

O cálculo de `expiresAt` é responsabilidade da aplicação no momento da criação do evento.

## Imutabilidade

A tabela é append-only para as aplicações normais.

Lambdas normais que produzam eventos de auditoria não receberão permissões para:

```text
dynamodb:UpdateItem
dynamodb:DeleteItem
```

Operações excepcionais de retenção, legal hold ou reconciliação utilizarão acesso operacional controlado.

## Convenção física completa

```text
Base table
  PK     = RESOURCE#<resourceType>#<resourceId>
  SK     = TS#<occurredAt>#EVENT#<eventId>

gsi-actor-time
  GSI1PK = ACTOR#<actorId>
  GSI1SK = TS#<occurredAt>#EVENT#<eventId>

gsi-correlation-time
  GSI2PK = CORRELATION#<correlationId>
  GSI2SK = TS#<occurredAt>#EVENT#<eventId>

gsi-period-time
  GSI3PK = PERIOD#<YYYY-MM>
  GSI3SK = TS#<occurredAt>#EVENT#<eventId>

TTL
  expiresAt = Unix epoch seconds
```

## Consequências positivas

- elimina a lacuna existente no modelo físico de auditoria;
- todos os access patterns principais utilizam `Query`;
- mantém a convenção `GSIxPK/GSIxSK` já utilizada no projeto;
- evita uma partição temporal global;
- evita fan-out diário desnecessário no MVP;
- permite evolução futura para sharding;
- reduz duplicação dos eventos completos nos GSIs.

## Consequências negativas

- consultas atravessando meses exigem múltiplas `Query`;
- paginação global entre buckets exige lógica na aplicação;
- filtros não cobertos diretamente pelas chaves podem consumir leituras adicionais;
- crescimento significativo poderá exigir revisão do particionamento temporal.

## Testes obrigatórios

A implementação deverá validar pelo menos:

1. chave composta `PK` + `SK`;
2. existência do `gsi-actor-time`;
3. existência do `gsi-correlation-time`;
4. existência do `gsi-period-time`;
5. mapeamento correto de `GSI1PK/GSI1SK`;
6. mapeamento correto de `GSI2PK/GSI2SK`;
7. mapeamento correto de `GSI3PK/GSI3SK`;
8. projeção `INCLUDE`;
9. TTL habilitado em `expiresAt`;
10. tags e outputs do módulo Terraform.

## Relação com decisões anteriores

- Refina ADR-005 quanto ao modelo físico de `audit-events`.
- Mantém ADR-015 quanto à retenção da auditoria.
- Mantém ADR-016 quanto à organização do módulo `audit_store`.

## Refinamento posterior — ADR-024

A **ADR-024 — Protocolo determinístico e trava singleton do bootstrap do primeiro Admin**, aprovada em 2026-08-20, complementa esta decisão para exigir que o audit event determinístico do bootstrap seja confirmado por leitura consistente durante a reconciliação dos cinco itens da transação.
