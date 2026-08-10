# ADR-020 — Estratégia de rollback e recuperação de deploy

**Status:** Approved  
**Data:** 2026-08-10

## Contexto

A documentação aprovada define:

- GitHub Actions como mecanismo de CI/CD;
- deploy automático em `dev`;
- promoção manual e protegida para `prod`;
- Terraform como fonte de verdade da infraestrutura;
- frontend estático em S3 privado + CloudFront;
- backend em AWS Lambda;
- DynamoDB com PITR de 35 dias em `prod`;
- smoke tests após deploy.

Ainda falta definir como recuperar o sistema quando um deploy válido tecnicamente produz regressão,
quando uma alteração de infraestrutura falha parcialmente ou quando dados precisam ser restaurados.

Rollback de aplicação, rollback de infraestrutura e recuperação de dados são problemas diferentes
e não devem usar o mesmo mecanismo.

## Objetivos

- restaurar rapidamente uma versão funcional da aplicação;
- manter releases anteriores imutáveis e identificáveis;
- evitar usar o arquivo de estado do Terraform como mecanismo normal de rollback;
- evitar rollback automático de dados;
- impedir que mudanças incompatíveis de dados eliminem a possibilidade de rollback;
- preservar aprovação humana em operações de produção;
- manter o processo auditável.

## Alternativas consideradas

### Opção A — Redeploy do commit anterior para tudo

O pipeline faria checkout de um commit conhecido como bom, reconstruiria aplicação e Terraform e
tentaria reaplicá-los.

#### Vantagens

- simples de compreender;
- poucos mecanismos adicionais.

#### Desvantagens

- rebuild não é necessariamente o mesmo artefato anteriormente implantado;
- aplicar Terraform antigo pode produzir mudanças destrutivas;
- mistura código, infraestrutura e dados em um único mecanismo;
- recuperação tende a ser lenta.

### Opção B — Rollback em camadas

Cada camada usa o mecanismo nativo adequado:

- Lambda: versões publicadas + alias estável;
- frontend: assets imutáveis + S3 Versioning para arquivos mutáveis;
- CloudFront: invalidação após restauração do entry point;
- infraestrutura: plano Terraform corretivo revisado;
- dados DynamoDB: PITR para nova tabela;
- migrações: estratégia backward-compatible / expand-contract.

#### Vantagens

- rollback rápido do código;
- reduz risco de infraestrutura;
- preserva artefatos efetivamente implantados;
- separa recuperação de aplicação e recuperação de dados;
- usa mecanismos nativos dos serviços.

#### Desvantagens

- exige disciplina de release;
- aumenta o pipeline;
- exige runbook específico por camada.

### Opção C — Blue/green/canary completo

Adicionar mecanismos avançados como CodeDeploy, roteamento ponderado e ambientes paralelos completos.

#### Vantagens

- rollback e redução de blast radius mais sofisticados.

#### Desvantagens

- complexidade e custo operacional desnecessários para o MVP;
- maior quantidade de recursos e políticas;
- aumenta o escopo do projeto antes da primeira versão funcional.

## Decisão proposta

Adotar a **Opção B — rollback em camadas**.

## 1. Backend Lambda

Cada deploy de código deve:

1. atualizar código/configuração compatível da função;
2. publicar uma versão imutável;
3. executar validações aplicáveis;
4. mover o alias estável `live` para a nova versão;
5. registrar qual versão era a anterior.

A API Gateway integra com o alias `live`, e não diretamente com `$LATEST`.

Rollback de código:

```text
live → versão anterior conhecida como boa
```

Nenhum rebuild é necessário para rollback imediato.

### Smoke failure

Em `prod`, a aprovação humana autoriza a execução completa do workflow de deploy.

Se o smoke test executado imediatamente no mesmo workflow falhar, o workflow pode
automaticamente devolver o alias `live` à versão anterior registrada no início da implantação.

Esse rollback automático limita-se à release de aplicação e não autoriza alterações destrutivas de infraestrutura ou dados.

## 2. Frontend

O bucket do frontend terá S3 Versioning habilitado.

A build deve produzir assets com nomes versionados/fingerprinted por conteúdo sempre que a ferramenta escolhida suportar essa prática.

Regras de publicação:

- assets imutáveis de releases anteriores não são excluídos durante a janela de rollback;
- `index.html` é tratado como entry point mutável e versionado pelo S3;
- qualquer arquivo de configuração runtime mutável deve seguir a mesma regra do `index.html`;
- o pipeline captura os Version IDs anteriores antes da publicação.

Rollback:

1. copiar/restaurar a versão S3 anterior do `index.html` e demais entry points mutáveis;
2. manter os assets imutáveis referenciados por essa versão;
3. criar invalidação CloudFront para os entry points necessários;
4. executar smoke test.

O pipeline não deve usar uma sincronização destrutiva que torne indisponíveis assets necessários à release anterior durante a janela de rollback.

## 3. Janela mínima de rollback da aplicação

Proposta inicial:

```text
dev  = manter pelo menos 3 releases bem-sucedidas
prod = manter pelo menos 5 releases bem-sucedidas e 30 dias de assets necessários
```

A política de lifecycle poderá eliminar versões/assets mais antigos depois da janela definida.

## 4. Infraestrutura Terraform

O estado Terraform **não é** o mecanismo normal para desfazer uma alteração real da AWS.

Para regressão de infraestrutura:

