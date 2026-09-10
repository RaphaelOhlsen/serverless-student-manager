# Agentic Development Harness v1

**Natureza:** protocolo normativo de trabalho, human-in-the-loop e vendor-neutral.
**Registro arquitetural:** [ADR-031](../decisions/adr/adr-031-agentic-development-harness.md) — Approved.

## Objetivo e escopo

Conduzir tarefas de engenharia com escopo, autorizações e evidências explícitos,
permitindo retomada entre Codex e Claude sem depender do histórico completo.
Este documento é a única fonte normativa do Harness. Adaptadores de agente devem
somente apontar/importar esta fonte, sem duplicar regras. O Harness não substitui
os requisitos e decisões aprovados do projeto nem controles técnicos de acesso.
A aprovação da ADR não concede autorização de execução.

## Modo econômico

- Trabalhar em uma missão delimitada e com um agente por padrão.
- Ler somente documentos e arquivos pertinentes; consultar ferramentas quando
  houver necessidade concreta, agrupando leituras independentes.
- Reutilizar evidências válidas; repetir verificações somente diante de mudança,
  falha ou incerteza relevante. Nunca declarar como executado um teste não feito.
- Executar verificações proporcionais ao diff, preservando checks obrigatórios.
- Não reabrir tarefas encerradas nem ampliar escopo para resolver problemas adjacentes.
- Ao encontrar bloqueio, registrar o ponto exato e a menor informação necessária.

## Fluxo

1. **Preflight:** conferir branch, HEAD, worktree e referência remota disponível;
   indicar se houve consulta remota. Ler checkpoint e fontes aplicáveis; verificar
   se evidências e autorizações ainda correspondem ao estado atual.
2. **Proposta:** apresentar objetivo, exclusões, arquivos, critérios de aceite,
   verificações, riscos, efeitos colaterais e gates necessários; obter aprovação.
3. **Execução:** agir somente no escopo autorizado. Parar antes de operação sem
   autorização válida ou diante de alteração que invalide a autorização associada.
4. **Revisão:** comparar diff/artefatos com a proposta; registrar evidências e
   resultados, inclusive limitações. Nenhum gate se abre pela revisão do agente.
5. **Publicação/Operação:** verificar separadamente cada autorização necessária,
   seu alvo e artefato imediatamente antes de agir; conferir o resultado.
6. **Checkpoint:** quando autorizado, registrar estado mínimo para retomada,
   pendências e próxima ação. Não converter checkpoint em permissão de execução.

## Gates e autorizações

Mutações são **deny-by-default**. Os gates são independentes e não transitivos:
conceder um não concede os demais. `READY=yes` significa prontidão técnica;
**READY != AUTHORIZED**. Apenas autorização humana explícita abre gate de mutação.

| Gate | Limite |
|---|---|
| READ_ONLY | Inspeções sem mutação, dentro do objetivo e das permissões disponíveis |
| CODE_CHANGE_ALLOWED | Edição/criação local dos arquivos aprovados; branch e outras mudanças locais devem estar explicitamente no escopo |
| COMMIT_ALLOWED | Commit do diff revisado e delimitado |
| PUSH_PR_ALLOWED | Push e/ou criação/atualização de PR expressamente autorizados |
| CLOUD_MUTATION_ALLOWED | Operação cloud ou apply específico, no ambiente/alvo e artefato aprovados |
| MERGE_ALLOWED | Merge do PR/SHA revisado, com método e efeitos conhecidos declarados |

Cada autorização deve registrar: gate, operação, alvo, escopo, artefato relevante
(SHA, diff ou plano/hash quando aplicável), efeitos colaterais conhecidos e
referência à confirmação humana. Não presumir permissões a partir do nome de uma
ferramenta. Nenhum gate autoriza exclusões ou limpeza fora do escopo descrito.

Mudança de SHA, diff, plano, alvo ou escopo invalida a autorização **associada**;
reapresentar o estado concreto para nova aprovação. Um gate de edição autoriza a
produção do diff proposto, mas não sua publicação. O resultado de uma operação
não concede autorização para a próxima. Evidências podem continuar válidas sem
que a autorização continue válida.

Operações sensíveis retomadas em nova sessão exigem nova confirmação humana,
especialmente cloud mutation, apply e merge. Autorizações antigas no checkpoint
são histórico, não gates abertos. Na mesma sessão, não pedir novamente autorização
que permaneça válida para a operação e artefato exatos aprovados.

