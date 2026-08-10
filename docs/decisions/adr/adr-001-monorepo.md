# ADR-001 — Organização em monorepo

**Status:** Approved  
**Data:** 2026-07-30

## Contexto

Frontend, backend, infraestrutura, testes e documentação evoluem como partes da mesma solução.

## Alternativas

1. Monorepo.
2. Repositórios separados.

## Decisão

Utilizar um monorepo.

## Consequências positivas

- Visão integrada do projeto.
- Documentação e versionamento centralizados.
- Mudanças coordenadas entre camadas.
- Pipelines no mesmo repositório.

## Consequências negativas

- Crescimento do repositório.
- Necessidade de filtros por caminho nos pipelines.
- Necessidade de limites claros entre componentes.
