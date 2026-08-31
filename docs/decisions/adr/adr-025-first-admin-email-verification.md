# ADR-025 — Verificação administrativa do e-mail do primeiro Administrador

**Status:** Approved
**Data:** 2026-08-28

## Contexto

O bootstrap do primeiro Administrador utiliza um `userId` técnico e imutável como `Username` no Amazon Cognito e associa a essa identidade o e-mail normalizado do usuário.

A implementação atual de `AdminCreateUser` envia o atributo:

```text
email = <normalizedEmail>
```

mas não envia:

```text
email_verified = true
```

No Amazon Cognito, um endereço de e-mail configurado como alias somente se torna um alias ativo após ser verificado. A API `AdminCreateUser` permite criar o usuário com `email_verified=true` quando o atributo `email` também é informado.

O bootstrap atual também utiliza:

```text
MessageAction = SUPPRESS
ForceAliasCreation = false
```

Essas garantias devem ser preservadas. Quando `email_verified=true` é enviado, manter `ForceAliasCreation=false` impede a migração silenciosa de um alias que já pertença a outra identidade; nesse caso, o Cognito deve rejeitar a criação com `AliasExistsException`.

Na verificação read-only realizada em 2026-08-27, a identidade do primeiro Administrador já criada no ambiente `dev` possuía o e-mail esperado e o atributo `email_verified` estava ausente. Marcar o e-mail como verificado não confirma a conta, não remove a senha temporária, não elimina `NEW_PASSWORD_REQUIRED` e não reduz a exigência de MFA TOTP.

A ADR-024 define o bootstrap inicial, seus replays, a trava singleton permanente e a operação `resume-first-admin-invitation`. Ela também impede que inconsistências históricas sejam reparadas silenciosamente durante replay.

Portanto, existem dois problemas distintos:

1. corrigir o contrato de criação para futuras identidades do primeiro Administrador;
2. corrigir, de forma explícita e controlada, a identidade histórica já criada.

A segunda necessidade não deve ser incorporada ao replay de `bootstrap-admin`, ao estado `COGNITO_CREATED` nem à retomada de convite.

## Objetivos

Esta decisão tem como objetivos:

- criar futuras identidades do primeiro Administrador com o e-mail já verificado;
- preservar `userId`, `Username` técnico e Cognito `sub`;
- preservar `MessageAction=SUPPRESS`;
- preservar `ForceAliasCreation=false`;
- impedir transferência silenciosa de alias;
- corrigir a identidade histórica sem recriá-la ou substituí-la;
- manter senha temporária, `NEW_PASSWORD_REQUIRED` e MFA TOTP;
- manter o bootstrap e seus replays semanticamente separados da correção administrativa;
- executar a correção histórica por operação idempotente, auditável e de menor privilégio;
- impedir qualquer alteração silenciosa de dados de negócio durante essa correção;
- permitir que o frontend só adote login por e-mail após confirmação objetiva do estado corrigido.

## Fora de escopo

Esta decisão não:

- altera o endereço de e-mail do primeiro Administrador;
- altera `userId`;
- altera o `Username` técnico;
- altera o Cognito `sub`;
- altera `role` ou `status` de negócio;
- altera o marker singleton do bootstrap;
- altera `CONTROL#ACTIVE_ADMIN_COUNT`;
- redefine senha;
- confirma senha temporária;
- envia ou reenvia convite;
- configura ou redefine TOTP;
- reduz a política de MFA;
- substitui a identidade Cognito;
- cria endpoint público;
- cria uma operação genérica para verificar o e-mail de qualquer usuário.

## Alternativas consideradas

### Opção A — Corrigir apenas futuras criações

Adicionar `email_verified=true` ao `AdminCreateUser` utilizado pelo bootstrap.

#### Vantagens

- mudança pequena;
- corrige o contrato para novos ambientes e futuras criações;
- não adiciona operação administrativa.

#### Desvantagens

- não corrige a identidade já existente;
- não libera, por si só, o login por e-mail no frontend;
- mantém uma divergência histórica conhecida.

