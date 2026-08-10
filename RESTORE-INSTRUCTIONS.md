# Restauração da documentação canônica v2.3 — Engineering Ready

Este pacote substitui integralmente a árvore documental v2.2 e versões anteriores.

## Antes da substituição

Faça um commit, branch ou cópia de segurança do repositório atual.

## Estrutura esperada

```text
serverless-student-manager/
├── AGENTS.md
└── docs/
    ├── README.md
    ├── DOCUMENTATION-VERSION.md
    ├── ENGINEERING-READINESS.md
    ├── AUDIT-REPORT.md
    ├── MANIFEST.md
    ├── overview.md
    ├── requirements/
    ├── decisions/
    │   └── adr/
    │       ├── adr-001-...
    │       └── adr-020-...
    ├── architecture/
    ├── operations/
    ├── references.md
    ├── serverless-student-manager-ordem-de-leitura.md
    └── serverless-student-manager-ordem-de-leitura.png
```

## Procedimento recomendado

1. Faça backup da pasta `docs/` atual e do `AGENTS.md`.
2. Remova a pasta `docs/` antiga.
3. Copie a pasta `docs/` deste pacote para a raiz do repositório.
4. Substitua o `AGENTS.md` da raiz pela versão deste pacote.
5. Não misture arquivos da v2.2 ou de versões anteriores.
6. Peça ao Codex uma auditoria somente leitura.
7. Somente após o resultado `APROVADO PARA ENGENHARIA`, autorize a primeira tarefa de scaffold.
