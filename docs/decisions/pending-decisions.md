# Pendências após a arquitetura

**Versão:** 2.8
**Data:** 2026-09-01
**Status:** Engenharia em andamento

As ADR-001 a ADR-027 estão aprovadas. Não há ADR proposta pendente nesta
baseline.

## Detalhamento operacional pendente

A taxonomia completa dos eventos operacionais e de auditoria para falhas, compensações, falhas de compensação, reconciliação e alertas permanece como ponto a detalhar durante a implementação e no runbook correspondente.

Isso inclui a taxonomia de tentativas negadas de ativação. A ADR-027 aprova
somente o evento transacional de sucesso `USER_ACTIVATED`.

## Próximas atividades de engenharia

1. implementar `POST /users/me/activation` conforme a ADR-027;
2. implementar o domínio de usuários;
3. implementar os fluxos de auditoria da aplicação;
4. desenvolver o frontend React;
5. ampliar observabilidade e testes integrados/end-to-end;
6. realizar hardening e preparar o ambiente `prod`.

## Itens que podem gerar novas ADRs

- decisões relevantes não previstas durante a implementação;
- mudança de serviço AWS;
- mudança do modelo de dados;
- mudança de fronteira de segurança;
- mudança relevante no processo de deploy;
- novas exigências de produção.
