# Uso local do Agentic Development Harness

O `AGENTS.md` da raiz continua sendo a autoridade canônica do projeto. O
[protocolo normativo do Harness v1](agentic-development-harness-v1.md) define
gates, autorizações e evidências. Este guia apenas operacionaliza o início e o
encerramento de tarefas para Codex e Claude Code.

## Início de uma tarefa

1. Leia `AGENTS.md`, o protocolo normativo e as fontes aplicáveis na ordem
   canônica.
2. Confirme escopo, riscos, arquivos e gate autorizado.
3. Atualize referências remotas quando a tarefa autorizar acesso à rede.
4. Crie ou selecione a branch aprovada e execute:

   ```bash
   make agentic-preflight
   ```

   Para uma inspeção explicitamente read-only em `main`, use:

   ```bash
   ./scripts/agentic-preflight.sh --read-only
   ```

O preflight não acessa a rede nem modifica arquivos. Ele confirma o repositório,
branch, HEAD, `origin/main`, divergência e alterações versionadas, além de listar
todos os arquivos não rastreados. `prompt_inicio_dia.txt` e
`prompt_inicio_dia copy.txt` são identificados como checkpoints e não causam
falha; qualquer outro arquivo não rastreado continua visível como `other`.

## Durante a implementação

- Trabalhe somente no escopo e gate aprovados.
- Preserve evidências válidas e execute validações proporcionais aos arquivos
  alterados.
- Pare quando SHA, diff, alvo ou autorização deixarem de corresponder à tarefa.
- Não inclua secrets, tokens, credenciais ou PII em comandos, logs ou relatórios.

Sem autorização humana explícita, agentes não podem executar `terraform apply`
ou operações destrutivas de Terraform, deploy de produção, alteração de recursos
AWS, mutações por AWS MCP, AWS Serverless MCP ou Terraform MCP, force push,
`git reset --hard`, `git clean -fd`, remoção de arquivos locais desconhecidos ou
modificação de secrets. MCPs são read-only por padrão. Implementações não são
feitas diretamente em `main`.

## Antes de commit ou PR

1. Revise todo o diff e confirme que os checkpoints permanecem fora do Git.
2. Execute formatadores, lint, typecheck e testes aplicáveis ao escopo.
3. Execute `git diff --check` e verifique a ausência de credenciais e artefatos.
4. Registre resultados `PASS`, `FAIL`, `PENDING` ou `NOT_APPLICABLE` sem
   transformar ausência de evidência em sucesso.
5. Confirme separadamente a autorização para commit, push, PR, merge ou cloud.

## Relatório final mínimo

```text
BRANCH=<branch>
HEAD=<sha>
ORIGIN_MAIN=<sha>
FILES_CHANGED=<lista ou 0>
TESTS_EXECUTED=<comandos ou none>
TESTS_RESULT=PASS|FAIL|NOT_APPLICABLE
COMMITS_CREATED=<n>
PR_CREATED=yes|no
TERRAFORM_EXECUTED=yes|no
DEPLOY_EXECUTED=yes|no
MCPS_USED=<none ou lista>
BLOCKERS=<none ou descrição>
NEXT_ACTION=<ação e gate necessário>
```

Não há armazenamento próprio de logs: Git, CI e o relatório da tarefa preservam
as evidências necessárias.
