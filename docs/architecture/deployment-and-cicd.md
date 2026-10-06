# Infraestrutura, ambientes e CI/CD

**Versão:** 3.3
**Status:** Approved

## 1. Ambientes

`dev` e `prod` usarão inicialmente a mesma conta AWS, com recursos independentes.

O projeto pode começar somente com `dev`.

## 2. Terraform

```text
infra/
├── bootstrap/
├── modules/
│   ├── frontend_hosting/
│   ├── identity/
│   ├── student_store/
│   ├── user_store/
│   ├── audit_store/
│   ├── idempotency_store/
│   ├── lambda_service/
│   ├── http_api/
│   ├── observability/
│   └── operational_access/
└── environments/
    ├── dev/
    └── prod/
```

Composição plana: child modules não chamam outros child modules.

## 3. Estados

Um bucket S3 privado armazenará estados separados:

```text
bootstrap/terraform.tfstate
environments/dev/terraform.tfstate
environments/prod/terraform.tfstate
```

- versioning;
- SSE-S3;
- Block Public Access;
- HTTPS obrigatório;
- `use_lockfile=true`;
- sem DynamoDB locking;
- sem Terraform Workspaces;
- `.terraform.lock.hcl` versionado.

O bootstrap inicia localmente e depois migra seu estado para S3.

## 4. CI/CD

```text
Pull Request
  → format/lint/static analysis
  → testes
  → build
  → OpenAPI lint
  → Terraform fmt/validate/test/TFLint
  → sem alterações na AWS

Merge main
  → OIDC
  → deploy automático em dev

Produção
  → workflow manual
  → GitHub Environment protegido
  → função IAM exclusiva de prod

Operações privilegiadas
  → workflow manual
  → GitHub Environment específico
  → OIDC
  → role IAM operacional separada da role de deploy
```

GitHub Environments operacionais:

```text
dev-bootstrap-admin
dev-resume-first-admin-invitation
dev-verify-first-admin-email
dev-admin-recovery
prod-admin-recovery
```

`dev-verify-first-admin-email` foi aprovado arquiteturalmente pela ADR-025. O
workflow e a infraestrutura declarativa correspondentes estão implementados no
repositório, mas o Environment, suas variables e os recursos IAM ainda não
foram provisionados ou configurados.

Cada capacidade operacional usa trust policy e policy IAM próprias, com `sub` OIDC exato e sem wildcards.

O bootstrap inicial, a retomada do convite e a verificação do e-mail possuem
workflows privilegiados manuais, distintos dos pipelines normais de CI e
deploy:

```text
.github/workflows/bootstrap-first-admin.yml
.github/workflows/resume-first-admin-invitation.yml
.github/workflows/verify-first-admin-email.yml
```

Os dois primeiros usam somente `workflow_dispatch`. Seus jobs estão associados,
respectivamente, a `dev-bootstrap-admin` e
`dev-resume-first-admin-invitation`. Esses dois Environments exigem
`RaphaelOhlsen` como reviewer, usam `prevent_self_review=false`, não permitem
bypass administrativo e não possuem wait timer ou política customizada de
branches/tags. O terceiro workflow também usa somente `workflow_dispatch`, mas
seu Environment ainda não foi criado ou protegido.

Os workflows estão versionados, os Environments estão protegidos e suas Environment variables estão completas e verificadas: `8/8` para o bootstrap e `6/6` para a retomada, sem Environment secrets. A role e a policy dedicadas à retomada foram aplicadas e verificadas na AWS; o apply criou três recursos sem alterar ou destruir infraestrutura existente, e o plan pós-apply confirmou convergência sem drift.

Os workflows estão disponíveis para `workflow_dispatch` na default branch `main`. Eles continuam sendo workflows operacionais manuais privilegiados, não etapas do pipeline normal de CI ou deploy. A primeira execução do bootstrap falhou após criar a identidade Cognito com mensagem suprimida e antes da persistência transacional; nenhum convite foi enviado e não houve validação end-to-end. O estado parcial deve permanecer congelado até reconciliação aprovada.

No bootstrap, nome e e-mail são lidos em runtime do payload indicado por `GITHUB_EVENT_PATH`, recebem `add-mask` antes do uso e não são declarados no bloco `env`. O masking protege a saída do runner, mas não transforma inputs de `workflow_dispatch` em secrets nem elimina sua exposição potencial na metadata ou UI do GitHub.

O provider OIDC existente é reutilizado pelas roles operacionais; nenhum segundo provider OIDC é criado.

O workflow `verify-first-admin-email.yml` usa exclusivamente
`workflow_dispatch`, recebe somente `operation_id`, deriva o ator da identidade
GitHub e referencia a role por Environment variable. Ele requer o Environment
`dev-verify-first-admin-email`, ainda não criado, e a role
`student-manager-github-dev-verify-first-admin-email`, ainda não provisionada.
O merge do workflow e do Terraform não disponibiliza por si só a operação.

A capacidade usa subject OIDC exato, sem wildcard, e não reutiliza as roles de
bootstrap ou recuperação. Sua policy declarada limita Cognito a `AdminGetUser`
e `AdminUpdateUserAttributes` no User Pool correto, além das permissões
DynamoDB mínimas para reconciliação, idempotência e auditoria.

