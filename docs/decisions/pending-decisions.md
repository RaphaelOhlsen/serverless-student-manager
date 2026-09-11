# Pendências após a arquitetura

**Versão:** 2.9
**Data:** 2026-09-04
**Status:** Engenharia em andamento

As ADR-001 a ADR-032 estão aprovadas. O milestone Update Student foi implementado,
validado e encerrado; não há decisão pendente específica desse milestone.

A [ADR-033](adr/adr-033-student-lifecycle.md) registra o contrato aprovado para
implementação de Deactivate/Reactivate Student e permanece Proposed até conclusão
e validação do milestone. Delete Student permanece deferido e fora desse contrato.

## Detalhamento operacional pendente

A taxonomia completa dos eventos operacionais e de auditoria para falhas, compensações, falhas de compensação, reconciliação e alertas permanece como ponto a detalhar durante a implementação e no runbook correspondente.

Isso inclui a taxonomia de tentativas negadas de ativação. A ADR-027 aprova
somente o evento transacional de sucesso `USER_ACTIVATED`.

A ADR-030 resolveu, somente para a criação bem-sucedida de aluno, o evento
transacional `STUDENT_CREATED / SUCCESS`, seu `changes` mínimo e os conflitos
HTTP correspondentes. A taxonomia ampla de tentativas negadas, falhas,
compensações, reconciliação e alertas continua pendente.

## Próximas atividades de engenharia

1. implementar backend de desativação/reativação conforme a ADR-033;
2. revisar e publicar as duas rotas após autorização explícita;
3. validar lifecycle no ambiente `dev` com fixtures descartáveis;
4. integrar filtro de status e ações de lifecycle no frontend;
5. promover a ADR-033 somente após implementação e validação;
6. manter Delete Student deferido para milestone próprio.

## Itens que podem gerar novas ADRs

- decisões relevantes não previstas durante a implementação;
- mudança de serviço AWS;
- mudança do modelo de dados;
- mudança de fronteira de segurança;
- mudança relevante no processo de deploy;
- novas exigências de produção.
