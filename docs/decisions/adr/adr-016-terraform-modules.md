# ADR-016 — Organização dos módulos Terraform

**Status:** Approved

## Decisão

Organizar módulos locais por capacidade arquitetural.

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

## Regras

- raízes independentes para `bootstrap`, `dev` e `prod`;
- três estados separados;
- composição plana;
- módulos filhos não chamam outros módulos;
- root modules conectam outputs e inputs;
- providers configurados somente nas raízes;
- child modules apenas declaram providers exigidos;
- seguir HashiCorp Style Guide;
- não usar provisioners para build/deploy;
- GitHub Actions faz build, upload e invalidação CloudFront.

## Estados

```text
bootstrap/terraform.tfstate
environments/dev/terraform.tfstate
environments/prod/terraform.tfstate
```

## Tags

Tags transversais:

```text
Project
Environment
ManagedBy
Workload
Component
DataClassification
```

Valores controlados de `Workload`:

```text
student-management
infrastructure-management
deployment-automation
```

Exemplos de `Component`:

```text
frontend
api
identity
students
users
audit
idempotency
observability
terraform-state
cicd
```

Classificações possíveis:

```text
public
internal
confidential
restricted
```

Nenhuma tag pode conter PII ou segredos.
