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

   A invocação sem parâmetros permanece compatível com o fluxo legado. Para
   vincular o preflight ao checkpoint aprovado, use, por exemplo:

   ```bash
   ./scripts/agentic-preflight.sh \
     --expected-branch feature/exemplo \
     --expected-head 0123456789abcdef0123456789abcdef01234567 \
     --base fedcba9876543210fedcba9876543210fedcba98 \
     --strict-untracked \
     --format json
   ```

   Para uma inspeção explicitamente read-only em `main`, use:

   ```bash
   ./scripts/agentic-preflight.sh --read-only
   ```

O preflight não acessa a rede nem modifica arquivos. Ele confirma o repositório,
branch, HEAD, `origin/main`, divergência e alterações versionadas, além de listar
todos os arquivos não rastreados. `--expected-branch`, `--expected-head` e
`--base` validam o checkpoint recebido sem fazer `fetch`; `--strict-untracked`
rejeita arquivos não rastreados que não sejam checkpoints. Os arquivos
`prompt_inicio_dia.txt` e `prompt_inicio_dia copy.txt` são identificados como
checkpoints locais e não causam falha no preflight; qualquer outro arquivo não
rastreado continua visível como `other`.

Todos os três validadores aceitam `--format text|json`. A saída é determinística
para o mesmo estado observado, e a saída JSON usa `schemaVersion: 1`. Os códigos
de saída comuns são:

- `0`: validação `PASS` ou ajuda solicitada;
- `1`: estado ou política não satisfeitos (`FAIL`);
- `2`: uso inválido ou impossibilidade de obter evidência confiável.

Um `PASS` valida somente as evidências observadas. Ele nunca concede autorização
para commit, push, merge, deploy, apply ou qualquer outra mutação; a autorização
humana continua separada e explícita.

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

1. Antes do staging, valide todo o escopo autorizado com caminhos exatos, sem
   globs:

   ```bash
   ./scripts/agentic-scope-check.sh \
     --expected-branch feature/exemplo \
     --expected-head 0123456789abcdef0123456789abcdef01234567 \
     --base fedcba9876543210fedcba9876543210fedcba98 \
     --allow-file caminho/autorizado \
     --format text
   ```

   O scope checker consolida mudanças commitadas desde a base, staged,
   unstaged e untracked, rejeita caminhos fora da allowlist e checkpoints
   staged ou tracked, e executa o equivalente a `git diff --check` também para
   arquivos novos. Renames são avaliados fail-closed como remoção e adição, de
   modo que os dois caminhos precisam estar autorizados.
2. Execute formatadores, lint, typecheck e testes aplicáveis ao escopo.
3. Depois de autorização humana específica para staging, adicione somente os
   arquivos permitidos e valide o índice:

   ```bash
   ./scripts/agentic-staging-check.sh \
     --expected-branch feature/exemplo \
     --expected-head 0123456789abcdef0123456789abcdef01234567 \
     --allow-file caminho/autorizado \
     --format text
   ```

   O staging checker rejeita índice vazio, arquivos fora da allowlist,
   checkpoints, whitespace inválido e artefatos ou indícios óbvios de secrets.
   Arquivos binários são reportados como não inspecionáveis. O campo
   `STAGED_DIFF_SHA256` identifica deterministicamente o diff staged completo,
   incluindo conteúdo binário. Use `--expected-diff-sha256 <sha256>` na
   revalidação imediatamente anterior ao commit para vincular a autorização ao
   artefato revisado.
4. Confirme que a saída mantém `AUTHORIZATION_GRANTED=no`. Esse valor é
   intencional mesmo em `PASS`: somente a decisão humana concede autorização.
5. Registre resultados `PASS`, `FAIL`, `PENDING` ou `NOT_APPLICABLE` sem
   transformar ausência de evidência em sucesso e confirme separadamente a
   autorização para commit, push, PR, merge ou cloud.

Os checks de artefatos e secrets são heurísticos e não substituem secret
scanning dedicado nem revisão humana. Eles não revelam o valor encontrado e não
inspecionam o conteúdo de binários. Arquivos ignorados pelo Git também não fazem
parte das evidências de diff desses validadores. Erros de Git ou evidência
inconclusiva falham fechado.

## Validação dos Technical Guards

Execute localmente:

```bash
make harness-test
make harness-shellcheck
make harness-check
```

`harness-test` usa repositórios Git temporários e isolados. `harness-shellcheck`
analisa os quatro scripts shell, seguindo a biblioteca compartilhada, e
`harness-check` combina ambas as validações. O workflow `Harness CI` executa os
mesmos checks em pull requests que alterem arquivos relevantes do Harness, sem
credenciais AWS, OIDC ou mutações externas.

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
