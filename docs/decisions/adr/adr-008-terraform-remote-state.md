# ADR-008 — Estado remoto do Terraform

**Status:** Approved  
**Data:** 2026-07-30

## Alternativas

1. Estado local.
2. Um bucket S3 com chaves por ambiente.
3. Um bucket por ambiente.

## Decisão

Utilizar um bucket S3 privado com estados separados:

```text
environments/dev/terraform.tfstate
environments/prod/terraform.tfstate
```

## Proteções

- Versionamento.
- Criptografia SSE-S3.
- Block Public Access.
- Exigência de HTTPS.
- IAM de menor privilégio.
- `use_lockfile = true`.
- Sem tabela DynamoDB para bloqueio.
- Bootstrap separado em `infra/bootstrap`.
- `.terraform.lock.hcl` versionado.
- `*.tfstate`, `.terraform/` e planos fora do Git.

## Organização

Não utilizar Terraform Workspaces para separar `dev` e `prod`; cada ambiente terá uma raiz explícita.

## Padrão de estilo

O código seguirá o Style Guide oficial da HashiCorp, com nomes descritivos em `snake_case`, interfaces claras de módulos, descrições de variáveis e formatação automática.
