# Pendências após a arquitetura

**Versão:** 2.9
**Data:** 2026-09-04
**Status:** Engenharia em andamento

As ADR-001 a ADR-034 estão aprovadas. Os milestones Update Student e Student
Lifecycle foram implementados, publicados, validados e encerrados; não há decisão
pendente específica desses milestones. A ADR-034 retirou a exclusão física de
Student do escopo da v1; Deactivate Student é a remoção operacional canônica.

## Detalhamento operacional pendente

A taxonomia completa dos eventos operacionais e de auditoria para falhas, compensações, falhas de compensação, reconciliação e alertas permanece como ponto a detalhar durante a implementação e no runbook correspondente.

Isso inclui a taxonomia de tentativas negadas de ativação. A ADR-027 aprova
somente o evento transacional de sucesso `USER_ACTIVATED`.

A ADR-030 resolveu, somente para a criação bem-sucedida de aluno, o evento
transacional `STUDENT_CREATED / SUCCESS`, seu `changes` mínimo e os conflitos
HTTP correspondentes. A taxonomia ampla de tentativas negadas, falhas,
compensações, reconciliação e alertas continua pendente.

## Próximas atividades de engenharia

1. avançar para o bloco funcional Users / Admin CRUD;
2. tratar exclusão física de Student apenas como possibilidade futura fora da v1.

Caso essa capacidade futura seja reaberta, ela exige revisão explícita do SRS e
nova decisão sobre retenção ou anonimização, reservas de e-mail e matrícula,
auditoria e recuperação. Esses pontos não são pendências de implementação da v1.

## Itens que podem gerar novas ADRs

- decisões relevantes não previstas durante a implementação;
- mudança de serviço AWS;
- mudança do modelo de dados;
- mudança de fronteira de segurança;
- mudança relevante no processo de deploy;
- novas exigências de produção.
