# ADR-034 — Política de exclusão física de aluno

**Status:** Approved
**Data:** 2026-09-12

## Contexto

O SRS não autoriza exclusão física de Student para `ADMIN` ou `OPERATOR` e não
define requisito funcional ou caso de uso para essa operação. O modelo aprovado
admite somente os estados `ACTIVE` e `INACTIVE`, e a ADR-033 implementa a
desativação como mecanismo de remoção operacional.

Uma exclusão física exigiria decisões adicionais sobre retenção ou anonimização,
reutilização de e-mail e matrícula, conteúdo de auditoria e recuperação. Criar a
operação apenas para completar CRUD contrariaria os requisitos e introduziria
risco de perda irreversível.

## Decisão

A exclusão física de Student fica fora do escopo da v1.

- Deactivate Student é a forma canônica de remoção operacional.
- Não será introduzido o status `DELETED`.
- Não será implementado hard delete de Student.
- Não haverá endpoint ou interface de exclusão física.
- IAM e infraestrutura não receberão permissões ou recursos específicos para
  essa capacidade.
- As reservas de e-mail e matrícula não serão liberadas por exclusão física,
  pois essa operação não existe na v1.

`DELETE_STUDENT_OUT_OF_SCOPE_V1=yes`

## Consequências

- Um Student pode permanecer `INACTIVE` indefinidamente conforme a política
  vigente.
- PROFILE e reservas de e-mail e matrícula permanecem preservados.
- GET detail continua retornando Students `ACTIVE` e `INACTIVE`.
- A listagem continua usando os filtros `ACTIVE`, `INACTIVE` e `ALL`.
- Nenhuma alteração de aplicação, modelo físico ou infraestrutura é necessária.
- Delete Student deixa de ser trabalho funcional pendente da v1.

Uma futura exclusão física exige alteração explícita do SRS e nova decisão
arquitetural. Antes de qualquer implementação, essa revisão deve definir política
de retenção ou anonimização, reutilização das reservas, auditoria e recuperação.

Esta ADR resolve o deferimento registrado pela ADR-033 ao retirar a capacidade do
escopo da v1; não altera o contrato aprovado de desativação e reativação.

## Alternativas rejeitadas

- Hard delete na v1: não possui requisito ou ator autorizado e pode causar perda
  irreversível.
- Novo status `DELETED`: conflita com os únicos estados aprovados e duplica a
  finalidade operacional de `INACTIVE`.
- Liberar reservas sem uma política institucional: permite reutilização de
  identificadores sem decisão de negócio e retenção correspondente.

`DEACTIVATE_IS_CANONICAL_OPERATIONAL_REMOVAL=yes`
