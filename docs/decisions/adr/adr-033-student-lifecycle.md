# ADR-033 — Ciclo de vida do aluno

**Status:** Approved
**Data:** 2026-09-11

## Contexto

RF-ALU-008/009, RN-ALU-007–010 e UC-005/006 exigem desativação lógica e
reativação de alunos. A operação deve preservar identidade, reservas de unicidade,
histórico e proteção concorrente, sem permitir alteração de status pelo PATCH da
ADR-032. As ADR-012, ADR-021, ADR-026 e ADR-032 fornecem os padrões de
idempotência, auditoria, índices e concorrência.

## Decisão

O lifecycle possui duas operações separadas, protegidas pelo JWT Authorizer e
permitidas somente a usuário `ADMIN` com status aplicativo `ACTIVE`:

```http
POST /students/{studentId}/deactivation
Idempotency-Key: <UUID>
Content-Type: application/json

{"expectedVersion": 1, "reason": "Motivo da desativação"}
```

```http
POST /students/{studentId}/reactivation
Idempotency-Key: <UUID>
Content-Type: application/json

{"expectedVersion": 2}
```

`expectedVersion` é obrigatório, integer >= 1 e não aceita boolean. A desativação
exige `reason` string, com trim externo, entre 5 e 300 caracteres após trim, sem
caracteres de controle ou controles de linha problemáticos. O texto não sofre
normalização semântica adicional. A reativação não aceita motivo. Ambos os bodies
são objetos estritos: campos extras, null, tipos inválidos e chaves JSON duplicadas
são rejeitados.

Sucesso e no-op retornam HTTP 200 com exatamente o modelo público de Student:
`studentId`, `registrationNumber`, `fullName`, `studentEmail`, `phone`,
`birthDate`, `status`, `version`, `createdAt`, `updatedAt`. Metadados internos de
lifecycle não fazem parte da resposta.

## Transições, versão e no-op

| Estado | Operação | Resultado | Versão | Auditoria |
|---|---|---|---|---|
| `ACTIVE` | deactivate | `INACTIVE`, efetiva | +1 | `STUDENT_DEACTIVATED` |
| `INACTIVE` | reactivate | `ACTIVE`, efetiva | +1 | `STUDENT_REACTIVATED` |
| `INACTIVE` | deactivate | HTTP 200, no-op | preservada | nenhuma |
| `ACTIVE` | reactivate | HTTP 200, no-op | preservada | nenhuma |

Para uma operação nova, o serviço resolve replay `COMPLETED`, carrega o Student,
valida `expectedVersion` e somente então avalia a transição. Versão obsoleta retorna
HTTP 409 `STUDENT_VERSION_CONFLICT`, mesmo quando o status já é o desejado.

A transição efetiva condiciona o PROFILE à existência, à versão esperada e ao
status de origem. Falha concorrente com mudança de versão é
`STUDENT_VERSION_CONFLICT`. Se a versão permanecer igual e o status violar o
protocolo esperado, a falha é técnica/de invariante; não existe
`STUDENT_STATE_CONFLICT` neste contrato. Resultados tecnicamente incertos não são
convertidos em conflito de versão antes da resolução idempotente.

## Persistência e atomicidade

Uma transição efetiva usa uma única `TransactWriteItems` com três operações:

1. Update do PROFILE, condicionado à existência, versão e status de origem;
2. Put do evento imutável de lifecycle;
3. Update da idempotência `INPROGRESS -> COMPLETED`, com a resposta pública.

O PROFILE altera somente `status`, `GSI1PK = STATUS#<novo status>`, `version`
incrementada exatamente em 1, `updatedAt` e `updatedBy`. Identidade, matrícula,
dados pessoais, normalizações, criação, `GSI1SK`, `GSI2PK` e `GSI2SK` permanecem.
Não são criados `deactivatedAt`, `deactivatedBy` ou `deactivationReason` no PROFILE.

As reservas `UNIQUE#EMAIL` e `UNIQUE#REGISTRATION` permanecem inalteradas em ambos
os estados. Reativação não readquire reservas. Nenhuma tabela ou índice novo é
necessário. No-op não altera domínio nem auditoria e conclui somente a idempotência
de forma condicional com a resposta corrente.

## Idempotência

As operações usam namespaces `deactivate-student` e `reactivate-student`, UUID
obrigatório e TTL de 24 horas. O hash canônico inclui operação, studentId,
expectedVersion e, na desativação, o motivo validado após trim. O item idempotente
não armazena o motivo bruto; guarda somente o hash técnico e a resposta permitida.

