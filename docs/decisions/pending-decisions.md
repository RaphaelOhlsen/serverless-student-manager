# Pendências após a arquitetura

**Versão:** 2.6
**Data:** 2026-08-19
**Status:** Engenharia em andamento

Não existem ADRs arquiteturais pendentes entre ADR-001 e ADR-023.

## Próximas atividades de engenharia

1. concluir o acesso operacional controlado via GitHub Actions OIDC;
2. implementar o bootstrap seguro do primeiro Administrador;
3. evoluir os endpoints restantes da Students API;
4. implementar o domínio de usuários;
5. implementar os fluxos de auditoria da aplicação;
6. desenvolver o frontend React;
7. ampliar observabilidade e testes integrados/end-to-end;
8. realizar hardening e preparar o ambiente `prod`.

## Itens que podem gerar novas ADRs

- decisões relevantes não previstas durante a implementação;
- mudança de serviço AWS;
- mudança do modelo de dados;
- mudança de fronteira de segurança;
- mudança relevante no processo de deploy;
- novas exigências de produção.