MERGE_ALLOWED autoriza somente a operação de merge aprovada. Efeitos automáticos
conhecidos de workflows existentes, inclusive deploy, devem ser identificados antes
da autorização, apresentados como consequências do merge e explicitamente aceitos
junto com sua autorização.

MERGE_ALLOWED não autoriza o agente a executar posteriormente ou separadamente
terraform apply, deploy manual, comandos de mutação AWS, alterações cloud ou qualquer
outra operação coberta por CLOUD_MUTATION_ALLOWED. Toda mutação cloud executada
diretamente pelo agente exige CLOUD_MUTATION_ALLOWED próprio, explícito e escopado,
mesmo depois de um merge autorizado. CLOUD_MUTATION_ALLOWED não implica MERGE_ALLOWED.
Os gates permanecem independentes e não transitivos; READY indica somente prontidão,
nunca autorização. O Harness não altera nem dispara autonomamente pipelines existentes.

## Evidências e resultados

- **PASS:** critério atendido com evidência suficiente e aplicável.
- **FAIL:** execução ou evidência demonstra descumprimento do critério.
- **PENDING:** falta execução, acesso, informação ou evidência; não inferir falha.
- Registrar comando/consulta ou origem manual, resultado observado, horário quando
  relevante, SHA/artefato/alvo e limites da observação. Não inferir HTTP, CI ou
  persistência a partir de outro indicador. Relato humano deve ser identificado.
- Não generalizar consulta por chave para ausência global de duplicações; informar
  consistência eventual e restrições de acesso quando afetarem a conclusão.
- Gate técnico agregado só recebe PASS quando todos os critérios necessários
  estiverem comprovados; havendo falha, FAIL; sem falha, mas com lacunas, PENDING.

## Ferramentas e dados

AWS MCP, AWS Serverless MCP e Terraform MCP são read-only por padrão. Escritas,
apply, deploy e chamadas com efeitos persistentes exigem autorização explícita
para a operação concreta, independentemente de serem feitas por MCP, CLI ou UI.
Permissão da ferramenta/sandbox não substitui aprovação do escopo, nem o contrário.

Não registrar tokens, senhas, TOTP, credenciais ou PII em documentos, checkpoints,
logs ou relatórios. Usar evidência sanitizada e dados sintéticos quando cabível.
Não solicitar cópia de tokens para contornar falta de acesso à sessão autenticada.

## Template de missão/tarefa

```text
OBJETIVO / FORA_DO_ESCOPO:
BASE: branch / SHA / estado Git
FONTES_APLICÁVEIS:
ARQUIVOS / ALVOS:
CRITÉRIOS_DE_ACEITE / VERIFICAÇÕES:
RISCOS / EFEITOS_COLATERAIS:
AUTORIZAÇÃO: gate / operação / alvo / escopo / SHA-diff-plan / efeitos / confirmação
EVIDÊNCIAS: origem / resultado / artefato-alvo / limitações
RESULTADO: PASS | FAIL | PENDING
PRÓXIMO_GATE / READY: yes | no (não concede autorização)
```

## Template de checkpoint

`prompt_inicio_dia.txt` permanece local e untracked, fora do Git. É um resumo de
retomada, não fonte normativa. Atualizá-lo somente quando autorizado, sem histórico
completo, secrets ou PII. Preferir referências às evidências em vez de copiá-las.

```text
GIT: branch / HEAD / referência remota / worktree
MISSÃO / ESCOPO:
CONCLUÍDO: critérios e evidências essenciais
PENDENTE: lacuna ou bloqueio exato (PENDING quando faltar evidência)
AUTORIZAÇÕES_ANTERIORES: escopo e referência; revalidar, não assumir gates abertos
PRÓXIMO_PASSO / GATE_NECESSÁRIO:
RESTRIÇÕES: operações não autorizadas; confirmações exigidas na retomada
```

## Fora do v1

Orchestrator multi-agent; vector DB/memory service; framework Python complexo;
runner autônomo; deploy/apply automático pelo Harness; merge autônomo;
infraestrutura AWS dedicada; novas dependências ou armazenamento de credenciais.
A fiscalização técnica continua nos controles existentes de sandbox, IAM e CI/CD;
este protocolo documental não é um mecanismo de enforcement técnico.
