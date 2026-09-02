# ADR-028 — Lambda Application Release via GitHub Actions

**Status:** Approved
**Data:** 2026-09-02

## Contexto

O Terraform cria cada função Lambda, sua configuração e o alias estável `live`, mas ignora
alterações posteriores de `filename` e de `alias.function_version`. Essa separação atribui releases
de aplicação ao GitHub Actions. Atualmente, porém, não existe workflow que publique código para
`students-api` ou `users-api`; o CI apenas valida os pacotes e o workflow OIDC apenas confirma a
identidade AWS.

A correção da `users-api` mergeada no commit
`40e2797d86a9b57d2262a75d9dd88dce32b5bf05` permanece pendente de publicação e não deve ser
implantada por CLI manual ou por `terraform apply`.

## Alternativas avaliadas

1. Remover `ignore_changes` e usar Terraform em todo release de código.
2. Fazer uploads manuais com AWS CLI.
3. Implementar releases de aplicação por GitHub Actions, mantendo Terraform responsável pela
   infraestrutura inicial.

## Decisão proposta

Adotar a alternativa 3. Terraform permanece responsável pela criação e configuração estrutural das
funções, aliases, integrações, roles e policies. GitHub Actions será responsável pelas releases
posteriores do código Lambda. Os `lifecycle.ignore_changes` atuais não serão removidos sem nova
decisão explícita.

O mecanismo será reutilizável para `students-api` e `users-api`, com isolamento por API: uma mudança
em apenas um domínio não publica o outro.

## Trigger e seleção em dev

- releases automáticos ocorrem somente em `push` para `main`, após merge;
- PRs e feature branches nunca publicam código;
- os paths relevantes incluem o diretório da API, sua definição de empacotamento e componentes
  compartilhados que efetivamente integrem o artifact;
- um job inicial determina quais APIs mudaram e alimenta uma matrix somente com os alvos afetados;
- `workflow_dispatch` é permitido para replay/recuperação controlada de um commit já pertencente à
  história de `main`, nunca para conteúdo de feature branch;
- a concorrência usa grupo por ambiente e API, sem cancelamento de release já iniciada, por exemplo
  `lambda-release-dev-users-api`.

O CI de PR permanece separado e não perde nenhuma verificação. O release faz checkout do SHA exato
em `main`, reconstrói o artifact do zero e executa apenas as validações necessárias para comprovar o
pacote e o alvo; não reutiliza arquivos locais ou artifacts de PR.

## Artifact e rastreabilidade

Cada API usa seu processo canônico de build a partir de checkout limpo. O build deve:

- usar Python e dependências fixadas pelo repositório, com resolução reproduzível;
- produzir ZIP com ordem e metadados determinísticos;
- incluir somente código executável e dependências runtime;
- excluir testes, caches, arquivos `.env`, secrets e arquivos locais;
- validar o handler e a presença dos arquivos esperados;
- calcular SHA-256 antes do upload.

O summary do workflow registra somente ambiente, API, nome da função, commit SHA, SHA-256 do
artifact, versão publicada, alias, versão anterior, horários e resultado. Tokens, secrets e PII não
são registrados.

## Autenticação AWS e GitHub Environment

O workflow usa GitHub OIDC e credenciais temporárias, sem access keys permanentes. Em `dev`, será
reutilizada a role `student-manager-github-dev-deploy`, cuja trust policy permanece restrita ao
subject imutável da branch `main`.

`dev` não usará GitHub Environment: o deploy é automático após merge e a trust policy atual baseada
em `ref:refs/heads/main` mantém essa fronteira. Adicionar Environment mudaria o subject OIDC e
introduziria uma barreira de aprovação incompatível com o fluxo automático aprovado pela ADR-009.
Produção continua fora do escopo desta ADR e preserva o GitHub Environment protegido definido nas
ADRs 009 e 020.

## IAM mínimo para release

A policy de deploy de `dev` adicionará apenas:

- `lambda:GetFunctionConfiguration`, para validar o alvo, acompanhar `LastUpdateStatus` e validar a
  versão publicada;
- `lambda:GetAlias`, para capturar a versão anterior e conferir o alias;
- `lambda:UpdateFunctionCode`, para atualizar `$LATEST` com o artifact construído;
- `lambda:PublishVersion`, para criar versão imutável;
- `lambda:UpdateAlias`, para promover `live` e, quando necessário, executar rollback.

