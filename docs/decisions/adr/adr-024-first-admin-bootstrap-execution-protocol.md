# ADR-024 — Protocolo determinístico e trava singleton do bootstrap do primeiro Admin

**Status:** Approved
**Data:** 2026-08-20

## Contexto

O bootstrap do primeiro Administrador é uma operação não HTTP que coordena efeitos em Amazon Cognito e Amazon DynamoDB.

As ADR-013, ADR-017 e ADR-018 já definem:

- execução controlada por utilitário Python e workflow manual;
- criação Cognito com convite suprimido;
- persistência atômica antes do envio do convite;
- idempotência por `operationId`;
- compensação e reconciliação diante de falhas parciais ou resultados ambíguos.

A implementação dos repositories evidenciou lacunas necessárias à futura camada de orquestração:

- formato e responsabilidade dos identificadores técnicos;
- derivação do `ClientRequestToken` do DynamoDB;
- preservação dos dados necessários para reconstruir a mesma transação;
- proteção permanente contra duas operações distintas provisionarem o "primeiro Admin";
- critérios completos para reconhecer a persistência como concluída;
- autoria e timestamps determinísticos em retries;
- semântica final da compensação quando a identidade só pode ser desabilitada.

Sem essas definições, retries após timeout podem reconstruir payloads diferentes, e dois `operationId` distintos podem criar usuários `INVITED` sem uma trava singleton compartilhada.

## Decisão

O bootstrap do primeiro Administrador seguirá o protocolo definido abaixo.

## 1. `operationId`

O `operationId` será:

- obrigatório;
- um UUID versão 4 canônico em lowercase;
- representado no formato textual padrão de 36 caracteres;
- criado ou recebido antes da primeira tentativa;
- preservado sem alteração durante todos os retries e replays.

A futura CLI ou o workflow manual poderá receber um `operationId` fornecido pelo operador ou gerar um UUIDv4 antes do primeiro efeito persistente.

O mesmo `operationId` não poderá ser reutilizado com payload incompatível.

## 2. `ClientRequestToken` do DynamoDB

Para a transação de provisionamento:

```text
ClientRequestToken = operationId
```

O valor será encaminhado:

- sem transformação;
- sem hash;
- sem truncamento;
- sem prefixo ou sufixo adicional.

A futura implementação derivará o argumento do repository diretamente da fonte de verdade:

```text
client_request_token = operation_id
```

O `clientRequestToken` não será persistido como campo separado no registro de idempotência.

O formato UUIDv4 canônico atende ao limite de 36 caracteres da API `TransactWriteItems`.

A idempotência nativa do DynamoDB, com janela de aproximadamente 10 minutos, será uma proteção adicional. A idempotência de aplicação, com retenção lógica de 24 horas, continuará sendo a fonte principal para replay e retomada do fluxo.

## 3. Identificadores técnicos

Os identificadores serão:

```text
userId        = UUIDv4
eventId       = UUIDv4
correlationId = UUIDv4
```

Todos serão:

- gerados uma única vez quando o estado `STARTED` for criado;
- persistidos no contexto idempotente;
- reutilizados em todas as tentativas subsequentes;
- nunca regenerados durante replay.

O `operationId` será gerado ou recebido antes da criação de `STARTED` e também permanecerá imutável.

## 4. Metadados determinísticos no registro de idempotência

Além dos campos já definidos, o registro da operação armazenará:

```text
eventId
occurredAt
auditExpiresAt
actorId
```

Os campos já existentes continuarão preservando, entre outros:

```text
userId
correlationId
operationId
payloadHash
createdAt
updatedAt
expiration
```

Esses metadados não são isoladamente suficientes para reconstruir o USER profile e os demais itens que dependem do payload original.

O registro não armazenará `fullName` ou e-mail adicionalmente. Em replay controlado:

- o payload original de `fullName` e e-mail deverá ser reapresentado;
- `normalize_name` e `normalize_email` serão reaplicados deterministicamente;
- o `payloadHash` do contexto idempotente será validado antes de qualquer reconstrução ou efeito;
- somente um payload compatível poderá ser combinado com `userId`, `eventId`, `correlationId`, timestamps e `actorId` preservados;
- um payload incompatível falhará sem produzir qualquer efeito.

