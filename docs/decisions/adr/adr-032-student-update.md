# ADR-032 — Atualização parcial de aluno

**Status:** Approved
**Data:** 2026-09-10

## Contexto

RF-ALU-007, RF-ALU-011–013 e UC-004 exigem correção de dados, matrícula
imutável, unicidade de e-mail e proteção contra sobrescrita concorrente.
As ADR-005, ADR-012, ADR-021 e ADR-026 definem persistência, idempotência,
auditoria e índices; a ADR-030 fornece o precedente transacional de criação.
As decisões deste contrato foram aprovadas pelo responsável e implementadas nos
gates próprios, sem que o status deste ADR autorize publicação ou operação.

## Decisão e contrato HTTP

`PATCH /students/{studentId}` atualiza parcialmente dados de alunos ACTIVE ou
INACTIVE. Exige access token válido, autorização funcional de ADMIN ou OPERATOR
ativo, `Content-Type: application/json` e `Idempotency-Key` UUID obrigatório,
seguindo a autenticação/autorização e validação da chave já adotadas na ADR-030.

O body é objeto JSON estrito:

- `expectedVersion`: integer obrigatório, >= 1; boolean não é integer válido;
- pelo menos um de `fullName`, `studentEmail`, `phone`, `birthDate`, todos strings;
- campos omitidos são preservados; null, campos extras e chaves duplicadas são rejeitados.

`studentId`, `registrationNumber`, `status`, `createdAt` e `createdBy` não são
aceitos no body. Identidade, matrícula e criação são imutáveis; status permanece
inalterado. Desativação e reativação continuam operações separadas.
Os campos fornecidos reutilizam as regras de validação e normalização da ADR-030:
nome com trim/espaços reduzidos e 3–150 caracteres, sem controles; nome de busca
conforme ADR-026; e-mail com trim/lowercase, até 254 caracteres, sem espaços ou
controles; telefone E.164; nascimento real, não futuro, em AAAA-MM-DD.

Sucesso retorna HTTP 200 com exatamente o modelo público:
`studentId`, `registrationNumber`, `fullName`, `studentEmail`, `phone`,
`birthDate`, `status`, `version`, `createdAt`, `updatedAt`.
Não expõe chaves físicas, índices, autoria ou atributos técnicos.

## Ordem de execução, concorrência e no-op

Após validação da request e autorização do ator:

1. Resolver replay idempotente COMPLETED da mesma operação antes de consultar
   ou validar a versão corrente do aluno; retornar HTTP 200 e resposta original.
2. Para operação nova, carregar o PROFILE; ausência retorna 404.
3. Comparar `expectedVersion` com `PROFILE.version`; divergência retorna
   `409 STUDENT_VERSION_CONFLICT`, mesmo se os valores enviados forem iguais.
4. Somente com versão coincidente, comparar os campos enviados normalizados.
5. Sem alteração efetiva: HTTP 200 com estado corrente, sem incrementar version,
   mudar updatedAt/updatedBy ou gerar STUDENT_UPDATED. A idempotência pode concluir
   e armazenar normalmente essa resposta.
6. Com alteração efetiva: transação condicionada à versão esperada, incremento
   de exatamente 1 e atualização de updatedAt/updatedBy; preservar createdAt/createdBy.

A condição transacional protege contra concorrência após a leitura. Não há
ETag/If-Match. Replay de sucesso expectedVersion=1 retorna a resposta original
version=2; outra chave com expectedVersion=1 encontra conflito se a versão já é 2.

## Atomicidade e reservas

Uma única TransactWriteItems inclui atualização do PROFILE, evento de auditoria
e conclusão durável da idempotência com a resposta pública original.
Se fullName mudar, atualizar normalizedName e as sort keys dos GSIs existentes,
preservando status e identidade. Não criar índices ou tabelas novos.