1. identificar a última configuração conhecida como boa;
2. preparar uma alteração corretiva no código Terraform;
3. executar `terraform plan`;
4. revisar o plano;
5. obter aprovação humana quando aplicável;
6. aplicar o plano corretivo.

Restaurar uma versão anterior do `terraform.tfstate` é reservado para **recuperação de corrupção ou perda do estado**, não para tentar desfazer recursos reais.

Nenhum `terraform destroy` faz parte de um rollback normal.

## 5. DynamoDB e dados

Rollback de aplicação não executa rollback automático dos dados.

Em `prod`, PITR permanece habilitado com janela de 35 dias.

Quando for necessária recuperação:

```text
PITR
  ↓
restaurar para uma NOVA tabela
  ↓
validar dados
  ↓
definir plano de reconciliação/cutover
  ↓
aprovação humana
```

A restauração não sobrescreve automaticamente a tabela ativa.

## 6. Compatibilidade de mudanças de dados

Releases normais devem preservar compatibilidade suficiente para que a versão anterior da aplicação continue funcionando durante a janela de rollback.

Mudanças incompatíveis devem usar estratégia **expand-contract**, por exemplo:

```text
release N
  → adicionar novo campo/índice sem remover o antigo

release N+1
  → aplicação passa a compreender ambos os formatos

janela de rollback encerrada
  → remover legado em alteração posterior
```

Uma transformação destrutiva ou irreversível de dados exige plano específico de migração e recuperação antes do deploy e não é elegível para rollback automático de aplicação.

## 7. Cognito

Mudanças de configuração do Cognito gerenciadas por Terraform seguem o procedimento corretivo de infraestrutura.

Dados de identidade não são revertidos automaticamente.

Mudanças potencialmente destrutivas sobre User Pool, usuários, aliases ou MFA exigem procedimento específico e aprovação humana.

## 8. API Gateway

A integração com Lambdas deve apontar para aliases estáveis.

Assim, rollback de código Lambda não exige alteração no API Gateway.

Mudanças estruturais de rotas, authorizers ou integrações são tratadas como infraestrutura e seguem Terraform.

## 9. Registro da release

Cada deploy deve registrar no summary do workflow, no mínimo:

```text
environment
commitSha
deploymentId
frontend release/version information
Lambda published versions
Lambda previous versions
Terraform configuration commit
startedAt
completedAt
result
rollbackResult (quando houver)
```

Não registrar PII, tokens ou credenciais.

## 10. Produção

Deploy em `prod` continua exigindo GitHub Environment protegido e aprovação humana.

A aprovação do deploy autoriza:

- publicação da release;
- smoke tests;
- rollback automático da release de aplicação para o estado capturado imediatamente antes do deploy caso o smoke falhe.

Não autoriza:

- rollback automático de banco de dados;
- `terraform destroy`;
- restauração automática de state;
- alterações destrutivas adicionais.

## 11. Relação com ADRs anteriores

- ADR-002: adiciona requisitos de rollback ao frontend S3 + CloudFront;
- ADR-004: passa a exigir versões publicadas e alias estável para Lambdas;
- ADR-009: incorpora rollback ao fluxo GitHub Actions;
- ADR-011: smoke tests acionam validação pós-deploy;
- ADR-015: usa PITR de 35 dias em `prod`;
- ADR-016: infraestrutura continua gerenciada pelo Terraform.

## 12. Consequências

### Positivas

- rollback de código Lambda rápido;
- frontend recuperável sem rebuild;
- infraestrutura não é revertida por manipulação indevida de state;
- recuperação de dados é deliberada e validada;
- mudanças de dados passam a considerar rollback desde o desenho.

### Negativas

- S3 Versioning e retenção de assets aumentam armazenamento;
- pipeline precisa capturar metadados da release anterior;
- Lambda aliases/versions aumentam objetos gerenciados;
- exige lifecycle para versões antigas;
- testes de rollback passam a fazer parte da engenharia.

## 13. Testes obrigatórios

Antes de considerar produção pronta:

1. rollback de uma Lambda para a versão anterior;
2. validação de que API Gateway continua chamando alias `live`;
3. rollback de `index.html` para versão S3 anterior;
4. invalidação CloudFront pós-rollback;
5. smoke test após rollback;
6. falha simulada de smoke disparando rollback automático da aplicação;
7. verificação de que nenhum rollback altera dados DynamoDB;
8. teste de restauração PITR em `dev` ou ambiente controlado para nova tabela;
9. teste de mudança backward-compatible;
10. validação de plano Terraform corretivo sem manipulação manual do state.

## Referências oficiais

- AWS Lambda — versions:
  https://docs.aws.amazon.com/lambda/latest/dg/configuration-versions.html
- AWS Lambda — aliases:
  https://docs.aws.amazon.com/lambda/latest/dg/configuration-aliases.html
- AWS Lambda — version control:
  https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/lambda-version-control.html
- Amazon S3 — Versioning:
  https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html
- Amazon S3 — restoring previous versions:
  https://docs.aws.amazon.com/AmazonS3/latest/userguide/RestoringPreviousVersions.html
- Amazon CloudFront — invalidation:
  https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Invalidation.html
- DynamoDB — PITR:
  https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Point-in-time-recovery.html
- DynamoDB — restore:
  https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/pointintimerecovery_restores.html
- Terraform — state:
  https://developer.hashicorp.com/terraform/language/state
- Terraform — recover state:
  https://developer.hashicorp.com/terraform/cli/state/recover
- GitHub Actions — deployments and environments:
  https://docs.github.com/actions/reference/workflows-and-actions/deployments-and-environments
