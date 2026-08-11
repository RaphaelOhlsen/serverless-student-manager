# Terraform bootstrap

Esta raiz Terraform cria somente a infraestrutura técnica necessária para o remote state e para
a federação do GitHub Actions com a AWS:

- bucket S3 privado e protegido para os states `bootstrap`, `dev` e `prod`;
- provider OIDC do GitHub Actions;
- roles distintas para deploy em `dev` e `prod`;
- policies de menor privilégio para os states de cada ambiente.

O bootstrap começa com state local. A migração do próprio state para
`bootstrap/terraform.tfstate` será uma operação posterior, controlada e explicitamente autorizada.
Não use Terraform Workspaces nem uma tabela DynamoDB para locking. As raízes de ambiente deverão
usar locking nativo do backend S3 com `use_lockfile = true`.

## Identidade inicial

Quando a execução for futuramente autorizada, o primeiro apply deverá usar uma identidade humana
federada e temporária, com permissões revisadas para criar estes recursos. Não crie, armazene nem
recomende access keys permanentes para o bootstrap.

Esta configuração não contém credenciais e não deve recebê-las em arquivos `.tf`, `.tfvars`, logs
ou no repositório.

O `prevent_destroy` reduz o risco de destruição acidental enquanto o lifecycle permanece na
configuração, mas não protege o recurso caso o bloco `aws_s3_bucket` seja removido da configuração.
A remoção do bucket de state exige revisão operacional explícita.

## Provider OIDC existente

Antes do primeiro apply, verifique de forma somente leitura e autorizada se a conta já possui um
provider OIDC para `https://token.actions.githubusercontent.com`. O IAM permite apenas um provider
por URL em uma conta.

Se ele já existir, não tente criar uma duplicata. Importe o provider existente para o state desta
raiz usando o endereço `aws_iam_openid_connect_provider.github_actions`, após revisão e autorização
específicas para o import. Esta verificação e o import não fazem parte desta tarefa.

## Configuração

Copie `bootstrap.tfvars.example` para um arquivo `.tfvars` local não versionado e substitua:

- `aws_region` pela região aprovada;
- `state_bucket_name` por um nome S3 globalmente único;
- `github_repository` pelo valor exato `owner/repository`.

As relações de confiança são deliberadamente fixas:

```text
dev  = repo:<owner>/<repository>:ref:refs/heads/main
prod = repo:<owner>/<repository>:environment:prod
aud  = sts.amazonaws.com
```

Não use wildcards nesses claims. O environment `prod` deverá ser protegido no GitHub antes do
primeiro deploy de produção.

## Validação local

Depois de autorização para baixar providers e plugins, os gates previstos são:

```shell
terraform -chdir=infra/bootstrap init -backend=false
terraform -chdir=infra/bootstrap fmt -check
terraform -chdir=infra/bootstrap validate
terraform -chdir=infra/bootstrap test
tflint --chdir=infra/bootstrap --config=.tflint.hcl --init
tflint --chdir=infra/bootstrap --config=.tflint.hcl
```

Os testes usam `mock_provider "aws"` e não devem acessar a AWS. O TFLint Deep Checking não está
habilitado e o lint não deve consultar a conta AWS.

## Aplicação e migração

`terraform plan`, `terraform apply`, `terraform import` e `terraform init -migrate-state` exigem
revisão e autorização humana separadas. A migração do state não deve acontecer junto da criação
inicial do bucket.

Não restaure uma versão antiga do state como mecanismo normal de rollback de infraestrutura. Use
uma alteração Terraform corretiva e revisada, conforme a ADR-020.
