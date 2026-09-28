# ADR-036 — Contrato de consulta de aluno por matrícula

**Status:** Approved

**Data:** 2026-09-28

## Contexto

O RF-ALU-003 exige consulta exata de Student pela matrícula normalizada. A
ADR-026 preservou esse requisito, mas deliberadamente deixou rota, parâmetros e
implementação para um contrato separado, sem incluir matrícula nos parâmetros de
`GET /students`.

A matrícula já é obrigatória, imutável e única entre estudantes `ACTIVE` e
`INACTIVE`. A criação definida pela ADR-030 persiste atomicamente uma reserva
técnica que referencia o `studentId`:

```text
PK = UNIQUE#REGISTRATION#<registrationNumber-normalizado>
SK = UNIQUE
studentId = <studentId>
```

Esta decisão fecha o contrato HTTP e a forma de leitura sem alterar o modelo
físico aprovado.

## Decisão

A consulta exata de Student por matrícula será exposta como:

```http
GET /students/by-registration/{registrationNumber}
```

A operação:

- recebe `registrationNumber` exclusivamente como path parameter;
- normaliza e valida a matrícula antes de acessar o DynamoDB;
- resolve a reserva de unicidade e, em seguida, o PROFILE referenciado;
- retorna a mesma representação pública de Student usada por
  `GET /students/{studentId}`;
- permite consultar estudantes `ACTIVE` e `INACTIVE`;
- não aceita nem exige `Idempotency-Key`.

## Contrato HTTP

### Requisição

```http
GET /students/by-registration/{registrationNumber}
Authorization: Bearer <access-token>
```

`registrationNumber` é obrigatório. A consulta é exata após a normalização
canônica definida nesta ADR; não oferece busca parcial, prefixo, substring ou
correspondência aproximada.

### Resposta de sucesso

Sucesso retorna HTTP `200` e exatamente a representação pública adotada por
`GET /students/{studentId}`:

```text
studentId
registrationNumber
fullName
studentEmail
phone
birthDate
status
version
createdAt
updatedAt
```

A resposta não expõe reservas `UNIQUE`, `PK`, `SK`, atributos de índices nem
outros metadados internos. O status do Student pode ser `ACTIVE` ou `INACTIVE`.

## Autenticação e autorização

A rota reutiliza o JWT Authorizer da HTTP API e exige Cognito access token.
Depois da autenticação, reutiliza o modelo funcional do detail/list de Student:

- o ator deve possuir status aplicativo `ACTIVE`;
- somente `ADMIN` e `OPERATOR` são permitidos;
- não existe restrição de ownership ou escopo por Student.

Token ausente ou inválido recebe HTTP `401` pelo authorizer. Identidade
autenticada sem autorização funcional recebe HTTP `403` com a semântica
existente de `FORBIDDEN`.

Esta decisão não introduz nova política de sessão ou de `authVersion`. Qualquer
ampliação transversal dessa política permanece fora deste milestone.

## Normalização da matrícula

A matrícula usa uma única semântica canônica compartilhada com a criação:

1. remover whitespace no início e no fim, quando o transporte preservar esses
   caracteres;
2. converter letras para uppercase;
3. validar o valor normalizado pela expressão `[A-Z0-9-]{4,20}`.

A implementação futura deve possuir uma única fonte reutilizável para essa
normalização e validação. Create Student e lookup por matrícula não podem manter
regras duplicadas ou incompatíveis.

## Padrão de acesso ao DynamoDB

Depois de autorizar o ator e validar a entrada, a sequência lógica é:

1. normalizar `registrationNumber`;
2. executar `GetItem` fortemente consistente em:

   ```text
   PK = UNIQUE#REGISTRATION#<registrationNumber-normalizado>
   SK = UNIQUE
   ```

3. obter e validar o `studentId` da reserva;
4. executar `GetItem` fortemente consistente em:

   ```text
   PK = STUDENT#<studentId>
   SK = PROFILE
   ```

5. verificar que o PROFILE é válido e coerente com a reserva e a matrícula
   normalizada;
6. projetar somente a representação pública de Student.

