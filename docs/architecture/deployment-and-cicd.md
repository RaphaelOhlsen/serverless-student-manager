# Infraestrutura, ambientes e CI/CD

**Versão:** 2.5
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

GitHub Environments operacionais iniciais:

```text
dev-bootstrap-admin
dev-admin-recovery
prod-admin-recovery
```

Cada capacidade operacional usa trust policy e policy IAM próprias, com `sub` OIDC exato e sem wildcards.

O provider OIDC existente é reutilizado pelas roles operacionais; nenhum segundo provider OIDC é criado.

Actions externas devem ser fixadas por SHA completo.

## 5. Builds

GitHub Actions executa:

- build frontend;
- empacotamento backend;
- upload S3;
- invalidação CloudFront.

Terraform não usa provisioners para essas ações.

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