### Opção B — Corrigir futuras criações e reconciliar separadamente a identidade histórica

Além de corrigir o `AdminCreateUser`, criar uma operação administrativa específica que:

1. descubra o primeiro Administrador pela cadeia autoritativa persistida;
2. reconcilie marker, USER, projeção Cognito e identidade Cognito;
3. confirme que o mesmo e-mail está associado à mesma identidade;
4. execute somente `AdminUpdateUserAttributes` para definir `email_verified=true`;
5. faça read-back;
6. conclua apenas quando a mesma identidade e o mesmo e-mail forem confirmados como verificados.

#### Vantagens

- corrige o contrato futuro e o estado atual;
- preserva a identidade;
- mantém o reparo fora do replay do bootstrap;
- permite auditoria, idempotência e menor privilégio;
- evita procedimentos manuais não versionados.

#### Desvantagens

- adiciona uma capacidade operacional;
- exige workflow, IAM, testes e documentação;
- exige reconciliação rigorosa antes da escrita.

### Opção C — Corrigir manualmente no Cognito

Executar a alteração diretamente pelo console ou por comando administrativo ad hoc.

#### Vantagens

- menor esforço imediato.

#### Desvantagens

- reduz rastreabilidade;
- não possui contrato versionado de replay;
- não prova reconciliação da identidade alvo;
- enfraquece auditoria e revisão;
- cria um precedente operacional fora do modelo aprovado pelo projeto.

## Decisão proposta

Adotar a **Opção B — corrigir futuras criações e reconciliar separadamente a identidade histórica**.

A correção será composta por duas capacidades distintas:

```text
bootstrap-first-admin
  └─ cria futuras identidades com email_verified=true

verify-first-admin-email
  └─ corrige somente a identidade histórica já existente
```

Nenhuma dessas capacidades substitui a outra.

## 1. Contrato para futuras criações

A criação inicial continuará usando:

```text
Username = <userId técnico>
MessageAction = SUPPRESS
ForceAliasCreation = false
```

`UserAttributes` deverá incluir:

```text
email = <normalizedEmail>
email_verified = true
```

O valor de `email_verified` deve ser enviado no formato esperado pela API do Cognito.

Esta decisão não adiciona ao bootstrap:

```text
name
phone_number
phone_number_verified
custom:*
```

`ForceAliasCreation=false` é obrigatório.

Se o endereço já estiver associado como alias a outra identidade, o bootstrap não poderá migrar, tomar ou transferir esse alias. A execução deve interromper o provisionamento e seguir o tratamento explícito de erro/reconciliação aplicável.

## 2. Read-back das novas criações

Uma criação executada sob este novo contrato deve ser considerada compatível somente quando o read-back confirmar, no mínimo:

- identidade Cognito existente;
- `Username` técnico esperado;
- `sub` existente;
- e-mail existente;
- e-mail igual ao valor normalizado esperado;
- `email_verified=true`.

Resultado ambíguo de `AdminCreateUser` deve continuar sendo reconciliado por leitura antes de qualquer decisão de repetir a criação.

Uma identidade incompatível nunca pode ser adotada silenciosamente.

### Compatibilidade com operações históricas

A exigência de `email_verified=true` não autoriza alterar silenciosamente a semântica de replays históricos já iniciados sob o contrato anterior.

A implementação deve separar explicitamente:

- validação estrita das novas criações realizadas sob esta decisão;
- tratamento de operações históricas;
- correção da identidade histórica por `verify-first-admin-email`.

A correção administrativa não deve ser embutida em `get_existing_user_sub()`, `COGNITO_CREATED` ou outra etapa compartilhada se isso transformar automaticamente replays históricos em reparos ou em incompatibilidades não previstas.

## 3. Operação `verify-first-admin-email`

Será criada uma operação não HTTP denominada:

```text
verify-first-admin-email
```

A operação é estritamente destinada à correção da identidade do primeiro Administrador já materializado.

Ela não constitui:

