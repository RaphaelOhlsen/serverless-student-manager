# Arquitetura de segurança

**Versão:** 2.9
**Status:** Approved

## 1. Autenticação

Amazon Cognito gerencia:

- credenciais;
- senha temporária;
- recuperação;
- MFA TOTP;
- tokens;
- proteção contra tentativas repetidas.

Não existe cadastro público administrativo.

## 2. Senhas

Política mínima:

- 12 caracteres;
- maiúscula;
- minúscula;
- número;
- caractere especial.

A aplicação não recebe nem armazena senhas.

## 3. Tokens e sessão

```http
Authorization: Bearer <access-token>
```

- access token: 15 min;
- ID token: 15 min;
- refresh token: 8 h;
- rotação de refresh token habilitada;
- Lambda valida `token_use=access`.

## 4. MFA

TOTP obrigatório para `ADMIN` e `OPERATOR`.

SMS MFA, e-mail MFA e remembered devices ficam desabilitados.

## 5. Autorização

O Cognito `sub` resolve:

```text
COGNITO#<sub>
```

A aplicação usa `role` e `status` atuais no DynamoDB.

- `ADMIN`: acesso administrativo;
- `OPERATOR`: operações rotineiras de alunos.

## 6. Menor privilégio

- `students-api`: alunos + auditoria;
- `users-api`: usuários + Cognito + auditoria;
- `audit-api`: leitura da auditoria;
- uma função IAM de deploy por ambiente;
- roles operacionais separadas das roles de deploy;
- roles operacionais separadas por capacidade e por ambiente;
- trust policies OIDC com `sub` exato, sem wildcards;
- nenhuma credencial AWS permanente no GitHub;
- frontend sem acesso direto ao DynamoDB.

## 7. Bootstrap e recuperação

O primeiro Administrador é criado pelo workflow manual `.github/workflows/bootstrap-first-admin.yml`, com OIDC e a role `student-manager-github-dev-bootstrap-admin`, associada ao GitHub Environment protegido `dev-bootstrap-admin`.

Se o primeiro Administrador permanecer `INVITED` depois da expiração do contexto idempotente original, o workflow manual `.github/workflows/resume-first-admin-invitation.yml` poderá somente reenviar o convite para a identidade existente e integralmente reconciliada. O procedimento não cria outro usuário, não substitui a identidade e não altera o marker singleton.

Bootstrap e retomada são capacidades separadas. A role dedicada `student-manager-github-dev-resume-first-admin-invitation` foi aplicada e verificada na AWS. Ela concede somente leitura da identidade persistida, leitura do Cognito, `AdminCreateUser` para `RESEND` e operações técnicas no registro idempotente. Não concede delete ou disable Cognito, `TransactWriteItems`, wildcards de ação ou recurso, nem acesso às tabelas de auditoria e alunos.

Os Environments `dev-bootstrap-admin` e `dev-resume-first-admin-invitation` exigem reviewer, impedem bypass administrativo e vinculam os jobs a trust policies OIDC com `sub` exato, sem wildcards. Os workflows usam credenciais temporárias OIDC e não armazenam credenciais AWS estáticas. As capacidades possuem infraestrutura, IAM, Environments e variables configurados e validados, sem Environment secrets, e seus arquivos estão na default branch `main`.

Uma primeira execução do bootstrap falhou após a criação suprimida da identidade Cognito e antes da persistência do domínio. O estado parcial permanece sujeito a reconciliação controlada; não houve convite, criação autoritativa do Administrador ou validação end-to-end. O workflow lê nome e e-mail do payload local do evento, registra masking antes do uso e não os declara no bloco `env`. Esses valores continuam sendo inputs comuns de `workflow_dispatch`, não secrets, portanto permanece risco residual de exposição na metadata ou UI da plataforma.

A recuperação excepcional do único Administrador usa roles operacionais independentes e GitHub Environments próprios:

- `dev-admin-recovery`;
- `prod-admin-recovery`.

Bootstrap, retomada e recuperação possuem trust policies e policies IAM próprias, com menor privilégio e sem reutilização das roles de deploy.

A ADR-025 aprova uma quarta capacidade operacional distinta em `dev`, denominada `verify-first-admin-email`. Sua finalidade exclusiva é reconciliar o primeiro Administrador existente e, quando todos os invariantes forem confirmados, definir somente `email_verified=true` na mesma identidade Cognito por `AdminUpdateUserAttributes`.

A capacidade declarada no repositório utilizará:

```text
GitHub Environment:
dev-verify-first-admin-email

IAM role:
student-manager-github-dev-verify-first-admin-email

IAM managed policy:
student-manager-dev-verify-first-admin-email
```

Essa capacidade preserva `userId`, `Username`, Cognito `sub`, e-mail, senha temporária e MFA. Ela não pode criar, substituir, excluir, desabilitar ou habilitar identidade, alterar senha, executar `RESEND`, transferir alias ou modificar USER, UNIQUE EMAIL, COGNITO projection, marker singleton ou contador de Administradores.

A trust declarada usa o provider OIDC existente, audience
`sts.amazonaws.com` e subject exato do Environment, sem wildcard. A role não
reutiliza as roles de bootstrap ou recuperação MFA, não usa access keys e
limita Cognito a `AdminGetUser` e `AdminUpdateUserAttributes` no User Pool
correto. DynamoDB é separado por tabela e pelas ações mínimas de leitura,
idempotência e append de auditoria.

