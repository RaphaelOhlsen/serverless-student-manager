# Arquitetura de segurança

**Versão:** 2.8
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

Reset de MFA é administrativo e auditado.  
O único Administrador terá procedimento excepcional controlado de recuperação.

## 8. Proteção de dados

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


## 9. Recuperação excepcional

Quando o único Administrador perde o TOTP e não há recuperação normal possível,
a ADR-019 define workflow manual protegido, OIDC, `operationId`, invalidacão da identidade
Cognito anterior, criação de nova identidade, atualização de `COGNITO#<sub>`,
incremento de `authVersion`, auditoria e novo `MFA_SETUP`.

O procedimento não reduz a política global de MFA.

Essa recuperação é exclusiva para `ADMIN` `ACTIVE` sem acesso ao TOTP. Ela não se confunde com `resume-first-admin-invitation`, que se aplica somente ao primeiro Admin ainda `INVITED`.