Depois da validação do `payloadHash`, os metadados persistidos e o payload compatível permitirão reconstruir exatamente o mesmo USER profile, marker singleton e audit event após timeout, resposta perdida ou replay.

## 5. Trava singleton permanente

A tabela `users` receberá um item de controle exclusivo do bootstrap inicial:

```text
PK = CONTROL#FIRST_ADMIN_BOOTSTRAP
SK = CONTROL
```

Campos:

```text
userId
operationId
createdAt
createdBy
```

Regras:

- não possui TTL;
- é criado somente pela transação do bootstrap do primeiro Admin;
- nunca é removido automaticamente;
- é protegido por condição de inexistência de `PK` e `SK`;
- impede que outra operação, inclusive com `operationId` diferente, materialize outro "primeiro Admin".

O marker identifica a operação vencedora e permanece como proteção mesmo depois da expiração do registro técnico de idempotência.

## 6. Transação do bootstrap

A transação passará a conter cinco operações `Put` atômicas, nesta ordem:

1. USER profile na tabela `users`;
2. UNIQUE EMAIL na tabela `users`;
3. COGNITO projection na tabela `users`;
4. `CONTROL#FIRST_ADMIN_BOOTSTRAP / CONTROL` na tabela `users`;
5. evento `USER_CREATED` na tabela `audit-events`.

Todos os itens impedirão sobrescrita acidental por condição de inexistência das chaves físicas.

Em concorrência entre operações com `operationId` distintos, somente uma poderá criar o marker. A operação perdedora deverá reconciliar o estado e compensar a identidade Cognito que ela própria criou, quando for possível comprovar essa propriedade com segurança.

O item:

```text
CONTROL#ACTIVE_ADMIN_COUNT / CONTROL
```

não participa da transação porque o usuário é criado como `INVITED`, e usuários convidados não incrementam a quantidade de Administradores ativos.

## 7. Reconciliação DynamoDB

O estado `PERSISTENCE_COMPLETED` somente poderá ser reconhecido depois da confirmação consistente dos cinco itens esperados:

1. USER profile;
2. UNIQUE EMAIL;
3. COGNITO projection;
4. marker singleton;
5. audit event.

Todos deverão corresponder integralmente aos IDs, payload, ator e timestamps preservados no contexto idempotente.

Se todos estiverem ausentes, a camada de orquestração poderá decidir por retry seguro conforme a classificação do erro e o estado atual.

Se houver combinação parcial, marker incompatível ou qualquer item incompatível, a operação não repetirá a transação cegamente e seguirá para reconciliação operacional.

O `ProvisioningRepository` deverá receber futuramente primitives de leitura fortemente consistente para:

```text
get_bootstrap_marker(...)
get_audit_event(...)
```

Esses primitives não fazem parte da alteração documental desta ADR.

## 8. Ator

O ator canônico será:

```text
actorId = github:<GITHUB_ACTOR>
```

Para o USER profile:

```text
createdBy = actorId
updatedBy = actorId
```

O ator original será persistido no estado `STARTED` e reutilizado em todos os retries da mesma operação.

Se outro executor realizar um replay controlado, sua identidade poderá aparecer nos logs operacionais da execução, mas não substituirá a autoria original da criação persistida.

## 9. Tempo

Timestamps persistidos pelo bootstrap usarão UTC RFC3339, precisão de milissegundos e sufixo `Z`.

Exemplo:

```text
2026-08-20T13:45:12.347Z
```

A camada de orquestração usará um `Clock` injetável.

O instante base da criação será capturado uma única vez e persistido antes dos efeitos externos.

Regras:

- `createdAt` será determinístico durante retries;
- `occurredAt` será determinístico durante retries;
- `auditExpiresAt` será calculado uma única vez a partir do instante base e da retenção do ambiente;
- `updatedAt` do registro idempotente poderá refletir o instante de cada transição de estado.

## 10. Retry

O `FirstAdminBootstrapService` não implementará loop próprio de retry no MVP.

