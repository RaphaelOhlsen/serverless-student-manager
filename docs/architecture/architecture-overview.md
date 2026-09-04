# Visão geral da arquitetura

**Versão:** 2.8
**Status:** Approved

## Componentes

| Componente | Responsabilidade |
|---|---|
| React SPA | Interface web |
| S3 privado | Armazenar build do frontend |
| CloudFront | Distribuição e ponto de entrada do frontend |
| Cognito User Pool | Identidade, senha, MFA e tokens |
| API Gateway HTTP API | Entrada HTTP e JWT Authorizer |
| `students-api` | Casos de uso de alunos |
| `users-api` | Usuários administrativos e integração Cognito |
| `audit-api` | Consulta da auditoria |
| DynamoDB `students` | Alunos e reservas de unicidade |
| DynamoDB `users` | Usuários, projeção auth e controle de Admin ativo |
| DynamoDB `audit-events` | Auditoria append-only |
| DynamoDB `idempotency` | Proteção contra writes duplicados |
| CloudWatch | Logs, métricas, dashboards e alarmes |
| SNS | Notificações operacionais |
| S3 state | Estado remoto Terraform |
| GitHub Actions | CI/CD por OIDC |

## Fluxo principal

```text
1. Usuário acessa o frontend pelo CloudFront.
2. Frontend autentica no Cognito.
3. Usuário completa MFA TOTP.
4. Frontend envia access token para a HTTP API.
5. JWT Authorizer valida o JWT.
6. Lambda valida `token_use=access`.
7. Lambda consulta `COGNITO#<sub>` em `users`.
8. Para self-profile, Lambda reconcilia AUTHORIZATION e PROFILE; para operações
   de negócio, aplica role/status atuais e exige `ACTIVE`.
9. Escritas usam idempotência.
10. DynamoDB persiste negócio e auditoria quando possível na mesma transação.
11. Logs e métricas vão para CloudWatch.
```

## Fronteiras

- Cognito autentica, mas não é fonte de verdade de role/status.
- API Gateway valida JWT; autorização funcional ocorre na Lambda.
- Frontend não acessa DynamoDB.
- Auditoria e logs operacionais são mecanismos diferentes.
- Terraform provisiona recursos permanentes.
- GitHub Actions executa builds e deploys; operações privilegiadas usam workflows manuais com roles IAM operacionais separadas.


## Refinamentos operacionais aprovados

- ADR-017: identidade Cognito criada com convite suprimido, persistência DynamoDB e envio posterior do convite.
- ADR-018: operações não HTTP usam `operationId`.
- ADR-019: recuperação break-glass do único Administrador substitui a identidade Cognito preservando `userId`.
- ADR-020: rollback de aplicação, infraestrutura e dados é tratado por camadas.
- ADR-021: auditoria usa modelagem física com GSIs específicos e bucket mensal para consultas por período.
- ADR-022: acesso operacional usa GitHub Actions OIDC com roles separadas por capacidade e ambiente, independentes das roles de deploy.
- ADR-024: o bootstrap inicial usa protocolo determinístico, marker singleton permanente e transação de cinco itens; `resume-first-admin-invitation` retoma somente o onboarding do mesmo Admin `INVITED` reconciliado.
- ADR-025: futuras criações do primeiro Admin definem `email_verified=true` com `ForceAliasCreation=false`; a identidade histórica é corrigida somente pela operação separada `verify-first-admin-email`, preservando `userId`, `Username`, `sub`, senha temporária e MFA.
- ADR-029: `GET /users/me` resolve o próprio perfil por AUTHORIZATION + PROFILE; somente essa leitura e a ativação aceitam `INVITED`, enquanto operações de negócio exigem `ACTIVE`.
