# Pendências após a arquitetura

**Versão:** 2.8
**Data:** 2026-08-28
**Status:** Engenharia em andamento

As ADR-001 a ADR-025 estão aprovadas. Não há ADR proposta pendente nesta baseline.

## Detalhamento operacional pendente

A taxonomia completa dos eventos operacionais e de auditoria para falhas, compensações, falhas de compensação, reconciliação e alertas permanece como ponto a detalhar durante a implementação e no runbook correspondente.

## Próximas atividades de engenharia

1. implementar o bootstrap seguro do primeiro Administrador;
2. evoluir os endpoints restantes da Students API;
3. implementar o domínio de usuários;
4. implementar os fluxos de auditoria da aplicação;
5. desenvolver o frontend React;
6. ampliar observabilidade e testes integrados/end-to-end;
7. realizar hardening e preparar o ambiente `prod`.

## Itens que podem gerar novas ADRs

- decisões relevantes não previstas durante a implementação;
- mudança de serviço AWS;
- mudança do modelo de dados;
- mudança de fronteira de segurança;
- mudança relevante no processo de deploy;
- novas exigências de produção.
