# ADR-027 — Ativação do usuário após o primeiro login

**Status:** Approved
**Data:** 2026-09-02

## Contexto

Usuários administrativos são provisionados no estado de negócio `INVITED`. O
Amazon Cognito conduz `NEW_PASSWORD_REQUIRED`, a definição da senha permanente
e o cadastro obrigatório do TOTP, mas esses efeitos não alteram a tabela
`users`, fonte de verdade de `role` e `status` da aplicação.

Após a conclusão real do primeiro acesso, uma identidade pode estar
`CONFIRMED`, com TOTP configurado, enquanto USER e projeção de autorização
permanecem `INVITED`. Nesse estado, a autorização funcional rejeita corretamente
as rotas protegidas que exigem `ACTIVE`.

Não existe transação distribuída entre Cognito e DynamoDB. A ativação precisa
reconciliar o estado Cognito no servidor e efetuar a mudança de negócio de modo
atômico, idempotente e auditável, sem confiar em declarações do frontend.

## Escopo

Esta ADR decide exclusivamente a transição de autoativação:

```text
INVITED → ACTIVE
```

depois do primeiro login concluído. Criação, convite, reenvio, desativação,
reativação de usuário `INACTIVE` e recuperação de MFA permanecem fora do escopo.

## Alternativas consideradas

### Opção A — Endpoint backend autenticado explícito

Depois de obter um access token válido, o cliente solicita a finalização do
próprio onboarding. O backend deriva a identidade do JWT, consulta Cognito e
executa a transação DynamoDB.

Vantagens:

- fronteira e contrato observáveis;
- retry e idempotência explícitos;
- reconciliação Cognito server-side imediatamente antes da escrita;
- auditoria e respostas de conflito determinísticas;
- não depende de segredo ou estado declarado pelo frontend.

Desvantagens:

- adiciona uma rota e permissões Cognito read-only à `users-api`;
- o frontend precisa chamar a operação após concluir os desafios.

### Opção B — Ativação lazy em qualquer primeira chamada autenticada

Vantagem: dispensa uma chamada explícita do cliente.

Desvantagens:

- mistura escrita de onboarding com operações de leitura ou de outros domínios;
- amplia IAM e responsabilidade de múltiplas Lambdas;
- torna retries, auditoria e falhas menos previsíveis;
- pode produzir efeitos em uma rota semântica de leitura.

### Opção C — Trigger ou evento Cognito

Vantagem: aproxima a ativação do ciclo de autenticação.

Desvantagens:

- não há evento transacional único que prove simultaneamente senha permanente,
  identidade reconciliada e o fator TOTP canônico requerido;
- aumenta acoplamento a triggers e tratamento assíncrono;
- dificulta resposta imediata e idempotência visível ao cliente.

### Opção D — Operação administrativa

Vantagem: controle humano explícito.

Desvantagens:

- exige intervenção para todo primeiro acesso;
- não corresponde ao fluxo normal aprovado no SRS;
- cria atraso e risco operacional desnecessários.

## Decisão proposta

Adotar a **Opção A — endpoint backend autenticado explícito**:

```http
POST /users/me/activation
Authorization: Bearer <access-token>
Idempotency-Key: <uuid>
```

A rota pertence ao futuro domínio `users-api`, usa JWT Authorizer e aceita
somente access token. Não aceita corpo nem identificador de usuário. O `sub` é
extraído exclusivamente do contexto JWT validado pelo API Gateway.

Essa rota é a única exceção de onboarding que permite uma projeção funcional
no estado `INVITED`. Ela não concede acesso geral a usuários convidados.

## Identidade e autorização da operação

O chamador pode ativar somente a própria identidade. O backend:

1. extrai `sub` do access token validado;
2. lê consistentemente `COGNITO#<sub> / AUTHORIZATION`;
3. obtém o `userId` autoritativo da projeção;
4. lê consistentemente `USER#<userId> / PROFILE`;
5. exige igualdade de `userId`, `cognitoSub`, `role`, `status` e `authVersion`
   entre os itens aplicáveis;
6. aceita somente `role = ADMIN | OPERATOR` e `status = INVITED | ACTIVE`;
7. usa o `userId` técnico como `Username` nas consultas administrativas ao
   Cognito.

O cliente não pode enviar `userId`, `sub`, role, status nem qualquer indicador
como `MFA_DONE=true`.

## Pré-condições Cognito

Antes de qualquer escrita, o backend executa duas consultas read-only no mesmo
user pool e para o mesmo `Username = userId`.

### `AdminGetUser`

Deve confirmar:

- `Enabled = true`;
- `UserStatus = CONFIRMED`;
- atributo `sub` igual ao `sub` do JWT, ao `cognitoSub` do USER e à chave da
  projeção de autorização;
- atributo `email_verified = true`.

### `AdminGetUserAuthFactors`

Deve confirmar:

```text
ConfiguredUserAuthFactors contém SOFTWARE_TOKEN
```

`ConfiguredUserAuthFactors` é a evidência canônica de TOTP configurado para
esta operação.