Retries normais do AWS SDK poderão continuar habilitados.

Depois de uma falha retornada ao serviço:

- respostas ambíguas serão reconciliadas antes de novo efeito;
- erros transitórios poderão deixar o estado atual disponível para replay;
- o replay controlado reutilizará o mesmo `operationId` e todos os metadados determinísticos.

Esta ADR não define contagem arbitrária de tentativas nem política própria de backoff.

## 11. Estados

O fluxo continuará utilizando somente:

```text
STARTED
COGNITO_CREATED
PERSISTENCE_COMPLETED
INVITATION_SENT
COMPLETED
COMPENSATED
RECONCILIATION_REQUIRED
```

`COMPENSATED` significa que a identidade Cognito criada pela operação foi efetivamente removida.

Se `AdminDeleteUser` falhar e apenas `AdminDisableUser` for concluído, o estado será:

```text
RECONCILIATION_REQUIRED
```

Uma identidade apenas desabilitada ainda existe e exige reconciliação. Nenhum novo estado será criado para esse caso.

Falha no `RESEND` não desfará Cognito nem DynamoDB. O estado permanecerá `PERSISTENCE_COMPLETED` para permitir retry seguro do convite.

## 12. Expiração da idempotência

O registro técnico manterá TTL lógico de 24 horas, conforme ADR-018.

O marker `CONTROL#FIRST_ADMIN_BOOTSTRAP / CONTROL` será permanente e continuará protegendo o sistema depois da expiração do registro idempotente.

Após expiração ou perda do contexto de uma operação incompleta:

- não será criada automaticamente outra identidade para substituir uma identidade possivelmente existente;
- nenhuma identidade será adotada silenciosamente;
- estados incompatíveis seguirão o procedimento de reconciliação operacional.

## 13. Retomada do onboarding após expiração da idempotência

Pode ocorrer o seguinte estado consistente depois da expiração ou indisponibilidade do registro idempotente original:

- a transação de cinco itens foi concluída;
- `CONTROL#FIRST_ADMIN_BOOTSTRAP / CONTROL` existe;
- o USER existe com `role = ADMIN` e `status = INVITED`;
- a identidade Cognito e a projeção de autorização estão consistentes;
- o convite não foi concluído ou precisa ser reenviado.

Nesse cenário, o marker permanente não será removido e um novo bootstrap não será iniciado.

Será permitido um procedimento operacional controlado para retomar o onboarding do mesmo primeiro Admin.

O nome lógico da operação é:

```text
resume-first-admin-invitation
```

A operação:

- receberá um `operationId` distinto do `operationId` expirado do bootstrap original;
- usará UUIDv4 conforme esta ADR;
- criará ou receberá esse `operationId` uma única vez para a operação de retomada;
- reutilizará o mesmo `operationId` em todos os retries e replays dessa retomada;
- será executada por workflow operacional manual, protegido e autenticado na AWS por OIDC;
- localizará consistentemente `CONTROL#FIRST_ADMIN_BOOTSTRAP / CONTROL`;
- obterá do marker o `userId` autoritativo;
- lerá consistentemente `USER#<userId> / PROFILE`;
- exigirá `role = ADMIN`;
- exigirá `status = INVITED`;
- exigirá que a COGNITO projection corresponda ao mesmo `userId`;
- consultará Cognito e confirmará o mesmo `cognitoSub` e um e-mail compatível;
- não criará novo USER;
- não criará novo UNIQUE EMAIL;
- não criará nova COGNITO projection;
- não substituirá a identidade Cognito;
- não removerá nem alterará o marker singleton;
- não incrementará `CONTROL#ACTIVE_ADMIN_COUNT`;
- executará somente `RESEND` para a identidade já reconciliada.

"Novo `operationId`" significa um identificador próprio e distinto para a retomada, não a geração de outro identificador em cada retry.

A identidade idempotente da retomada será:

```text
operation = resume-first-admin-invitation
target = first-admin
```

O registro físico será:

```text
NONHTTP#<environment>#resume-first-admin-invitation#first-admin#<operationId>
```

