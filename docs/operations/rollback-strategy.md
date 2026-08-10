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

Somente dentro de um deploy já aprovado de `prod`:

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