O workflow recebe somente `operation_id`; a autoria é derivada de
`github.actor` e `github.actor_id`. E-mail, `userId`, `cognitoSub`, nome, senha,
token e MFA não são inputs. O IAM não permite restringir
`AdminUpdateUserAttributes` somente ao atributo `email_verified`. Essa limitação
é compensada pela role e Environment dedicados, workflow sem dados pessoais,
service restrito, reconciliação e read-back obrigatórios, idempotência e
auditoria.

A ADR-025 está aprovada na baseline v2.8. A CLI, o workflow e o Terraform da
role/policy estão implementados no repositório, mas a role/policy ainda não foi
provisionada em `dev`; o Environment e suas variables ainda não foram criados.
A correção histórica também não foi autorizada nem executada. Até essas etapas,
`verify-first-admin-email` não está disponível como capacidade operacional na
AWS.

## 8. Ativação após o primeiro login

A ADR-027 aprova `POST /users/me/activation` com JWT access token e
`Idempotency-Key`. A rota permite somente autoativação: o `sub` vem do contexto
validado e nenhum identificador ou estado MFA é aceito do frontend.

Antes de escrever, a `users-api` consulta `AdminGetUser` para confirmar
identidade habilitada, `CONFIRMED`, `sub` reconciliado e `email_verified=true`.
Também consulta `AdminGetUserAuthFactors` e exige
`ConfiguredUserAuthFactors` contendo `SOFTWARE_TOKEN`. Não exige
`PreferredMfaSetting`; `UserMFASettingList` ausente ou vazio não é evidência de
TOTP ausente.

As permissões Cognito da ativação são somente
`cognito-idp:AdminGetUser` e `cognito-idp:AdminGetUserAuthFactors`, restritas ao
user pool aplicável. A operação não modifica Cognito. Não há atomicidade
distribuída entre essas leituras e DynamoDB; a transação revalida o estado de
USER e AUTHORIZATION com conditions no momento da escrita.

### Resolução do próprio perfil

A ADR-029 aprova `GET /users/me` como leitura autenticada e estritamente
self-service. O `sub` vem exclusivamente do access token validado, resolve
`COGNITO#<sub> / AUTHORIZATION` e, a partir do `userId` autoritativo, resolve
`USER#<userId> / PROFILE`. Os itens devem estar reconciliados em `userId`,
`cognitoSub`, `role`, `status` e `authVersion`.

`ADMIN` e `OPERATOR` em `INVITED` ou `ACTIVE` podem consultar o próprio perfil.
As únicas exceções para `INVITED` são `GET /users/me` e
`POST /users/me/activation`; todas as operações de negócio continuam exigindo
`ACTIVE`. Usuários `INACTIVE`, projeções ausentes ou estados inconsistentes
falham de forma fechada com `403`, sem revelar existência ou vínculo.

Todos os campos públicos vêm do DynamoDB. Essa leitura não consulta Cognito,
não expõe MFA, senha, tokens ou atributos internos e não exige novo índice ou
permissão IAM.

### Criação de aluno

A ADR-030 aprova `POST /students` como operação de negócio para `ADMIN` e
`OPERATOR` exclusivamente `ACTIVE`. O Cognito `sub` vem somente do JWT validado
e resolve `COGNITO#<sub> / AUTHORIZATION` com leitura consistente. `INVITED`,
`INACTIVE`, vínculo inconsistente ou role diferente falham com `403`. Não há
consulta nem escrita Cognito.

O request exige JSON estrito, `Idempotency-Key` UUID canônico e validação de
nome, matrícula, e-mail, telefone E.164 e data de nascimento. O fingerprint
idempotente usa somente o payload normalizado e não persiste PII completa.

A Lambda recebe menor privilégio para a transação nas tabelas `students` e
`audit-events`; `PutItem` fica condicionado a
`dynamodb:EnclosingOperation = TransactWriteItems`. Na tabela `idempotency`,
recebe apenas as ações exigidas pela ADR-012. Não recebe permissão Cognito.

Aluno, reservas de unicidade e auditoria de sucesso são gravados atomicamente.
O evento `STUDENT_CREATED` registra somente status e versão iniciais; não
registra e-mail, telefone ou corpo integral. Erros não revelam chaves físicas,
cancellation reasons, stack traces ou dados pessoais desnecessários.

Reset de MFA é administrativo e auditado.  
O único Administrador terá procedimento excepcional controlado de recuperação.

## 9. Proteção de dados

Não registrar:

- senha;
- token;
- credencial;
- `Authorization`;
- corpo completo;
- e-mail completo;
- telefone;
- data de nascimento.

Tags AWS não podem conter PII ou segredos.

Erros operacionais podem registrar somente estágio, serviço/operação AWS, classe da exceção, AWS error code, AWS request ID e `operationId`. Mensagens brutas de serviços, payloads e cancellation reason items são proibidos.


## 10. Recuperação excepcional

Quando o único Administrador perde o TOTP e não há recuperação normal possível,
a ADR-019 define workflow manual protegido, OIDC, `operationId`, invalidacão da identidade
Cognito anterior, criação de nova identidade, atualização de `COGNITO#<sub>`,
incremento de `authVersion`, auditoria e novo `MFA_SETUP`.

O procedimento não reduz a política global de MFA.

Essa recuperação é exclusiva para `ADMIN` `ACTIVE` sem acesso ao TOTP. Ela não se confunde com `resume-first-admin-invitation`, que se aplica somente ao primeiro Admin ainda `INVITED`.