Essa operação possuirá registro de idempotência próprio com TTL de 24 horas, conforme ADR-018.

Para a retomada, serão reutilizados apenas estados já existentes.

Fluxo normal:

```text
STARTED
→ COMPLETED
```

Fluxo excepcional:

```text
STARTED
→ RECONCILIATION_REQUIRED
```

`COMPLETED` e `RECONCILIATION_REQUIRED` são terminais para aquela operação.

Nenhum novo estado será criado.

Antes do `RESEND`, a operação reconciliará obrigatoriamente:

- marker singleton;
- USER profile;
- COGNITO projection;
- identidade Cognito;
- role, status, e-mail e `cognitoSub`.

Se identidade, `cognitoSub`, e-mail, role, status, projeção ou marker estiver incompatível, o procedimento:

- não produzirá efeitos destrutivos;
- não enviará convite;
- será interrompido;
- exigirá `RECONCILIATION_REQUIRED` ou tratamento operacional equivalente conforme o contexto idempotente da retomada.

Se marker, USER, COGNITO projection e identidade Cognito estiverem consistentes e o USER já estiver `ACTIVE`:

- o procedimento não executará `RESEND`;
- o onboarding será considerado concluído;
- o registro de `resume-first-admin-invitation` transicionará de `STARTED` para `COMPLETED`;
- qualquer replay posterior retornará sucesso sem efeito.

Se o USER estiver `ACTIVE`, mas houver incompatibilidade de identidade, projeção ou marker, o registro transicionará de `STARTED` para `RECONCILIATION_REQUIRED` sem produzir novo efeito.

Depois de `RESEND` confirmado, a retomada transicionará:

```text
STARTED → COMPLETED
```

Se `RESEND` retornar falha explícita, o registro permanecerá `STARTED` para permitir nova tentativa controlada.

Se o resultado de `RESEND` for ambíguo:

- o registro permanecerá `STARTED`;
- um replay controlado será permitido;
- uma nova tentativa poderá produzir um convite adicional;
- nenhum USER, UNIQUE EMAIL, COGNITO projection, marker ou identidade Cognito poderá ser criado ou modificado.

A garantia é de replay seguro sobre o estado persistente e reconciliado, não de entrega exatamente uma vez da mensagem Cognito.

Se o registro da retomada estiver `COMPLETED`, qualquer replay retornará sucesso sem executar novo `RESEND`.

As transições do registro de idempotência são específicas da operação.

Para `bootstrap-admin`:

Fluxo normal:

```text
STARTED
→ COGNITO_CREATED
→ PERSISTENCE_COMPLETED
→ INVITATION_SENT
→ COMPLETED
```

As transições excepcionais continuam sendo as aprovadas para compensação e reconciliação, incluindo `COMPENSATED` e `RECONCILIATION_REQUIRED`, conforme ADR-017 e esta ADR.

Para `resume-first-admin-invitation`:

Fluxo normal:

```text
STARTED
→ COMPLETED
```

Fluxo excepcional:

```text
STARTED
→ RECONCILIATION_REQUIRED
```

`COMPLETED` e `RECONCILIATION_REQUIRED` são terminais para aquela operação.

Isso não permite globalmente a transição `STARTED → COMPLETED` para qualquer operação. A implementação validará as transições considerando o campo `operation`, sem criar novos estados.

`resume-first-admin-invitation` será idempotente e auditável. A taxonomia e o nome final do evento de auditoria poderão ser detalhados no runbook de implementação, desde que não alterem essas garantias.

Esse procedimento é distinto da ADR-019. A ADR-019 trata da recuperação excepcional do único Administrador `ACTIVE` que perdeu acesso ao TOTP; a retomada aqui definida trata exclusivamente do onboarding de um primeiro Admin ainda `INVITED` e com identidade existente e reconciliada.

## 14. Relação com ADRs existentes

Esta ADR:

