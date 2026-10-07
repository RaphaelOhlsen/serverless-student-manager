# Runbook — Rollback e recuperação de deploy

**Status:** Approved
**Data:** 2026-08-10

## Objetivo

Restaurar serviço após regressão de aplicação ou infraestrutura sem confundir rollback de código com recuperação de dados.

## Classificação inicial

Antes de agir, classifique o incidente:

```text
A — frontend
B — Lambda/backend
C — infraestrutura
D — dados DynamoDB
E — identidade Cognito
F — combinação das anteriores
```

## A. Rollback do frontend

### Pré-condições

- identificar último deploy bem-sucedido;
- identificar Version ID anterior do `index.html`;
- confirmar que assets referenciados ainda existem.

### Procedimento

1. restaurar/copiar a versão anterior do `index.html` como versão corrente;
2. restaurar também qualquer runtime config mutável relacionada;
3. criar invalidação CloudFront dos entry points;
4. executar smoke test;
5. registrar resultado.

### Não fazer

- não excluir versões S3 durante o incidente;
- não executar `sync --delete` antes de confirmar a recuperação;
- não alterar infraestrutura CloudFront para um simples rollback de conteúdo.

## B. Rollback de Lambda

### Pré-condições

- alias `live` existente;
- versão anterior conhecida como boa;
- motivo da regressão identificado ou smoke falhou.

### Procedimento

```text
alias live:
newVersion → previousVersion
```

1. atualizar alias para a versão anterior;
2. remover qualquer routing weight temporário;
3. executar smoke test;
4. verificar métricas e erros;
5. registrar release revertida.

Nenhum rebuild é necessário.

## C. Rollback de infraestrutura

Não usar `terraform state push` como mecanismo normal de rollback.

1. interromper novos deploys;
2. inspecionar estado real e último commit bom;
3. produzir alteração Terraform corretiva;
4. executar `terraform plan`;
5. revisar impacto;
6. obter aprovação;
7. aplicar;
8. executar smoke/integration test.

State recovery é reservado para perda/corrupção de state.

## D. Recuperação DynamoDB

1. identificar tabela e timestamp seguro;
2. iniciar PITR para uma nova tabela;
3. aguardar restauração;
4. validar chaves, índices e amostra de dados;
5. comparar com tabela ativa;
6. definir reconciliação/cutover;
7. obter aprovação humana;
8. executar somente o plano aprovado.

Nunca sobrescrever automaticamente a tabela ativa.

## E. Cognito

- configuração: corrigir por Terraform;
- identidade de usuário: usar runbook específico aplicável;
- recuperação MFA: usar ADR-019/runbook;
- não apagar/recriar User Pool como rollback genérico.

## Rollback automático por smoke failure

Em `dev`, o workflow de release executa rollback automático quando o smoke
pós-deploy falha e existe uma versão anterior utilizável. Ele captura a versão
corrente de `index.html` antes do upload, publica o novo entry point por último,
invalida somente `/` e `/index.html` e aguarda a conclusão antes do smoke.

Quando há versão anterior, o rollback copia diretamente essa versão S3 para uma
nova versão corrente, preservando seus metadados e sem rebuild. Depois repete a
invalidação e o smoke. A falha inicial permanece como resultado final do
workflow, mesmo se o rollback recuperar o serviço.

No primeiro release, a ausência de `index.html` anterior é normal. Se o smoke
falhar, o workflow registra `ROLLBACK_NOT_AVAILABLE_FIRST_RELEASE`, não apaga
objetos e termina com falha.

### Evidência operacional do primeiro release

O primeiro release real do frontend em `dev` foi executado em 2026-10-07 pelo
workflow oficial, run `37595125892`, commit
`93aa33817088a7a7475d9848669d7b24dcf1ab2d`.

A execução concluiu `SUCCESS`, com `PREVIOUS_INDEX_VERSION = NONE`, uploads,
invalidação e smokes aprovados. Nenhum rollback foi necessário; portanto, o
caminho de rollback real permaneceu não exercitado nessa execução.

A invalidação CloudFront `I2DBEP9CTXHE403LPZT90C2PUE` concluiu usando apenas
`/` e `/index.html`. Não houve upload S3 ou invalidação CloudFront manual,
`DeleteObject`, `sync --delete`, Terraform apply ou alteração em produção.

Em `prod`, o rollback automático continua limitado a um deploy previamente
aprovado:

```text
deploy application
  ↓
smoke
  ├── PASS → concluir
  └── FAIL
       ↓
       Lambda aliases → previous
       frontend entry point → previous S3 version
       ↓
       CloudFront invalidation
       ↓
       smoke novamente
```

Se o segundo smoke falhar:

- marcar deployment como failed;
- bloquear novas promoções;
- alertar operação;
- exigir intervenção humana.

O rollback do frontend restaura a versão S3 anterior do `index.html`, preserva
os assets fingerprinted de releases anteriores, invalida apenas os entry points
necessários e nunca usa `sync --delete`.

## Compatibilidade de dados

Antes de deploy com mudança de modelo:

- confirmar compatibilidade da versão anterior;
- usar expand-contract;
- impedir remoção de atributo/índice necessário enquanto rollback for necessário.

Mudança destrutiva exige runbook próprio.

## Evidências mínimas

Registrar:

```text
environment
deploymentId
commitSha
previousCommitSha
Lambda old/new versions
frontend old/new S3 version IDs
correlationId
reason
startedAt
completedAt
result
```

Sem PII, senha, token ou credencial.