Replay `COMPLETED` precede leitura e versão. Mesma chave/request retorna a resposta
original; request diferente reutiliza `IDEMPOTENCY_KEY_REUSED`; execução simultânea
reutiliza `OPERATION_IN_PROGRESS`. Falhas definitivas não deixam `INPROGRESS`
residual. Resultado incerto consulta consistentemente a idempotência antes de
inferir conflito. A estratégia determinística de `ClientRequestToken` da ADR-032 é
reutilizada como proteção complementar; a idempotência persistida é a fonte durável.

## Auditoria e minimização

Somente transições efetivas geram `STUDENT_DEACTIVATED` ou
`STUDENT_REACTIVATED`, com `result=SUCCESS`, studentId, ator, correlationId,
timestamp e:

```json
{
  "status": {"from": "ACTIVE", "to": "INACTIVE"},
  "version": {"from": 1, "to": 2}
}
```

O evento `STUDENT_DEACTIVATED` também guarda o atributo de negócio `reason`.
Esse texto livre é
potencialmente sensível: fica somente no evento, segue a retenção existente e não é
copiado para PROFILE, resposta pública, logs operacionais, reativação ou hashes de
auditoria. A UI orienta o Administrador a não inserir PII ou dados sensíveis
desnecessários. No-op não gera evento.

## Erros

O contrato reutiliza o envelope e os códigos existentes:

| Situação | HTTP | Code |
|---|---:|---|
| Body, chave ou validação inválida | 400 | `INVALID_REQUEST` |
| Autenticação inválida/ausente | 401 | resposta do JWT Authorizer |
| Ator não ADMIN ativo | 403 | `FORBIDDEN` |
| Student inexistente | 404 | `STUDENT_NOT_FOUND` |
| Versão obsoleta | 409 | `STUDENT_VERSION_CONFLICT` |
| Chave reutilizada com request diferente | 409 | `IDEMPOTENCY_KEY_REUSED` |
| Operação idempotente em andamento | 409 | `OPERATION_IN_PROGRESS` |
| Invariante violada ou falha inesperada | 500 | `INTERNAL_ERROR` |

Não expor motivo, detalhes internos, chaves físicas ou cancellation reasons nos erros.

## Frontend

A UI deve manter o filtro padrão `ACTIVE` e oferecer `ACTIVE`, `INACTIVE` e `ALL`.
Somente ADMIN vê as ações: desativar em aluno ativo, com confirmação e motivo, e
reativar em aluno inativo, com confirmação simples. O frontend carrega o detail
antes da operação para obter `expectedVersion`, usa chave idempotente por tentativa,
impede double-submit, trata `STUDENT_VERSION_CONFLICT` e atualiza a lista após
sucesso. Status continua não editável no `EditStudentForm`.

## Evidências de encerramento

O backend foi publicado na Students Lambda v8 e as duas rotas foram provisionadas
com Terraform (`2 add / 0 change / 0 destroy`). O E2E real em `dev` validou
desativação e reativação efetivas, replay, versão obsoleta, no-op, conflito de
idempotência, auditoria, privacidade do motivo, preservação das reservas e ausência
de `INPROGRESS` residual. A fixture terminou `ACTIVE`.

No frontend, 128 testes, lint e build/typecheck passaram. O E2E manual-assisted
validou filtros `ACTIVE`/`INACTIVE`/`ALL`, detail antes da transição,
`expectedVersion`, Idempotency-Key, desativação, reativação, mensagens de sucesso e
proteção visual contra double-submit, com somente um POST por ação.

As evidências não executadas visualmente permanecem registradas sem reclassificação:

- `VERSION_CONFLICT_LIVE_VISUAL=NOT_RUN`; aceitação
  `PASS_BY_BACKEND_E2E_AND_FRONTEND_AUTOMATION`;
- `OPERATOR_FRONTEND_LIVE_TEST=NOT_RUN`; aceitação
  `PASS_BY_AUTOMATED_AUTHORIZATION_AND_ROLE_VISIBILITY_EVIDENCE`.

`STUDENT_LIFECYCLE_MILESTONE=CLOSED`

## Alternativas rejeitadas

- PATCH genérico de status: mistura lifecycle com edição de dados da ADR-032.
- Exclusão física: pertence ao milestone Delete Student.
- Liberar ou readquirir reservas: quebra unicidade entre ativos e inativos.
- Guardar motivo no PROFILE: duplica histórico e amplia exposição do texto livre.
- Separar domínio, auditoria e conclusão idempotente: permite estado parcial.

## Consequências

As duas rotas reutilizam a Students Lambda, o JWT Authorizer, a integração e as
permissões existentes. O CORS já contempla POST; nenhuma mudança de IAM, tabela,
índice ou configuração da Lambda foi necessária.

Delete Student permanece separado e deferido; hard/soft delete, retenção, liberação
de reservas e recuperação não são decididos aqui.

`DELETE_STUDENT_DEFERRED=yes`