- refina a ADR-013 ao formalizar o protocolo determinístico e a trava permanente do bootstrap;
- complementa a ADR-017 ao expandir a transação do bootstrap de quatro para cinco itens e detalhar concorrência, replay e compensação;
- especializa a ADR-018 para o bootstrap, definindo UUIDv4 e `ClientRequestToken = operationId`;
- complementa a ADR-021 ao exigir reconstrução e leitura consistente do audit event na reconciliação;
- refina a ADR-023 ao adicionar o item físico `CONTROL#FIRST_ADMIN_BOOTSTRAP / CONTROL` à tabela `users`.

Sua aprovação promove a documentação arquitetural para a baseline v2.7, com atualização de `docs/architecture/data-model.md`, dos documentos consolidados impactados, da versão documental e do manifesto. A implementação correspondente permanece uma etapa posterior.

## Consequências positivas

- uma única operação pode materializar o primeiro Admin;
- o sistema permanece protegido após expiração da idempotência técnica;
- retries reconstruirão o mesmo payload transacional;
- `ClientRequestToken` terá formato válido e origem inequívoca;
- autoria, IDs e timestamps permanecerão estáveis;
- reconciliação verificará também marker e audit event;
- concorrência entre workflows terá resultado determinístico.

## Consequências negativas

- a transação passa de quatro para cinco itens;
- o registro idempotente recebe novos metadados técnicos;
- repositories e testes existentes precisarão evoluir;
- o marker permanente exigirá procedimento operacional explícito para situações excepcionais;
- a implementação completa deverá seguir a baseline documental v2.7;
- a taxonomia de eventos operacionais ainda precisa ser detalhada.

## Testes obrigatórios

A implementação deverá cobrir, no mínimo:

1. duas operações concorrentes com `operationId` diferentes;
2. somente uma operação criando o marker singleton;
3. replay da operação vencedora;
4. compensação da identidade Cognito criada pela operação perdedora;
5. reconstrução da mesma transação após timeout DynamoDB;
6. marker existente e compatível;
7. marker existente e incompatível;
8. audit event ausente durante reconciliação;
9. `ClientRequestToken` exatamente igual ao `operationId`;
10. `userId`, `eventId` e `correlationId` preservados em replay;
11. timestamps e autoria preservados em replay;
12. replay a partir de `PERSISTENCE_COMPLETED` sem nova persistência;
13. ausência de atualização de `CONTROL#ACTIVE_ADMIN_COUNT` para usuário `INVITED`;
14. delete Cognito falhando e disable concluído, resultando em `RECONCILIATION_REQUIRED`;
15. expiração do registro idempotente com marker permanente existente;
16. marker permanente, registro idempotente expirado e `ADMIN` `INVITED` consistente permitindo somente retomada e `RESEND`;
17. recuperação de onboarding nunca criando um segundo primeiro Admin;
18. marker apontando para `userId` incompatível, com interrupção sem efeito;
19. Cognito `sub` incompatível, com interrupção sem efeito;
20. USER `ACTIVE`, sem execução da recuperação de onboarding ou `RESEND`;
21. replay de `resume-first-admin-invitation` sem efeitos inconsistentes e sem alteração do marker;
22. replay de `resume-first-admin-invitation` reutilizando o mesmo `operationId`;
23. estado `COMPLETED` da retomada sem execução de novo `RESEND`;
24. resultado ambíguo de `RESEND` repetido sem criar ou modificar qualquer item persistente;
25. payload incompatível no replay do bootstrap rejeitado antes de qualquer efeito.
26. incompatibilidade na retomada transicionando `STARTED → RECONCILIATION_REQUIRED`;
27. USER `ACTIVE` consistente transicionando `STARTED → COMPLETED` sem `RESEND`;
28. USER `ACTIVE` com identidade, projeção ou marker incompatível resultando em `RECONCILIATION_REQUIRED`;
29. transições de estado validadas pelo campo `operation`;
30. combinação parcial dos cinco itens do bootstrap nunca reparada silenciosamente por criação isolada.

## Ponto ainda a detalhar

A taxonomia completa dos eventos operacionais e de auditoria para falhas, compensações, falhas de compensação, reconciliação e alertas será detalhada durante a implementação e no runbook correspondente.

Esse detalhamento não poderá alterar silenciosamente os estados ou as garantias definidos nesta proposta.
