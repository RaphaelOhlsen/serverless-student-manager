# Versão documental canônica

**Projeto:** Serverless Student Manager  
**Versão:** 3.2 — Frontend Hosting Infrastructure Declared
**Data:** 2026-10-06
**Status:** Canônica — hosting frontend declarado em Terraform; release ainda não implementada

## Escopo desta versão

Esta versão consolida:

- SRS v1.2 com MFA e rastreabilidade atualizados;
- ADR-001 a ADR-030 aprovadas;
- modelos físicos de dados;
- autenticação, autorização e MFA;
- bootstrap do primeiro Administrador;
- consistência e compensação Cognito ↔ DynamoDB;
- idempotência HTTP e não HTTP;
- recuperação excepcional do único Administrador sem TOTP;
- retenção da auditoria;
- observabilidade;
- testes;
- CI/CD com OIDC;
- rollback em camadas;
- Terraform remote state;
- organização final dos módulos Terraform;
- estratégia de tags;
- runbooks operacionais;
- guia canônico de leitura;
- manifesto com SHA-256.
- contrato público real das 18 operações HTTP em OpenAPI 3.1;
- lint local e CI dedicado com Redocly, sem credenciais AWS ou deploy.
- hosting frontend de `dev` declarado com S3 privado, CloudFront, OAC, security
  headers gerenciados, fallback controlado de SPA e cache por classe de objeto;
- IAM mínimo para publicação e rollback futuro do frontend, sem permissão de
  exclusão de objetos.

## Mudanças principais em relação à v3.1

1. O módulo `frontend_hosting` declara S3 privado e versionado, CloudFront com
   OAC, HTTPS, security headers e fallback SPA sem mascarar assets ausentes.
2. O root `dev` expõe os outputs de release e limita a role OIDC existente ao
   bucket e à distribuição exatos, sem `s3:DeleteObject`.
3. O Terraform CI passa a validar e testar explicitamente o novo módulo.
4. Rollback automático em `dev` após falha de smoke está decidido, mas o
   workflow de release e o primeiro deploy permanecem para fases posteriores.
5. CSP específica, domínio próprio e hosting de produção permanecem adiados.
6. O marco funcional do frontend permanece encerrado e não foi reaberto.

## Estado de implementação desta baseline

O frontend funcional permanece 100% concluído, o contrato público da API está
versionado e a infraestrutura de hosting em `dev` está declarada, mas ainda não
foi aplicada. O workflow de release também ainda não foi implementado. Isso não
declara o projeto inteiro como 100% concluído; a engenharia do projeto e os itens
adiados continuam.

## Regra de precedência

Esta versão substitui documentalmente a v3.1 como fonte de verdade para a engenharia.
