# ADR-018 — Idempotência para operações não HTTP

**Status:** Approved  
**Data:** 2026-08-10

## Contexto

A ADR-012 definiu idempotência para operações de escrita expostas pela API HTTP por meio do header `Idempotency-Key`.

O projeto também possui operações de escrita que não são HTTP, como:

- bootstrap do primeiro Administrador;
- seed de dados fictícios em `dev`;
- reset administrativo de MFA;
- rotinas operacionais controladas;
- ferramentas de retenção, hold ou recuperação.

Essas operações também podem sofrer retries, timeouts e reexecuções humanas ou automáticas.

## Alternativas consideradas

### Opção A — Cada ferramenta implementa sua própria idempotência

Vantagem: menor acoplamento.

Desvantagens:

- padrões diferentes;
- maior risco de duplicidade;
- comportamento inconsistente entre workflows.

### Opção B — `operationId` técnico equivalente ao `Idempotency-Key`

Vantagens:

- mantém o mesmo modelo conceitual;
- evita semântica HTTP artificial;
- permite reutilizar a infraestrutura técnica de idempotência;
- simplifica retries e reconciliação.

### Opção C — Simular `Idempotency-Key` fora de HTTP

Vantagem: nomenclatura única.

Desvantagem: aplica um conceito de transporte HTTP a ferramentas CLI e workflows que não utilizam HTTP.

## Decisão

Adotar a **Opção B**.

Operações não HTTP usarão um identificador técnico denominado:

```text
operationId
```

Esse identificador é semanticamente equivalente ao `Idempotency-Key`, mas adequado ao contexto de CLI, GitHub Actions e ferramentas operacionais.

## Escopo

O `operationId` é obrigatório para operações não HTTP que produzam efeitos persistentes ou externos relevantes.

Exemplos:

- criação do primeiro Administrador;
- seed de dados;
- reset administrativo de MFA;
- hold/release de auditoria;
- rotinas de recuperação;
- ferramentas de reconciliação.

Operações puramente de leitura não exigem `operationId`.

## Composição lógica

O registro técnico de idempotência deverá considerar, no mínimo:

```text
environment
operation
target
operationId
```

Exemplo conceitual:

```text
dev | bootstrap-admin | first-admin | 4af5...
```

O `target` deve ser um identificador técnico e não conter PII completa.

## Regras

- o mesmo `operationId` deve ser preservado em retries;
- mesma operação + mesmo alvo + mesmo payload retorna o resultado anterior ou continua a execução segura;
- mesmo `operationId` com payload incompatível deve falhar;
- retries não podem criar efeitos duplicados;
- o `operationId` não deve ser regenerado durante um retry da mesma execução;
- o valor pode ser gerado pelo workflow, CLI ou ferramenta antes da primeira tentativa;
- registros seguem a retenção técnica de idempotência definida na ADR-012, salvo exceção explicitamente documentada;
- nenhum dado pessoal completo deve ser colocado na chave técnica.

## Relação com ADR-012

A ADR-012 continua sendo a decisão principal sobre idempotência.

- HTTP: usa `Idempotency-Key`;
- não HTTP: usa `operationId`.

Ambos usam o mesmo princípio arquitetural e podem reutilizar a mesma tabela técnica DynamoDB, mantendo separação lógica por tipo de operação.

## Relação com ADR-013

O bootstrap do primeiro Administrador deve receber ou gerar um `operationId` antes de executar qualquer efeito persistente.

O mesmo `operationId` deve ser reutilizado em retries do workflow.

## Relação com ADR-017

O `operationId` participa da correlação do fluxo Cognito ↔ DynamoDB e deve ser preservado durante compensações e reconciliações.

## Consequências

### Positivas

- comportamento idempotente uniforme;
- retries previsíveis;
- menor risco de duplicidade;
- melhor rastreabilidade operacional;
- sem dependência artificial de semântica HTTP.

### Negativas

- ferramentas operacionais precisam gerenciar estado idempotente;
- workflows devem preservar o identificador entre tentativas;
- testes devem cobrir reexecução e conflito de payload.

## Testes mínimos

Para cada ferramenta de escrita não HTTP:

1. primeira execução;
2. retry com mesmo `operationId`;
3. retry após falha parcial;
4. mesmo `operationId` com payload diferente;
5. novo `operationId` para nova operação legítima.

## Refinamento posterior — ADR-024

A **ADR-024 — Protocolo determinístico e trava singleton do bootstrap do primeiro Admin**, aprovada em 2026-08-20, especializa esta decisão para `bootstrap-admin` e `resume-first-admin-invitation`. Ela define UUIDv4 canônico, metadados determinísticos, `ClientRequestToken = operationId` para a transação do bootstrap e transições de estado validadas por `operation`.
