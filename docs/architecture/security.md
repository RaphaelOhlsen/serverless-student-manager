# Arquitetura de segurança

**Versão:** 2.4
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
- nenhuma credencial AWS permanente no GitHub;
- frontend sem acesso direto ao DynamoDB.

## 7. Bootstrap e recuperação

O primeiro Administrador é criado por workflow manual com OIDC e função temporária.

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


## 9. Recuperação excepcional

Quando o único Administrador perde o TOTP e não há recuperação normal possível,
a ADR-019 define workflow manual protegido, OIDC, `operationId`, invalidacão da identidade
Cognito anterior, criação de nova identidade, atualização de `COGNITO#<sub>`,
incremento de `authVersion`, auditoria e novo `MFA_SETUP`.

O procedimento não reduz a política global de MFA.
