# Versão documental canônica

**Projeto:** Serverless Student Manager  
**Versão:** 3.3 — Frontend Release Automation Implemented
**Data:** 2026-10-06
**Status:** Canônica — hosting dev implantado; release automatizada ainda não executada

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
  exclusão de objetos;
- infraestrutura de hosting aplicada e convergente em `dev`;
- workflow e helper testável de release, smoke e rollback automático do frontend.

## Mudanças principais em relação à v3.2

1. O hosting S3 privado + CloudFront/OAC foi aplicado em `dev`; o plan
   pós-apply confirmou convergência sem drift.
2. O workflow lê alvos e configurações públicas diretamente dos outputs
   Terraform, compila o SHA exato e publica `index.html` por último.
3. Assets fingerprinted recebem cache imutável; entry point e arquivos públicos
   não fingerprinted usam cache conservador. Nenhum objeto é excluído.
4. Smoke valida root, asset, security headers e `GET /health`.
5. Falha pós-publicação restaura a versão S3 anterior de `index.html` quando ela
   existe, mas mantém o workflow como failed. O primeiro release sem versão
   anterior falha de forma explícita sem rollback destrutivo.
6. O workflow está implementado, mas não foi executado e nenhum conteúdo foi
   publicado. CSP específica, domínio próprio, produção e CI/Playwright amplo
   permanecem adiados.
7. O marco funcional do frontend permanece encerrado e não foi reaberto.

## Estado de implementação desta baseline

O frontend funcional permanece 100% concluído, o contrato público da API está
versionado e o hosting de `dev` está implantado. A automação de release está
implementada e testada localmente, porém seu primeiro deploy permanece pendente
de gate operacional próprio. Isso não declara o projeto inteiro como 100%
concluído; a engenharia do projeto e os itens adiados continuam.

## Regra de precedência

Esta versão substitui documentalmente a v3.2 como fonte de verdade para a engenharia.
