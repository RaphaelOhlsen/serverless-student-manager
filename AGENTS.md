# AGENTS.md — Serverless Student Manager

## 1. Papel do agente

Você atua como engenheiro executor do **Serverless Student Manager**.

Implemente somente tarefas explicitamente solicitadas e aprovadas.
Não altere requisitos, arquitetura ou decisões registradas sem autorização humana.

## 2. Fonte de verdade

A pasta `docs/` é a fonte oficial e canônica da documentação do projeto.

Antes de planejar ou implementar qualquer tarefa, consulte nesta ordem:

1. `docs/README.md`
2. `docs/serverless-student-manager-ordem-de-leitura.md`
3. `docs/overview.md`
4. `docs/requirements/srs.md`
5. `docs/decisions/decision-register.md`
6. ADRs aplicáveis em `docs/decisions/adr/`
7. documentos aplicáveis em `docs/architecture/`
8. runbooks aplicáveis em `docs/operations/`

Quando houver conflito, use a seguinte precedência:

1. requisitos aprovados no SRS;
2. ADRs aprovadas;
3. Decision Register;
4. documentos consolidados de arquitetura;
5. código existente.

Não invente decisões para preencher lacunas.

## 3. Fluxo obrigatório antes de modificar arquivos

Antes de modificar qualquer arquivo:

1. leia a documentação relacionada;
2. inspecione o estado atual do repositório;
3. apresente um plano;
4. liste os arquivos que pretende criar ou modificar;
5. identifique riscos, dúvidas e decisões ausentes;
6. aguarde aprovação humana.

Depois da aprovação:

1. implemente apenas o escopo autorizado;
2. execute formatadores, análise estática e testes aplicáveis;
3. apresente um resumo das mudanças;
4. informe os comandos executados;
5. informe testes aprovados e falhos;
6. apresente os arquivos modificados;
7. apresente o `git diff` relevante antes de commit quando solicitado.

## 4. Ações proibidas sem autorização explícita

Não executar sem autorização humana:

- `terraform apply`;
- `terraform destroy`;
- deploy na AWS;
- criação, alteração destrutiva ou exclusão de recursos AWS;
- alteração em produção;
- exclusão de documentação aprovada;
- alteração silenciosa de ADRs aprovadas;
- mudança dos serviços AWS definidos;
- mudança do modelo físico aprovado do DynamoDB;
- ampliação de permissões IAM;
- commits, pushes, merges ou criação de tags Git.

## 5. Arquitetura aprovada

- Monorepo.
- Frontend: React + TypeScript.
- Backend: Python + AWS Lambda.
- API: Amazon API Gateway HTTP API.
- Autenticação: Amazon Cognito.
- Autorização: JWT Authorizer + validação funcional nas Lambdas.
- Persistência: DynamoDB por domínio.
- Frontend: S3 privado + CloudFront.
- Infraestrutura: Terraform.
- CI/CD: GitHub Actions com OIDC.
- Observabilidade: CloudWatch.
- Ambientes: `dev` e `prod`, inicialmente na mesma conta AWS.
- ADR-001 a ADR-023: `Approved`.

## 6. Segurança

- princípio do menor privilégio;
- nenhuma credencial AWS permanente no GitHub;
- nenhuma senha no código, Terraform ou DynamoDB;
- não registrar tokens, credenciais ou dados pessoais completos;
- não colocar dados pessoais ou segredos em tags;
- MFA TOTP obrigatório para `ADMIN` e `OPERATOR`;
- access e ID tokens de 15 minutos;
- refresh token de 8 horas com rotação;
- operações destrutivas exigem aprovação humana.

## 7. Terraform

Seguir o Style Guide oficial da HashiCorp.

- nomes descritivos em `snake_case`;
- providers configurados somente nos módulos raiz;
- módulos locais por capacidade arquitetural;
- composição plana;
- estados separados para `bootstrap`, `dev` e `prod`;
- `terraform fmt`;
- `terraform validate`;
- TFLint;
- `terraform test`;
- `.terraform.lock.hcl` versionado;
- não usar provisioners, `null_resource` ou `local-exec` para build/deploy da aplicação.

## 8. Tags AWS

Tags comuns:

- `Project`
- `Environment`
- `ManagedBy`
- `Workload`
- `Component`
- `DataClassification`

Valores controlados de `Workload`:

- `student-management`
- `infrastructure-management`
- `deployment-automation`

Nenhuma tag pode conter dados pessoais ou segredos.

## 9. Qualidade e testes

- backend: cobertura mínima de 80%;
- frontend: cobertura mínima de 70%;
- fluxos críticos devem ser testados independentemente da cobertura;
- testes locais e de PR não devem alterar recursos AWS;
- integração real ocorre no ambiente `dev`;
- Playwright será usado em E2E;
- smoke tests serão executados após deploy.

## 10. Atualização da documentação

Toda decisão aprovada que afete requisitos, arquitetura, segurança,
infraestrutura, dados, testes ou operação deve atualizar os documentos
correspondentes na mesma tarefa.

O agente deve:

1. identificar os documentos afetados;
2. atualizar somente os arquivos necessários;
3. manter o Decision Register consistente;
4. atualizar a ordem de leitura quando novos documentos forem adicionados;
5. apresentar o diff para revisão;
6. não modificar silenciosamente uma ADR aprovada.

Uma nova decisão arquitetural deve ser registrada em uma nova ADR.


## 11. Engenharia pronta

A documentação canônica v2.4 está classificada como `Engineering Ready`.

Isso não autoriza automaticamente deploy, `terraform apply`, alterações destrutivas,
mudanças de produção ou decisões arquiteturais novas. Essas ações continuam sujeitas
às regras de aprovação deste arquivo.

ADRs novas devem começar em ADR-021.