Essas ações serão restritas aos ARNs exatos das funções `students-api` e `users-api` de `dev`, com
qualificadores de versão/alias quando a ação admitir esse nível de recurso. Não haverá `Resource: *`,
ações de exclusão, alteração de configuração, escrita em DynamoDB/Cognito nem permissões operacionais.

Os waiters usarão `GetFunctionConfiguration`; não será concedida uma ação apenas por conveniência.
Qualquer permissão adicional descoberta na implementação exige evidência técnica e nova revisão do
menor privilégio.

## Sequência de release

Para cada API selecionada:

```text
checkout do commit exato em main
→ build determinístico
→ hash e validação do artifact
→ autenticação OIDC
→ GetFunctionConfiguration + GetAlias live
→ UpdateFunctionCode em $LATEST
→ aguardar LastUpdateStatus=Successful
→ PublishVersion
→ validar a versão publicada
→ UpdateAlias live para a nova versão numerada
→ confirmar alias
→ smoke test read-only
```

O alias nunca é atualizado antes de a nova versão estar pronta. API Gateway continua invocando
`live`; `$LATEST` não recebe tráfego lógico da aplicação.

## Falhas, atomicidade operacional e rollback

Não existe transação única entre as operações Lambda. A fronteira de tráfego é a atualização do
alias:

- falha antes de `UpdateAlias` preserva `live` na versão anterior;
- falha após `UpdateFunctionCode` e antes da promoção deixa `$LATEST` sem tráfego;
- o workflow registra a versão anterior antes de qualquer alteração;
- nenhuma versão publicada é excluída durante o release;
- falha no smoke após promoção reponta `live` para a versão anterior conhecida como boa e repete o
  smoke, conforme ADR-020;
- rollback não reconstrói artifact, não usa Terraform e não altera dados.

Releases concorrentes da mesma API/ambiente são serializadas pelo concurrency group. APIs distintas
podem avançar independentemente.

## Smoke tests

Após promoção, o workflow executa somente verificações sem efeito de negócio:

- `users-api`: `POST /users/me/activation` sem token deve retornar `401` no JWT Authorizer;
- `students-api`: `GET /students` sem token deve retornar `401` no JWT Authorizer.

O smoke não usa token real, não chega à Lambda autenticada e não muta DynamoDB ou Cognito.

## Primeira release pendente da users-api

Depois que o workflow e sua IAM mínima forem implementados e provisionados, uma execução do próprio
mecanismo canônico publicará a `users-api` correspondente ao commit
`40e2797d86a9b57d2262a75d9dd88dce32b5bf05`. Essa primeira publicação poderá usar
`workflow_dispatch`, informando o SHA e validando server-side que ele pertence à história de `main`.

Não será permitido upload manual, atualização direta pela AWS CLI local nem uso do artifact local
`/tmp/users-api-auth-version-fix.zip`.

## Impacto futuro de implementação

- criar workflow reutilizável de release Lambda e seleção por paths/API;
- criar build determinístico por API e suas validações;
- ampliar declarativamente a policy da role de deploy de `dev` com as ações exatas desta ADR;
- testar seleção de API, concorrência, falhas antes da promoção, promoção, smoke e rollback;
- publicar a correção pendente somente depois de plan/apply IAM revisado e execução autorizada do
  workflow.

## Consequências

### Positivas

- separação clara entre infraestrutura e release de aplicação;
- artifacts rastreáveis até um commit de `main`;
- rollback rápido por alias, sem rebuild;
- Students e Users compartilham o mecanismo sem releases acoplados.

### Negativas

- exige pipeline, policy IAM e testes adicionais;
- atualização de `$LATEST`, publicação e promoção não são atomicamente distribuídas;
- builds realmente reproduzíveis exigem disciplina sobre dependências e metadados do ZIP.

## Relação com decisões anteriores

- ADR-004: mantém uma Lambda por domínio e empacotamento próprio;
- ADR-009: detalha o deploy automático em `dev` com GitHub Actions e OIDC;
- ADR-011: preserva CI de PR e smoke pós-deploy;
- ADR-020: implementa versões imutáveis, alias `live` e rollback em camadas;
- ADR-022: mantém release separado de operações administrativas privilegiadas.