Se o e-mail normalizado permanecer igual, não tocar sua reserva. Se mudar, a mesma
transação reserva `UNIQUE#EMAIL#<novo>` sem sobrescrever reserva existente, libera
`UNIQUE#EMAIL#<antigo>` do próprio aluno e atualiza PROFILE e auditoria. A unicidade
inclui ativos e inativos. Qualquer condição falha cancela todas as escritas.
A reserva UNIQUE#REGISTRATION permanece intacta; não existe troca ou conflito de
matrícula gerado por este endpoint.

## Idempotência

Reutilizar o padrão ADR-012/ADR-030, com namespace/operação `update-student`,
escopo ambiente/ator/operação/chave e TTL de 24h. O hash da request inclui
studentId, expectedVersion e apenas o payload fornecido após normalização;
não incorporar estado corrente lido do banco nem completar campos omitidos no hash.
Mesma chave/request retorna a resposta original; request diferente usa
`IDEMPOTENCY_KEY_REUSED`; operação simultânea usa `OPERATION_IN_PROGRESS`.
Erros de negócio definitivos não deixam INPROGRESS residual, conforme o padrão
validado de criação. Replays não repetem transação, incremento ou auditoria.
### Conclusão durável e resultado incerto

Para alteração efetiva, esta operação especializa o precedente da ADR-030:
a MESMA TransactWriteItems atualiza PROFILE condicionado a expectedVersion,
troca as reservas de e-mail quando necessário, grava STUDENT_UPDATED e atualiza
o registro idempotente de INPROGRESS para COMPLETED, incluindo a resposta pública
necessária ao replay. A atualização idempotente é condicionada ao estado INPROGRESS
e à identidade da mesma operação, ator e request hash esperados.
Se o domínio desta operação foi commitado, sua idempotência também está COMPLETED;
não existe janela legítima de domínio commitado com idempotência ainda INPROGRESS
por separação dessas escritas. O registro idempotente persistido é a fonte durável.

Após timeout, erro de transporte ou outro resultado tecnicamente incerto:

1. Retries técnicos da MESMA transação podem usar ClientRequestToken determinístico
   e estável, derivado seguramente da identidade da operação/request, distinguindo
   ambiente, ator e operação. O UUID bruto do cliente não é identidade global.
   Respeitar as restrições do DynamoDB; o token é proteção complementar, não
   substitui a idempotência durável.
2. Consultar consistentemente o registro de idempotência antes de interpretar
   a versão corrente do Student.
3. COMPLETED: retornar HTTP 200 e a resposta original armazenada.
4. INPROGRESS: tratar como operação ainda não resolvida segundo
   OPERATION_IN_PROGRESS/recovery; não inferir STUDENT_VERSION_CONFLICT pela
   versão corrente. Resultado incerto não é erro de negócio definitivo e não
   autoriza limpar INPROGRESS como se o cancelamento estivesse comprovado.
5. Retry posterior da mesma operação continua resolvendo idempotência antes da
   checagem da versão corrente.

Para no-op, após encontrar o Student, validar expectedVersion e confirmar ausência
de alteração, finalizar condicionalmente o registro idempotente como COMPLETED
com a resposta corrente, confirmando a identidade da operação/ator/request hash.
Não há escrita de domínio nem evento nesse caminho. Incerteza nessa finalização
é resolvida por leitura/retry idempotente da própria finalização, sem incrementar
version ou gerar auditoria.

### Precedência de conflitos transacionais

A ordem inicial permanece replay COMPLETED, existência (404), versão (409),
avaliação de no-op e execução transacional. As condições são obrigatórias porque
existe corrida entre leitura e commit.

Em cancelamento transacional comprovado, STUDENT_VERSION_CONFLICT tem precedência
sobre STUDENT_EMAIL_ALREADY_EXISTS: se ambas as condições falharem na mesma
tentativa, retornar 409 STUDENT_VERSION_CONFLICT. Se a condição de versão não
falhar e somente a nova reserva de e-mail conflitar, retornar
409 STUDENT_EMAIL_ALREADY_EXISTS. Usar evidências da falha transacional e/ou
diagnóstico read-only consistente, preservando essa precedência.