`PreferredMfaSetting` não é exigido. `UserMFASettingList` ausente, nulo ou vazio
não constitui evidência de que TOTP não esteja configurado e não pode bloquear
a ativação quando `ConfiguredUserAuthFactors` contém `SOFTWARE_TOKEN`.

As duas respostas devem identificar o mesmo `Username` técnico esperado.
Qualquer ausência, divergência ou pré-condição não satisfeita interrompe o fluxo
antes da transação.

A ativação não modifica Cognito.

## Contrato HTTP

A requisição não possui body nem parâmetros de query.

Resposta `200 OK`, tanto na primeira ativação quanto no caso já `ACTIVE` e
reconciliado:

```json
{
  "userId": "identificador-interno",
  "role": "ADMIN",
  "status": "ACTIVE",
  "authVersion": 1
}
```

O `authVersion` não é incrementado pela ativação: a identidade Cognito não é
substituída.

| Situação | Status |
|---|---:|
| Ativação concluída | `200` |
| Usuário já `ACTIVE` e integralmente reconciliado | `200` |
| `Idempotency-Key`, body, query ou formato inválido | `400` |
| Token ausente, inválido, expirado ou que não seja access token | `401` |
| Projeção ausente, identidade incompatível ou role não permitida | `403` |
| Cognito ainda não satisfaz as pré-condições | `409` |
| Estado aplicativo incompatível, inclusive `INACTIVE` | `409` |
| Falha interna inesperada | `500` |

Erros seguem a estrutura canônica do SRS e não expõem token, `sub`, e-mail,
atributos Cognito completos, chaves físicas ou detalhes de infraestrutura.

## Transação DynamoDB

Para `INVITED`, uma única `TransactWriteItems` executa todas as mudanças ou
nenhuma delas.

### USER principal

Atualiza:

```text
USER#<userId> / PROFILE
status = INVITED → ACTIVE
updatedAt = <occurredAt>
updatedBy = <userId>
```

A condição exige item existente, `status = INVITED`, `role` e `authVersion`
esperados e `cognitoSub = <sub>`.

### Projeção de autorização

Atualiza:

```text
COGNITO#<sub> / AUTHORIZATION
status = INVITED → ACTIVE
```

A condição exige item existente, `status = INVITED` e igualdade do `userId`,
`role` e `authVersion` esperados.

### Contador de Administradores ativos

Para `role = ADMIN`, a transação atualiza:

```text
CONTROL#ACTIVE_ADMIN_COUNT / CONTROL
activeAdminCount = activeAdminCount + 1
```

O contador pode ser inicializado atomicamente em `1` quando ainda não existe e
somente aceita valor numérico não negativo quando existente. O incremento faz
parte da mesma transação condicionada pelos dois estados `INVITED`; portanto,
um replay ou concorrente não pode incrementá-lo sem também vencer a única
transição válida.

Para `role = OPERATOR`, o contador não participa da transação.

### Auditoria

A transação insere um evento imutável na tabela `audit-events` com condição de
inexistência das chaves:

```text
eventType     = USER_ACTIVATED
resourceType  = USER
resourceId    = <userId>
actorId       = <userId>
result        = SUCCESS
eventId       = <eventId preservado pela idempotência>
correlationId = <correlationId da requisição>
occurredAt    = <UTC>
changes       = status: INVITED → ACTIVE
```

O evento não contém e-mail, `sub`, token, senha, segredo TOTP ou código TOTP.

As condições dos updates impedem dupla ativação, incremento duplicado,
identidade divergente e transição a partir de estado diferente de `INVITED`.
Uma falha condicional cancela toda a transação.

## Idempotência e retries

A operação é uma escrita HTTP e segue a ADR-012:

- `Idempotency-Key` UUID obrigatório;
- escopo lógico inclui ambiente, ator, operação `activate-current-user` e chave;
- payload canônico é a requisição sem body vinculada ao próprio `userId`;
- `eventId`, `correlationId`, `occurredAt` e resposta são preservados no contexto
  idempotente;
- `TransactWriteItems` usa `ClientRequestToken` derivado deterministicamente do
  contexto idempotente durante a janela nativa do DynamoDB;
- mesma chave e mesmo alvo retorna a resposta preservada;
- chave reutilizada em contexto incompatível recebe `409`.

A transação condicional protege os efeitos de negócio, mas não substitui a
tabela de idempotência exigida pela ADR-012.

Se a transação concluir e a resposta ou conclusão do registro idempotente se
perder, o retry lê USER e projeção consistentemente. Se ambos estiverem
`ACTIVE`, coerentes com a mesma identidade, role e `authVersion`, retorna `200`
e conclui o replay sem novo contador nem novo evento.

Uma nova chave para usuário já `ACTIVE` também retorna `200` depois de todas as
pré-condições e reconciliações, sem executar nova transação, incrementar o
contador ou inserir outro `USER_ACTIVATED`.

Não existe estado DynamoDB parcialmente aplicado: `TransactWriteItems` é
atômico. Falhas Cognito são somente de leitura e ocorrem antes da transação.

## Consistência entre Cognito e DynamoDB

Não existe transação distribuída entre `AdminGetUser`,
`AdminGetUserAuthFactors` e `TransactWriteItems`.

