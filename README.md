# Serverless Student Manager

Aplicação web para gerenciamento de alunos de uma instituição de ensino e demonstração de práticas profissionais de engenharia em uma arquitetura serverless na AWS.

A documentação canônica do projeto está em [`docs/`](docs/).

Antes de planejar ou implementar mudanças, consulte:

- [`AGENTS.md`](AGENTS.md);
- [guia canônico de leitura](docs/serverless-student-manager-ordem-de-leitura.md).

## Baselines de desenvolvimento

- Python 3.13;
- Node.js 24.x;
- Terraform CLI 1.15.8.

## Pré-requisitos

- Python 3.13 com suporte a `venv`;
- Node.js 24.x e npm;
- GNU Make;
- Terraform CLI 1.15.8 somente quando os artefatos de infraestrutura forem introduzidos.

## Setup local

Instale as dependências de desenvolvimento com:

```shell
make setup
```

O comando cria `.venv`, instala o tooling Python de `requirements-dev.txt` e instala as
dependências Node.js registradas em `package-lock.json`. Ele não instala dependências de runtime das
futuras funções Lambda.

## Comandos locais

| Comando                | Finalidade                                                   |
| ---------------------- | ------------------------------------------------------------ |
| `make setup`           | Preparar o ambiente local de desenvolvimento                 |
| `make format`          | Formatar os arquivos atualmente suportados                   |
| `make format-check`    | Verificar formatação sem alterar arquivos                    |
| `make lint`            | Executar Ruff e ESLint                                       |
| `make typecheck`       | Executar os verificadores aplicáveis de tipos                |
| `make test`            | Executar as suítes de testes existentes                      |
| `make coverage`        | Aplicar os gates de cobertura disponíveis                    |
| `make security`        | Auditar dependências Python e Node.js                        |
| `make terraform-init`  | Instalar providers localmente, sem configurar backend remoto |
| `make tflint-init`     | Instalar o ruleset AWS do TFLint                             |
| `make terraform-check` | Executar os gates Terraform após as inicializações           |
| `make check`           | Executar todos os quality gates atualmente aplicáveis        |

Os gates Terraform fazem parte dos comandos agregados. Antes da primeira execução, rode
`make terraform-init` e `make tflint-init`; esses comandos baixam dependências, mas não acessam uma
conta AWS nem configuram o backend remoto. OpenAPI será incluído quando seus artefatos reais forem
introduzidos.