O lookup não utiliza `Scan`, `Query`, novo GSI, `TransactGetItems`, nova tabela
DynamoDB ou novo serviço AWS. Não há alteração do modelo físico. Leituras fortes
são suficientes porque matrícula é imutável, PROFILE e reserva nascem na mesma
transação e a reserva é preservada durante o ciclo de vida.

## Semântica de erros

| Situação | Status | Semântica |
|---|---:|---|
| Matrícula sintaticamente inválida | `400` | mecanismo existente de validação/erro da API |
| Matrícula válida sem reserva | `404` | `STUDENT_NOT_FOUND` |
| Token ausente ou inválido | `401` | JWT Authorizer existente |
| Ator sem autorização funcional | `403` | `FORBIDDEN` |
| Reserva malformada, incompatível ou apontando para PROFILE ausente/malformado | `500` | `INTERNAL_ERROR` |

Uma reserva existente sem PROFILE íntegro é violação de invariância interna, não
ausência funcional. A implementação não pode convertê-la silenciosamente em
`404` nem expor detalhes físicos na resposta.

Esta ADR reutiliza os mecanismos de erro existentes e não resolve o futuro
Canonical Error Envelope global.

## Auditoria e observabilidade

Leituras bem-sucedidas de Student não geram evento de auditoria atualmente.
Este lookup também não introduz evento de auditoria de leitura bem-sucedida.

A taxonomia transversal de auditoria para tentativas negadas permanece fora
deste milestone. Logs e métricas existentes continuam aplicáveis, sem registrar
tokens, chaves físicas ou dados pessoais completos.

## Idempotência

Idempotência não se aplica. Esta é uma operação `GET` sem efeito de escrita e
não usa `Idempotency-Key` nem registro na tabela técnica de idempotência.

## Impacto de infraestrutura

A implementação posterior deve somente expor a nova route key quando exigido
pela configuração declarativa atual e reutilizar:

- a Lambda `students-api`;
- a HTTP API existente;
- o JWT Authorizer existente;
- a tabela `students` existente;
- a permissão existente `dynamodb:GetItem`.

Não são necessários novo serviço AWS, nova integração Lambda, nova tabela,
novo índice, nova permissão DynamoDB ou ampliação IAM.

```text
NEW_AWS_SERVICE_REQUIRED=NO
IAM_EXPANSION_REQUIRED=NO
DYNAMODB_PHYSICAL_MODEL_CHANGE_REQUIRED=NO
```

## Alternativas consideradas

### `GET /students/registration/{registrationNumber}`

Mantém uma rota dedicada, mas o segmento `by-registration` comunica de forma
mais explícita que se trata de lookup exato por uma chave alternativa.

### Endpoint dedicado com query parameter

Poderia separar o lookup da listagem, mas torna a intenção menos visível no
path sem oferecer benefício para uma única chave exata e obrigatória.

### `GET /students?registrationNumber=...`

Não adotada porque sobrecarrega a listagem, altera seu conjunto fechado de
parâmetros e conflita com a separação estabelecida pela ADR-026.

A rota escolhida distingue explicitamente matrícula de `studentId`, preserva
`GET /students` e `GET /students/{studentId}`, torna a intenção de lookup exato
visível e usa o segmento estático `by-registration` para evitar colisão com a
rota dinâmica de detail.

## Consequências

- RF-ALU-003 passa a possuir contrato HTTP inequívoco.
- Listagem e detail por `studentId` permanecem inalterados.
- A reserva existente permite lookup determinístico sem índice adicional.
- A implementação precisará centralizar a normalização hoje usada pela criação.
- Estado interno corrompido produzirá erro interno observável, nunca falso
  `STUDENT_NOT_FOUND`.
- Testes futuros deverão cobrir normalização, autorização, respostas públicas,
  leituras consistentes, ausência funcional e violações de invariância.

## Não objetivos

- implementar backend, frontend, Terraform ou testes nesta decisão;
- alterar `GET /students` ou `GET /students/{studentId}`;
- oferecer busca parcial, por prefixo ou aproximada de matrícula;
- criar GSI, tabela, serviço AWS ou ampliar IAM;
- alterar a mutabilidade ou a unicidade da matrícula;
- introduzir nova política de `authVersion` ou sessão;
- criar nova taxonomia de auditoria para leituras ou tentativas negadas;
- resolver o Canonical Error Envelope global.