Reserva antiga que não pertence ao studentId, estado incompatível com invariantes
ou condição técnica não classificável não são conflitos funcionais. Seguem a
convenção de erro técnico/interno (500 INTERNAL_ERROR), sem inventar ou mascarar
esses casos com 409. Resultado tecnicamente incerto segue primeiro a resolução
idempotente descrita acima, não essa classificação de cancelamento comprovado.

## Auditoria sem valores pessoais

Somente alteração efetiva gera `eventType: STUDENT_UPDATED`, `result: SUCCESS`,
com resourceType STUDENT, mesmo studentId, ator autorizado, correlationId,
eventId e timestamp UTC, usando índices/retenção das ADR-015/021.
O evento append-only participa da mesma transação do domínio.

A representação de changes é:

```json
{
  "fields": ["studentEmail", "phone"],
  "version": {"from": 3, "to": 4}
}
```

`fields` contém somente nomes dos campos de negócio efetivamente alterados,
sem duplicatas; `version` registra a transição. Não incluir valores anteriores
ou novos de fullName, studentEmail, phone ou birthDate, nem hashes substitutos.
Não incluir corpo integral. Campos derivados de índice não são campos de negócio.
No-op não gera STUDENT_UPDATED.

## Erros

Usar envelope canônico `code`, `message`, `correlationId`, `details`.

| Situação | HTTP | Code |
|---|---|---|
| Request inválida | 400 | INVALID_REQUEST |
| Autenticação inválida/ausente | 401 | Resposta do JWT Authorizer |
| Ator sem autorização funcional | 403 | FORBIDDEN |
| Aluno inexistente | 404 | STUDENT_NOT_FOUND |
| Versão obsoleta | 409 | STUDENT_VERSION_CONFLICT |
| Novo e-mail reservado | 409 | STUDENT_EMAIL_ALREADY_EXISTS |
| Chave reutilizada com request diferente | 409 | IDEMPOTENCY_KEY_REUSED |
| Operação idempotente em andamento | 409 | OPERATION_IN_PROGRESS |
| Falha inesperada | 500 | INTERNAL_ERROR |

Não expor PII, detalhes internos ou cancellation reasons nos erros.

## Alternativas rejeitadas

- PUT completo: exige retransmitir campos não alterados.
- ETag/If-Match: desnecessário para o contrato aprovado com expectedVersion.
- Checar versão antes de replay COMPLETED: quebra retries de operações concluídas.
- Avaliar no-op antes da versão: aceita requests novas obsoletas.
- Escritas separadas de PROFILE/reservas/auditoria/conclusão idempotente: permitem
  estado parcial ou sucesso de domínio sem replay durável.
- Auditoria com valores pessoais ou seus hashes: viola minimização aprovada.
- Troca de matrícula ou status pelo PATCH: fora do escopo e das regras do domínio.

## Consequências

A implementação inclui rota PATCH, CORS correspondente, autorização funcional,
serviço transacional, idempotência isolada, UI de edição e testes de concorrência,
replay, no-op e unicidade. O IAM concede somente as ações necessárias às operações
transacionais aprovadas. Publicação, infraestrutura e validações reais em `dev`
foram executadas em gates próprios.

## Validação e encerramento

Evidências de encerramento:

- `UPDATE_STUDENT_BACKEND_E2E=PASS`;
- UI detail-before-edit, happy path, conflito de versão, no-op, conflito de e-mail e
  auditoria sem valores ou hashes de PII: `PASS`;
- code guard, evidência unitária e teste de regressão de double-submit: `PASS`;
- `LIVE_VISUAL_EVIDENCE=NOT_PRESERVED` para double-submit;
- `DOUBLE_SUBMIT_ACCEPTANCE=PASS_BY_AUTOMATED_EVIDENCE`;
- `UPDATE_STUDENT_MILESTONE=CLOSED`.

A aceitação automatizada não representa observação visual de double-submit.
