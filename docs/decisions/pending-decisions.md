# Pendências após a arquitetura

**Versão:** 2.3  
**Data:** 2026-08-10  
**Status:** Arquitetura inicial concluída — Engineering Ready

Não existem ADRs arquiteturais pendentes entre ADR-001 e ADR-020.

## Próximas atividades de engenharia

1. Validar esta documentação com o Codex.
2. Criar o esqueleto do monorepo.
3. Configurar ferramentas de qualidade.
4. Implementar `infra/bootstrap`.
5. Criar remote state e OIDC.
6. Implementar os módulos Terraform.
7. Provisionar `dev`.
8. Implementar o bootstrap do primeiro Administrador.
9. Desenvolver backend e frontend.
10. Implementar pipelines e testes integrados.
11. Criar `prod` após validação do MVP.

## Itens que podem gerar novas ADRs

- decisões relevantes não previstas durante a implementação;
- mudança de serviço AWS;
- mudança do modelo de dados;
- mudança de fronteira de segurança;
- mudança relevante no processo de deploy;
- novas exigências de produção.
