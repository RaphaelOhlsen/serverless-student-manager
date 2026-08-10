# ADR-014 — MFA e segurança adicional do Cognito

**Status:** Approved

## Decisão

MFA TOTP será obrigatório para todos os usuários administrativos (`ADMIN` e `OPERATOR`).

## Configuração

- TOTP: habilitado e obrigatório;
- SMS MFA: desabilitado;
- e-mail MFA: desabilitado;
- dispositivos lembrados: desabilitados;
- recuperação de senha: e-mail verificado.

## Tokens

| Token | Validade |
|---|---:|
| Access token | 15 minutos |
| ID token | 15 minutos |
| Refresh token | 8 horas |

Refresh token rotation será habilitada.

## Primeiro acesso

```text
senha temporária
  → NEW_PASSWORD_REQUIRED
  → senha definitiva
  → MFA_SETUP
  → associação TOTP
```

## Recuperação de MFA

Reset administrativo, auditado e com encerramento de sessões.  
Haverá procedimento excepcional para recuperar o único Administrador.


## Refinamento posterior

A recuperação excepcional do único Administrador sem acesso ao TOTP foi formalizada na **ADR-019**.

O procedimento aprovado não reduz temporariamente a política global de MFA. Em vez disso,
substitui de forma controlada a identidade Cognito, preservando o mesmo `USER#<userId>`,
atualizando a projeção `COGNITO#<sub>`, incrementando `authVersion`, invalidando a identidade
anterior e exigindo novo `NEW_PASSWORD_REQUIRED` + `MFA_SETUP`.