- novo bootstrap;
- replay do bootstrap;
- retomada de convite;
- recuperação de MFA;
- substituição de identidade;
- operação administrativa genérica para usuários.

## 4. Descoberta autoritativa do alvo

A operação não deve confiar em `Username`, `sub` ou e-mail fornecidos livremente pelo operador como fonte autoritativa da identidade alvo.

A identidade deve ser reconstruída a partir da cadeia persistida:

```text
CONTROL#FIRST_ADMIN_BOOTSTRAP / CONTROL
        ↓
      userId
        ↓
USER#<userId> / PROFILE
        ↓
  cognitoSub
        ↓
COGNITO#<cognitoSub>
        ↓
Amazon Cognito
```

O marker singleton identifica o primeiro Administrador.

O `userId`, a projeção Cognito e o próprio Cognito devem convergir para a mesma identidade antes de qualquer escrita.

## 5. Pré-condições obrigatórias

Antes de `AdminUpdateUserAttributes`, a operação deve confirmar:

1. marker singleton existente;
2. marker estruturalmente válido;
3. `userId` autoritativo obtido do marker;
4. USER correspondente existente;
5. `role = ADMIN`;
6. USER em estado compatível com a identidade esperada;
7. COGNITO projection existente;
8. projeção pertencente ao mesmo `userId`;
9. `cognitoSub` persistido de forma consistente;
10. identidade Cognito existente;
11. Cognito `sub` igual ao `cognitoSub` persistido;
12. e-mail Cognito existente;
13. e-mail Cognito igual ao e-mail normalizado persistido para o USER;
14. ausência de qualquer divergência de identidade.

Se qualquer pré-condição falhar, nenhuma atualização Cognito será executada.

A operação não deve tentar corrigir automaticamente marker, USER, UNIQUE EMAIL ou COGNITO projection para satisfazer suas próprias pré-condições.

## 6. Único efeito de identidade permitido

Depois da reconciliação completa, a única alteração de identidade permitida é equivalente a:

```text
AdminUpdateUserAttributes(
    Username=<userId técnico>,
    UserAttributes=[
        {
            "Name": "email_verified",
            "Value": "true"
        }
    ]
)
```

A operação não altera o valor do atributo `email`.

O `Username` técnico imutável é utilizado para endereçar a mesma identidade já reconciliada.

## 7. Efeitos proibidos

`verify-first-admin-email` não pode executar:

```text
AdminCreateUser
AdminDeleteUser
AdminDisableUser
AdminEnableUser
AdminUserGlobalSignOut
AdminSetUserPassword
RESEND
```

Também não pode:

- criar nova identidade;
- substituir identidade;
- alterar `sub`;
- alterar o e-mail;
- transferir alias;
- alterar USER;
- alterar UNIQUE EMAIL;
- alterar COGNITO projection;
- alterar marker singleton;
- alterar contador de Administradores;
- executar compensação destrutiva.

As tabelas de negócio são somente leitura para fins de reconciliação.

Escritas técnicas permanecem permitidas somente quando necessárias à idempotência e à auditoria da própria operação.

## 8. Idempotência e contexto determinístico

A operação seguirá a ADR-018.

Sua identidade lógica será:

```text
operation = verify-first-admin-email
target = first-admin
```

O payload canônico será:

```json
{"target":"first-admin"}
```

O `payloadHash` será calculado deterministicamente a partir desse payload canônico e persistido no registro idempotente.

Cada execução controlada terá:

```text
operationId   = UUIDv4 canônico
eventId       = UUIDv4
correlationId = UUIDv4
```

O `operationId` será criado ou recebido antes da criação de `STARTED`.

`eventId` e `correlationId` serão gerados uma única vez quando `STARTED` for criado.

O registro idempotente deverá preservar, no mínimo:

```text
operation
target
operationId
payloadHash
eventId
correlationId
occurredAt
auditExpiresAt
actorId
createdAt
updatedAt
expiration
```

O ator canônico será:

```text
actorId = github:<GITHUB_ACTOR>
```

`occurredAt` será capturado uma única vez em UTC RFC3339 com precisão de milissegundos e sufixo `Z`.