As leituras Cognito fornecem uma evidência server-side imediatamente anterior à
ativação. A transação revalida, no momento da escrita, todo o estado aplicativo
que pode ser protegido por condições DynamoDB. Alteração concorrente ou
inconsistência em USER/projeção cancela a operação sem mutação parcial.

Mudanças Cognito posteriores à leitura não são escondidas nem compensadas pela
ativação. A operação não escreve no Cognito; divergências comprovadas seguem
tratamento seguro e reconciliação posterior, sem adoção silenciosa de outra
identidade.

## Auditoria de tentativas negadas

O evento `USER_ACTIVATED` registra somente sucesso e integra a transação de
ativação. Tentativas negadas, conflitos e falhas continuam sujeitas à taxonomia
futura de auditoria operacional já registrada em `pending-decisions.md`.

Esta ADR não amplia essa taxonomia nem autoriza eventos com PII desnecessária.

## Segurança

- JWT Authorizer valida o access token antes da Lambda;
- `sub` vem somente do contexto autenticado;
- a rota permite apenas autoativação;
- USER, projeção e Cognito devem apontar para a mesma identidade;
- o frontend não declara conclusão de senha ou MFA;
- TOTP é comprovado por `ConfiguredUserAuthFactors = SOFTWARE_TOKEN`;
- `UserMFASettingList` e `PreferredMfaSetting` não são usados como veto;
- `INACTIVE` nunca é promovido por esta operação;
- condições transacionais impedem contar um ADMIN duas vezes;
- nenhum segredo, token ou dado pessoal completo é registrado.

## Impacto futuro de implementação

### Backend

- criar ou ampliar `users-api` para a rota de ativação;
- implementar leituras consistentes de USER e projeção;
- implementar cliente Cognito para `AdminGetUser` e
  `AdminGetUserAuthFactors`;
- implementar idempotência HTTP, transação, reconciliação e erros seguros;
- confirmar no build que as versões empacotadas de Boto3/Botocore expõem
  `admin_get_user_auth_factors`; a baseline atual `1.43.70` já expõe a operação;
- não depender da AWS CLI local para essa chamada.

### Terraform e IAM

- adicionar `POST /users/me/activation` com JWT Authorizer;
- conceder somente:
  - `cognito-idp:AdminGetUser` no user pool aplicável;
  - `cognito-idp:AdminGetUserAuthFactors` no user pool aplicável;
  - leituras e escritas DynamoDB estritamente necessárias nos itens/tabelas de
    users, idempotência e auditoria;
- não conceder operações Cognito de escrita para a ativação.

### Frontend

- chamar o endpoint depois que Cognito concluir todos os desafios e emitir a
  sessão autenticada;
- usar `Idempotency-Key` estável durante retries da mesma finalização;
- somente entrar na área protegida após resposta `200`;
- não enviar identidade nem estado MFA no payload.

### Testes

- JWT ausente/inválido e token que não seja access token;
- autoativação e impossibilidade de escolher outro usuário;
- todas as pré-condições de `AdminGetUser`;
- `ConfiguredUserAuthFactors` com e sem `SOFTWARE_TOKEN`;
- `UserMFASettingList` ausente sem falso negativo;
- USER/projeção ausente ou incompatível;
- ativação ADMIN e OPERATOR;
- inicialização e incremento do contador ADMIN;
- concorrência, replay e usuário já `ACTIVE` sem efeitos duplicados;
- `INACTIVE` rejeitado;
- falhas condicionais sem mutação parcial;
- auditoria mínima e ausência de PII;
- IAM mínimo e rota JWT.

## Consequências positivas

- fecha o gap entre onboarding Cognito e autorização funcional;
- não confia em sinalização do frontend;
- permite retry seguro e resposta determinística;
- mantém contador e auditoria coerentes com a ativação;
- não modifica Cognito durante a finalização.

## Consequências negativas

- adiciona uma chamada explícita depois da autenticação;
- requer duas leituras administrativas Cognito por ativação;
- mantém uma pequena janela inevitável entre leitura Cognito e escrita DynamoDB;
- exige tratamento especial de autorização para `INVITED` somente nessa rota.

## Relação com decisões anteriores

- ADR-006 permanece válida: Cognito autentica e DynamoDB autoriza.
- ADR-012 governa `Idempotency-Key` e replay HTTP.
- ADR-013 e ADR-017 permanecem válidas para provisionamento e convite.
- ADR-014 permanece válida para MFA TOTP obrigatório.
- ADR-015 governa retenção dos eventos de auditoria.
- ADR-019 permanece exclusiva à recuperação do único ADMIN já `ACTIVE`.
- ADR-021 define as chaves e índices físicos do evento de auditoria.
- ADR-023 permanece válida para USER, projeção e contador de ADMINs ativos.
- ADR-024 permanece válida para o bootstrap e seu marker singleton.

## Estado documental

Após aprovação humana, o contrato normativo mínimo foi consolidado no SRS, no
modelo de dados e no documento de segurança. Implementação e provisionamento
continuam sujeitos ao fluxo de engenharia e a autorização específica.
