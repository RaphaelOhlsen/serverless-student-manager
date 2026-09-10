# ADR-031 — Agentic Development Harness v1

**Status:** Approved
**Data:** 2026-09-10

## Contexto

Tarefas assistidas por agentes precisam preservar escopo, evidências e limites de
execução entre sessões e fornecedores. O projeto já possui governança documental,
CI e controles de acesso; duplicar regras ou acrescentar infraestrutura aumentaria
custo e risco sem necessidade demonstrada para a primeira versão.

## Decisão

Adotar um Harness documental, human-in-the-loop e vendor-neutral para Codex/Claude.
A única fonte normativa é o [protocolo operacional do Harness v1](../../operations/agentic-development-harness-v1.md).
Adaptadores mínimos apontam/importam essa fonte, sem reproduzir suas regras.
O protocolo define fluxo, gates independentes, evidências e checkpoint local.
Este ADR registra a justificativa; não é uma segunda especificação normativa.

O desenho foi revisado e aprovado, e a implementação documental foi concluída.
O adaptador Codex e a retomada em nova sessão foram validados operacionalmente.
Edições de adaptadores e operações subsequentes exigem seus próprios gates.

## Alternativas rejeitadas para v1

- Regras completas por fornecedor: geram divergência e manutenção duplicada.
- Histórico de chat como única memória: dificulta retomada verificável.
- Orquestrador, serviço de memória ou framework próprio: ampliam dependências e custo.
- Runner com apply/deploy/merge autônomos: amplia o alcance de erros e exigiria
  controles técnicos e validação adicionais ainda não justificados.

## Consequências

- Portabilidade, baixo custo e revisão humana explícita, reutilizando ferramentas existentes.
- Checkpoint compacto e evidências rastreáveis reduzem repetição de trabalho.
- Nenhuma nova dependência, infraestrutura dedicada ou alteração da arquitetura da aplicação.
- A execução depende da disciplina humana e dos controles técnicos existentes;
  instruções documentais não bloqueiam comandos por si mesmas.
- Automação futura exigirá nova avaliação e decisão, sem ampliação implícita do v1.
