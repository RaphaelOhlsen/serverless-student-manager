# Pendências após a arquitetura

**Versão:** 2.9
**Data:** 2026-09-04
**Status:** Engenharia em andamento

As ADR-001 a ADR-030 estão aprovadas. Não há ADR proposta pendente nesta
baseline.

## Detalhamento operacional pendente

A taxonomia completa dos eventos operacionais e de auditoria para falhas, compensações, falhas de compensação, reconciliação e alertas permanece como ponto a detalhar durante a implementação e no runbook correspondente.

Isso inclui a taxonomia de tentativas negadas de ativação. A ADR-027 aprova
somente o evento transacional de sucesso `USER_ACTIVATED`.

A ADR-030 resolveu, somente para a criação bem-sucedida de aluno, o evento
transacional `STUDENT_CREATED / SUCCESS`, seu `changes` mínimo e os conflitos
HTTP correspondentes. A taxonomia ampla de tentativas negadas, falhas,
compensações, reconciliação e alertas continua pendente.

## Próximas atividades de engenharia

1. implementar `POST /students` conforme a ADR-030;
2. aplicar rota e IAM após revisão e autorização explícita;
3. publicar e validar a criação em `dev`;
4. integrar o formulário de criação no frontend;
5. ampliar observabilidade e testes integrados/end-to-end;
6. realizar hardening e preparar o ambiente `prod`.

## Itens que podem gerar novas ADRs

- decisões relevantes não previstas durante a implementação;
- mudança de serviço AWS;
- mudança do modelo de dados;
- mudança de fronteira de segurança;
- mudança relevante no processo de deploy;
- novas exigências de produção.