O CI Python de bootstrap administrativo cobre conjuntamente
`tools/bootstrap_admin` e `tools/verify_first_admin_email` com Ruff, mypy e
pytest. O Terraform CI executa também os testes mockados do root
`infra/environments/dev`, além de fmt, validate e TFLint, sem credenciais AWS.

A ADR-025 não autoriza implicitamente capacidade equivalente em `prod`.

Actions externas devem ser fixadas por SHA completo.

## 5. Builds

GitHub Actions executa:

- build frontend;
- empacotamento backend;
- upload S3;
- invalidação CloudFront.

Terraform não usa provisioners para essas ações.

### 5.1 Hosting frontend implantado em `dev`

O módulo `infra/modules/frontend_hosting` e sua composição em
`infra/environments/dev` declaram:

- bucket S3 privado, sem website hosting, com Block Public Access,
  `BucketOwnerEnforced`, SSE-S3 e Versioning;
- CloudFront como único caminho público, usando o domínio e certificado default;
- Origin Access Control com assinatura SigV4 e bucket policy limitada ao ARN da
  distribuição;
- `SecurityHeadersPolicy` gerenciada pela AWS;
- CloudFront Function no evento `viewer-request`, reescrevendo somente paths sem
  extensão para `/index.html`; o comportamento `/assets/*` não usa essa função e
  assets ausentes não são mascarados;
- cache desabilitado para o entry point e rotas SPA, e cache de um ano para
  assets fingerprinted em `/assets/*`;
- outputs de bucket, distribuição e URL para o pipeline futuro;
- policy mínima anexada à role existente
  `student-manager-github-dev-deploy`, limitada a publicação/restauração de
  objetos e invalidação da distribuição, sem `s3:DeleteObject`.

O hosting foi aplicado em `dev` e o plan pós-apply confirmou convergência sem
drift. O bucket permanece privado e pode continuar vazio até o primeiro release.

### 5.2 Release frontend automatizada em `dev`

O workflow `.github/workflows/frontend-release.yml` está implementado e ainda
não foi executado. Ele dispara automaticamente apenas para mudanças em
`frontend/**` enviadas à `main` e também oferece `workflow_dispatch` na própria
`main`. Alterações no workflow, helper, documentação ou Terraform não disparam o
primeiro deploy por si só.

O job usa OIDC com a role existente `student-manager-github-dev-deploy`. Não usa
GitHub Environment porque o trust atual dessa role restringe o subject à ref
`refs/heads/main`; associar um Environment mudaria o subject OIDC. O nome do
bucket de state deve ser fornecido pela repository variable
`TERRAFORM_STATE_BUCKET`. Depois do `terraform init`, todos os alvos de aplicação
e as configurações públicas do Vite são obtidos por `terraform output`:

- `frontend_bucket_name`;
- `frontend_cloudfront_distribution_id`;
- `frontend_cloudfront_domain_name`;
- `frontend_url`;
- `cognito_user_pool_id`;
- `cognito_user_pool_client_id`;
- `http_api_endpoint`.

O build usa as três últimas configurações como
`VITE_COGNITO_USER_POOL_ID`, `VITE_COGNITO_USER_POOL_CLIENT_ID` e
`VITE_API_BASE_URL`. Elas são identificadores/URLs públicos incorporados ao
bundle; nenhum segredo usa o prefixo `VITE_`.

O helper `tools/frontend_release/release.py` captura a versão corrente de
`index.html`, publica assets fingerprinted com cache imutável, publica os demais
arquivos com cache conservador e envia `index.html` por último com `no-cache` e
metadata `commit-sha`. Não usa exclusão nem `sync --delete`. Em seguida invalida
somente `/` e `/index.html`, aguarda a invalidação e valida frontend, asset,
security headers e `GET /health`.

Se o smoke falhar e existir uma versão anterior, o helper copia essa versão S3
de `index.html` para uma nova versão corrente, repete invalidação e smoke e mantém
o workflow como failed. No primeiro release, a ausência de versão anterior é
registrada como `ROLLBACK_NOT_AVAILABLE_FIRST_RELEASE`, sem excluir conteúdo.
O primeiro release permanece reservado a gate operacional separado.

CSP específica, domínio próprio, ACM, Route 53, WAF e hosting de `prod`
permanecem fora deste incremento. A policy gerenciada de security headers é a
proteção aprovada nesta fase.

## 6. Tags

Tags:

```text
Project
Environment
ManagedBy
Workload
Component
DataClassification
```

`Workload`:

```text
student-management
infrastructure-management
deployment-automation
```


## 7. Rollback

Conforme ADR-020:

- Lambda usa versões publicadas e alias estável `live`;
- frontend usa S3 Versioning, assets imutáveis e restauração dos entry points;
- CloudFront é invalidado após restauração do frontend;
- infraestrutura é corrigida por novo `terraform plan` revisado;
- `terraform.tfstate` não é mecanismo normal de rollback;
- DynamoDB PITR restaura para nova tabela;
- mudanças de dados devem preferir `expand-contract`;
- rollback automático pós-smoke é limitado à release da aplicação dentro de workflow já aprovado.

Para `dev`, o workflow implementado restaura automaticamente a versão anterior
de `index.html` após falha de smoke, invalida os entry points e executa novo
smoke. A release original continua marcada como failed mesmo quando a restauração
recupera o serviço. O workflow ainda não foi executado nesta baseline.