`auditExpiresAt` será derivado uma única vez da retenção de auditoria aplicável ao ambiente.

`eventId`, `correlationId`, `occurredAt`, `auditExpiresAt` e `actorId` serão reutilizados sem alteração em todos os retries e replays da mesma operação.

O registro físico seguirá o padrão de operações não HTTP:

```text
NONHTTP#<environment>#verify-first-admin-email#first-admin#<operationId>
```

Antes de qualquer leitura de marker, USER, COGNITO projection ou Cognito, um replay deverá:

1. validar estruturalmente o registro idempotente;
2. reconstruir o payload canônico;
3. validar o `payloadHash`;
4. rejeitar `operationId` reutilizado com payload incompatível sem produzir qualquer novo efeito.

O fluxo normal será:

```text
STARTED
→ COMPLETED
```

O fluxo excepcional será:

```text
STARTED
→ RECONCILIATION_REQUIRED
```

`COMPLETED` e `RECONCILIATION_REQUIRED` são terminais para aquela operação.

Falhas explícitas recuperáveis podem manter a operação em `STARTED` para nova tentativa controlada.

Nenhum novo estado é introduzido por esta decisão.

## 9. Identidade já corrigida

Se a reconciliação inicial confirmar:

```text
email_verified = true
```

e todos os demais invariantes permanecerem compatíveis:

- `AdminUpdateUserAttributes` não será chamado;
- nenhum segundo efeito Cognito será produzido;
- o audit event determinístico da operação deverá ser materializado ou confirmado;
- a operação somente poderá transicionar para `COMPLETED` depois da confirmação do audit event correspondente.

Esse comportamento cobre tanto uma execução iniciada quando a identidade já se encontra corrigida quanto um replay após resultado ambíguo no qual a atualização Cognito tenha sido efetivada, mas a auditoria ainda não tenha sido confirmada.

## 10. Read-back após atualização

Depois de uma tentativa bem-sucedida ou de resultado ambíguo de `AdminUpdateUserAttributes`, a operação deve executar `AdminGetUser`.

O efeito somente será considerado confirmado quando o read-back comprovar simultaneamente:

- mesma identidade;
- mesmo `sub`;
- mesmo e-mail;
- `email_verified=true`.

A atualização não será considerada concluída apenas porque a chamada de escrita retornou sem erro.

## 11. Falhas e reconciliação

### Falha antes da escrita Cognito

Nenhuma alteração de identidade ocorreu.

Se a falha for recuperável, a operação pode permanecer `STARTED`.

Divergência de identidade ou estado incompatível deve interromper efeitos e resultar em `RECONCILIATION_REQUIRED`.

### Falha explícita durante a atualização

Não executar qualquer efeito alternativo ou destrutivo.

Se `AdminUpdateUserAttributes` retornar `AliasExistsException`, a operação não poderá tentar migrar, tomar ou transferir o alias.

Esse resultado será tratado como incompatibilidade e deverá levar a:

```text
RECONCILIATION_REQUIRED
```

Para outras falhas recuperáveis, um retry controlado deve repetir as leituras de reconciliação antes de uma nova tentativa.

### Resultado ambíguo

Executar read-back.

Se a mesma identidade estiver reconciliada e `email_verified=true`, considerar o efeito confirmado.

Se o estado permanecer inequivocamente não verificado e todas as pré-condições continuarem válidas, a operação pode permanecer retomável.

Se não for possível determinar o estado com segurança, transicionar para:

```text
RECONCILIATION_REQUIRED
```

### Divergência após a escrita

Qualquer divergência de `sub`, e-mail, marker, USER ou projeção deve impedir novas escritas automáticas e exigir reconciliação operacional.

## 12. Replay

Replay em `COMPLETED` deve retornar sucesso sem executar nova atualização Cognito.

Replay em `RECONCILIATION_REQUIRED` não pode produzir novos efeitos.

Replay em `STARTED` deve:

1. revalidar o registro idempotente e o `payloadHash`;
2. repetir toda a cadeia de reconciliação;
3. não executar nova escrita Cognito se `email_verified=true`;
4. materializar ou confirmar o audit event determinístico correspondente;
5. transicionar para `COMPLETED` somente depois da confirmação desse audit event;
6. executar nova escrita Cognito somente se o estado ainda for inequivocamente compatível e não verificado.

Nenhum replay pode criar, excluir, desabilitar, substituir ou reenviar convite para a identidade.

## 13. Auditoria determinística

A operação deve produzir um audit event determinístico.

A taxonomia final de `eventType` será detalhada no runbook de implementação, sem alterar as garantias desta ADR.

O evento será reconstruído em retries e replays utilizando os metadados preservados no registro idempotente:

```text
eventId
userId
operationId
correlationId
actorId
occurredAt
auditExpiresAt
result
```

O evento deverá usar o mesmo `eventId`, `occurredAt`, `correlationId`, `actorId` e retenção originalmente definidos para a operação.

A operação não poderá transicionar para `COMPLETED` apenas porque `email_verified=true` foi confirmado.

Antes de `COMPLETED`, deverá ser confirmado por leitura consistente que o audit event esperado:

1. existe;
2. possui o `eventId` esperado;
3. corresponde ao mesmo `userId`;
4. corresponde ao mesmo `operationId`;
5. corresponde ao mesmo `correlationId`;
6. preserva `actorId` e `occurredAt`;
7. representa a conclusão da mesma operação.

Se Cognito já estiver corrigido, mas o audit event determinístico estiver ausente, um replay compatível poderá materializar somente o evento esperado e depois confirmá-lo por leitura.

Esse comportamento não autoriza qualquer nova escrita no Cognito quando `email_verified=true` já estiver confirmado.

Se existir audit event incompatível ou se o estado não puder ser reconciliado inequivocamente, nenhuma nova escrita Cognito será executada e a operação deverá seguir para:

```text
RECONCILIATION_REQUIRED
```

A confirmação do audit event determinístico é obrigatória para a transição para `COMPLETED`, mas não constitui pré-condição absoluta para registrar `RECONCILIATION_REQUIRED`.

Ao determinar `RECONCILIATION_REQUIRED`:

- a operação deverá preservar esse estado terminal no registro idempotente;
- se o audit event esperado estiver ausente e puder ser materializado com segurança, a operação poderá registrar o mesmo evento determinístico com o resultado excepcional correspondente;
- um audit event existente e incompatível nunca poderá ser sobrescrito, corrigido ou substituído automaticamente;
- falha ou indisponibilidade da escrita de auditoria não autoriza repetir a escrita Cognito nem produzir qualquer efeito destrutivo;
- quando a auditoria não puder ser confirmada, deverá ser emitido diagnóstico operacional sanitizado para investigação, sem PII.

Assim, uma inconsistência na própria camada de auditoria não cria um impasse que impeça o registro do estado excepcional que exige intervenção operacional.

Não devem ser registrados em auditoria ou logs operacionais:

```text
email
fullName
senha
temporaryPassword
tokens
TOTP
atributos Cognito pessoais
```

O valor real do e-mail pode ser utilizado em memória para reconciliação, mas não deve ser incluído em mensagens operacionais normais.

## 14. Acesso operacional e IAM

A operação deve ser executada por workflow manual protegido do GitHub Actions usando OIDC, conforme a ADR-022.

A policy Cognito deve conter somente as ações necessárias ao contrato, incluindo:

```text
cognito-idp:AdminGetUser
cognito-idp:AdminUpdateUserAttributes
```

limitadas ao User Pool correto.

As permissões DynamoDB devem ser limitadas a:

- leituras necessárias à reconciliação;
- escrita no registro técnico de idempotência;
- escrita do evento de auditoria quando aplicável.

A capacidade não deve receber permissões Cognito destrutivas apenas por conveniência.

Conforme a ADR-022, esta nova capacidade operacional terá role e GitHub Environment próprios em `dev`:

```text
GitHub Environment:
dev-verify-first-admin-email

IAM role:
student-manager-github-dev-verify-first-admin-email
```

A role não reutilizará `student-manager-github-dev-bootstrap-admin` nem `student-manager-github-dev-admin-recovery`, porque os conjuntos de privilégios e a fronteira operacional são distintos.

O GitHub Environment deverá proteger exclusivamente a capacidade `verify-first-admin-email` e será utilizado no subject OIDC exato da trust policy correspondente.

A eventual criação da mesma capacidade em `prod` exigirá decisão e implementação explícitas; esta ADR não autoriza implicitamente sua disponibilização em produção.

Nenhuma credencial AWS permanente será utilizada.

## 15. Relação com ADRs existentes

Esta decisão:

- mantém a ADR-006: Cognito autentica e DynamoDB define `role` e `status`;
- refina a ADR-013: futuras criações do primeiro Admin passam a definir `email_verified=true`;
- mantém a sequência de consistência da ADR-017;
- utiliza a ADR-018 para idempotência não HTTP;
- utiliza a ADR-022 para acesso operacional por OIDC;
- complementa a ADR-024 sem incorporar reparo silencioso ao replay do bootstrap;
- não altera a ADR-019 e não constitui recuperação de MFA.

Nenhuma ADR anterior é substituída.

## 16. Impacto sobre o frontend

O frontend não deve assumir login exclusivo por e-mail até que:

1. o contrato do bootstrap futuro esteja implementado;
2. a identidade histórica tenha sido reconciliada;
3. um read-back confirme `email_verified=true`;
4. uma validação read-only confirme que o alias de e-mail está apto ao fluxo de autenticação esperado.

A correção de `email_verified` não substitui a validação dos desafios de primeiro acesso:

```text
NEW_PASSWORD_REQUIRED
MFA_SETUP
```

## Consequências positivas

- futuras identidades passam a nascer com o contrato correto;
- a identidade histórica pode ser corrigida sem substituição;
- `userId`, `Username` e `sub` permanecem estáveis;
- o bootstrap não ganha reparos implícitos;
- `ForceAliasCreation=false` continua impedindo tomada silenciosa de alias;
- a operação histórica é idempotente e auditável;
- o IAM pode ser restrito à capacidade necessária;
- senha temporária e MFA permanecem inalterados;
- o frontend recebe um critério objetivo para liberar login por e-mail.

## Consequências negativas

- uma nova capacidade operacional precisa ser implementada;
- haverá novas permissões IAM, workflow e testes;
- a reconciliação exige leituras adicionais;
- o tratamento de compatibilidade com replays históricos precisa ser explícito;
- o frontend permanece bloqueado para login por e-mail até a correção ser comprovada;
- a taxonomia final do evento de auditoria ainda precisa ser detalhada.

## Testes obrigatórios

A implementação deverá cobrir, no mínimo:

