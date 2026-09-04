# Decision Register

**Projeto:** Serverless Student Manager  
**Versão:** 2.8
**Data:** 2026-09-04
**Status:** Canônico

## 1. Decisões de produto, restrições e segurança

| ID | Categoria | Decisão | Status |
|---|---|---|---|
| PROD-001 | Produto | MVP para uma única instituição | Approved |
| PROD-002 | Produto | CRUD profissional, não apenas demonstrativo | Approved |
| PROD-003 | Produto | Perfis `ADMIN` e `OPERATOR` | Approved |
| PROD-004 | Produto | Desativação lógica | Approved |
| PROD-005 | Produto | E-mail do aluno obrigatório e único | Approved |
| PROD-006 | Produto | Telefone obrigatório e não único | Approved |
| PROD-007 | Produto | Acesso do aluno fora do MVP | Approved |
| PROD-008 | Futuro | Login futuro do aluno por `studentEmail`, identidade por Cognito `sub` | Deferred |
| CON-001 | Restrição | React + TypeScript | Approved |
| CON-002 | Restrição | Python + Lambda | Approved |
| CON-003 | Restrição | API Gateway HTTP API | Approved |
| CON-004 | Restrição | DynamoDB | Approved |
| CON-005 | Restrição | Cognito | Approved |
| CON-006 | Restrição | Terraform | Approved |
| CON-007 | Restrição | GitHub Actions | Approved |
| SEC-001 | Segurança | Proteção nativa do Cognito contra tentativas repetidas | Approved |
| SEC-002 | Segurança | Sem contador paralelo de tentativas na aplicação | Approved |
| SEC-003 | Segurança | Sem sign-up público de usuários administrativos | Approved |
| SEC-004 | Segurança | Senha: 12+ caracteres, maiúscula, minúscula, número e especial | Approved |
| TECH-001 | Terraform | Seguir HashiCorp Style Guide | Approved |

## 2. ADRs aprovadas

| ID | Decisão | Status |
|---|---|---|
| ADR-001 | Monorepo | Approved |
| ADR-002 | Frontend em S3 privado + CloudFront | Approved |
| ADR-003 | API Gateway HTTP API + JWT Authorizer | Approved |
| ADR-004 | Uma Lambda por domínio | Approved |
| ADR-005 | Uma tabela DynamoDB por domínio | Approved |
| ADR-006 | Cognito autentica; DynamoDB define role/status atuais | Approved |
| ADR-007 | `dev` e `prod` separados na mesma conta AWS | Approved |
| ADR-008 | Remote state Terraform em S3, locking nativo | Approved |
| ADR-009 | GitHub Actions + OIDC + função IAM por ambiente | Approved |
| ADR-010 | CloudWatch como base de observabilidade | Approved |
| ADR-011 | Estratégia de testes em camadas | Approved |
| ADR-012 | Idempotência com `Idempotency-Key` + DynamoDB | Approved |
| ADR-013 | Bootstrap controlado do primeiro Administrador | Approved |
| ADR-014 | MFA TOTP obrigatório | Approved |
| ADR-015 | Retenção configurável da auditoria | Approved |
| ADR-016 | Módulos Terraform por capacidade arquitetural | Approved |
| ADR-017 | Consistência de provisionamento Cognito ↔ DynamoDB | Approved |
| ADR-018 | Idempotência para operações não HTTP com `operationId` | Approved |
| ADR-019 | Recuperação excepcional do único Administrador sem TOTP | Approved |
| ADR-020 | Rollback em camadas e recuperação de deploy | Approved |
| ADR-021 | Modelagem física dos índices de auditoria com bucket mensal | Approved |
| ADR-022 | Acesso operacional controlado via GitHub Actions OIDC | Approved |
| ADR-023 | Modelagem física da tabela users | Approved |
| ADR-024 | Protocolo determinístico e trava singleton do bootstrap do primeiro Admin | Approved |
| ADR-025 | Verificação administrativa do e-mail do primeiro Administrador | Approved |
| ADR-026 | Contrato de listagem e modelagem física de Students | Approved |
| ADR-027 | Ativação do usuário após o primeiro login | Approved |
| ADR-028 | Release de código Lambda via GitHub Actions | Approved |
| ADR-029 | Resolução autenticada do próprio perfil | Approved |

## 3. Modelos de dados aprovados

| Modelo | Status |
|---|---|
| Tabela `students` | Approved |
| Tabela `users` | Approved |
| Tabela `audit-events` | Approved |
| Tabela técnica `idempotency` | Approved |
| Unicidade transacional de matrícula/e-mail | Approved |
| Controle do último Administrador ativo | Approved |
| Paginação por cursor | Approved |

## 4. Evoluções futuras registradas

| Tema | Direção futura | Status |
|---|---|---|
| Observabilidade distribuída | OpenTelemetry / Application Signals | Deferred |
| Visualização | Grafana consultando CloudWatch | Deferred |
| Métricas Prometheus | AMP quando houver necessidade Prometheus-native | Deferred |
| Contas AWS | Separar `dev` e `prod` em contas distintas | Deferred |
| Busca | Busca avançada além de prefixo | Deferred |
| Aplicação | Multi-tenancy | Deferred |
| Usuários | Acesso do aluno | Deferred |

## 5. Situação arquitetural

As ADR-001 a ADR-029 estão aprovadas.

Novas decisões relevantes surgidas durante a engenharia devem ser registradas em ADR-030 ou posterior.

## 6. Regra de manutenção

Uma decisão substituída não deve ser apagada.  
A ADR anterior será marcada como `Superseded` e apontará para a decisão substituta.