1. `AdminCreateUser` contendo `email` e `email_verified=true`;
2. `MessageAction=SUPPRESS`;
3. `ForceAliasCreation=false`;
4. ausência de atributos não previstos no payload de criação;
5. `AliasExistsException` sem tentativa de migração ou tomada do alias;
6. read-back de nova criação exigindo e-mail correspondente;
7. read-back de nova criação exigindo `email_verified=true`;
8. `email_verified` ausente;
9. `email_verified=false`;
10. valor incompatível de `email_verified`;
11. resultado ambíguo de `AdminCreateUser` seguido de read-back;
12. identidade incompatível nunca sendo adotada silenciosamente;
13. replay histórico não executando reparo implícito;
14. marker compatível;
15. marker incompatível impedindo escrita;
16. USER compatível;
17. USER incompatível impedindo escrita;
18. COGNITO projection compatível;
19. projeção incompatível impedindo escrita;
20. `sub` Cognito compatível;
21. `sub` incompatível impedindo escrita;
22. e-mail Cognito compatível sem exposição em logs;
23. e-mail divergente impedindo escrita;
24. identidade histórica não verificada executando exatamente uma atualização;
25. identidade já verificada concluindo sem atualização;
26. payload de `AdminUpdateUserAttributes` contendo somente `email_verified=true`;
27. nenhuma alteração do atributo `email`;
28. read-back pós-escrita confirmando mesma identidade, mesmo e-mail e atributo verificado;
29. replay `COMPLETED` sem nova atualização;
30. replay `RECONCILIATION_REQUIRED` sem novo efeito;
31. timeout ou resultado ambíguo seguido de read-back;
32. falha recuperável mantendo caminho de retry controlado;
33. zero chamadas a `AdminCreateUser` na operação corretiva;
34. zero chamadas a `AdminDeleteUser`;
35. zero chamadas a `AdminDisableUser`;
36. zero chamadas a `RESEND`;
37. nenhuma alteração de USER, UNIQUE EMAIL, COGNITO projection ou marker;
38. nenhuma alteração de `CONTROL#ACTIVE_ADMIN_COUNT`;
39. logs sanitizados sem PII;
40. auditoria da operação sem PII;
41. policy Cognito limitada a `AdminGetUser` e `AdminUpdateUserAttributes`;
42. ausência de permissões Cognito destrutivas na capacidade;
43. preservação de `FORCE_CHANGE_PASSWORD` quando aplicável;
44. preservação do fluxo `NEW_PASSWORD_REQUIRED`;
45. preservação do fluxo `MFA_SETUP` e TOTP obrigatório;
46. payload canônico exatamente igual a `{"target":"first-admin"}`;
47. `payloadHash` incompatível rejeitado antes de qualquer leitura de negócio ou Cognito;
48. `eventId`, `correlationId`, `occurredAt`, `auditExpiresAt` e `actorId` preservados em replay;
49. operação nunca transitando para `COMPLETED` antes da confirmação do audit event determinístico;
50. Cognito já corrigido e audit event ausente materializando somente o evento esperado, sem nova escrita Cognito;
51. audit event incompatível resultando em `RECONCILIATION_REQUIRED`;
52. `AliasExistsException` em `AdminUpdateUserAttributes` resultando em `RECONCILIATION_REQUIRED`, sem tentativa de transferência do alias;
53. role `student-manager-github-dev-verify-first-admin-email` sem reutilização de permissões destrutivas;
54. GitHub Environment `dev-verify-first-admin-email` associado exclusivamente à capacidade correspondente;
55. `COMPLETED` exigindo confirmação do audit event determinístico;
56. `RECONCILIATION_REQUIRED` podendo ser persistido mesmo quando a própria auditoria estiver ausente, incompatível ou indisponível;
57. audit event incompatível nunca sendo sobrescrito ou reparado automaticamente.

## Referências normativas

- Amazon Cognito — `AdminCreateUser`
- Amazon Cognito — `AdminUpdateUserAttributes`
- Amazon Cognito — atributos e aliases de usuários
- ADR-006 — Autenticação e autorização
- ADR-013 — Bootstrap do primeiro Administrador
- ADR-017 — Consistência Cognito ↔ DynamoDB
- ADR-018 — Idempotência para operações não HTTP
- ADR-019 — Recuperação excepcional do único Administrador sem TOTP
- ADR-022 — Acesso operacional controlado via GitHub Actions OIDC
- ADR-024 — Protocolo determinístico e trava singleton do bootstrap do primeiro Admin
- Runbook — `operations/first-admin-email-verification.md`

## Promoção documental

A aprovação desta ADR em 2026-08-28 promove a documentação arquitetural para a baseline **v2.8 — Engineering Ready**.

A promoção será realizada de forma coordenada, incluindo:

- registro da ADR-025 como `Approved`;
- atualização do `decision-register.md`;
- atualização de `pending-decisions.md`;
- atualização dos documentos arquiteturais impactados;
- atualização de `DOCUMENTATION-VERSION.md`;
- atualização da ordem canônica de leitura;
- atualização do `MANIFEST.md` e dos hashes SHA-256.

A implementação correspondente permanece uma etapa posterior à aprovação e à promoção documental.
