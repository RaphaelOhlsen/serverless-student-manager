# ADR-017 — Consistência de provisionamento entre Cognito e DynamoDB

**Status:** Approved  
**Data:** 2026-08-10

## Contexto

A criação de um usuário administrativo envolve dois serviços independentes:

- Amazon Cognito, responsável pela identidade;
- Amazon DynamoDB, fonte de verdade da aplicação para `role`, `status` e projeção de autorização.

Não existe transação ACID única envolvendo Cognito e DynamoDB.

A ADR-013 determinou que o primeiro Administrador seja criado por um processo controlado com compensação em caso de inconsistência, porém não definiu a ordem operacional e os mecanismos de recuperação.

O mesmo problema existe na criação normal de Administradores e Operadores pela `users-api`.

## Alternativas consideradas

### Opção A — Cognito cria e envia convite imediatamente; DynamoDB depois

Vantagens:

- fluxo simples;
- segue literalmente o fluxo resumido da ADR-013.

Desvantagens:

- o usuário pode receber credenciais antes de existir a projeção de autorização no DynamoDB;
- uma falha no DynamoDB exige excluir a identidade Cognito depois que o convite já foi enviado;
- cria uma janela de inconsistência visível ao usuário.

### Opção B — DynamoDB primeiro; Cognito depois

Vantagens:

- unicidade de e-mail pode ser reservada antes da criação da identidade;
- nenhuma identidade Cognito é criada se a transação DynamoDB falhar.

Desvantagens:

- pode deixar reservas internas sem identidade após falhas ambíguas no Cognito;
- altera mais significativamente o fluxo aprovado na ADR-013.

### Opção C — Cognito cria identidade sem enviar convite; DynamoDB confirma; convite é enviado depois

Vantagens:

- mantém Cognito como primeiro sistema a criar a identidade;
- impede envio de credenciais antes da consistência interna;
- permite compensar com exclusão/disable antes de qualquer convite;
- uma falha apenas no envio do convite deixa um estado recuperável: usuário `INVITED`.

Desvantagens:

- exige uma sequência tipo saga;
- exige tratamento explícito de falhas ambíguas;
- o envio do convite é uma terceira etapa.

## Decisão proposta

Adotar a **Opção C**.

### Identificador Cognito

O backend gera `userId` antes da chamada ao Cognito.

O Cognito usa esse `userId` como `Username` técnico e imutável.

O e-mail é configurado como alias de login, para que o usuário continue autenticando com e-mail.

A identidade de autorização da aplicação continua sendo o Cognito `sub`, conforme ADR-006.

### Fluxo de criação

```text
requisição idempotente
  ↓
gerar/reutilizar userId
  ↓
AdminCreateUser
  Username = userId
  MessageAction = SUPPRESS
  ForceAliasCreation = false
  ↓
capturar Cognito sub
  ↓
TransactWriteItems
  USER#userId
  UNIQUE#EMAIL#normalizedEmail
  COGNITO#sub
  evento de auditoria
  ↓
AdminCreateUser
  MessageAction = RESEND
  ↓
usuário permanece INVITED
```

### Transação DynamoDB

A transação deve criar atomicamente:

1. `USER#<userId>`;
2. `UNIQUE#EMAIL#<normalizedEmail>`;
3. `COGNITO#<sub>`;
4. evento de auditoria de criação bem-sucedida, quando possível na mesma transação.

O usuário é criado com status de negócio `INVITED`.

O contador de Administradores ativos não é incrementado durante o convite porque `INVITED` não é `ACTIVE`.

### Idempotência

A operação HTTP continua protegida pela ADR-012.

O `userId` gerado para a primeira tentativa é preservado na execução idempotente e reutilizado em retries.

`TransactWriteItems` usa `ClientRequestToken` como proteção adicional durante sua janela nativa.

A idempotência de aplicação, com TTL de 24 horas, permanece a fonte principal de replay após a janela nativa do DynamoDB.

## Compensação

### Cognito criado; DynamoDB falha definitivamente

1. não enviar convite;
2. executar `AdminDeleteUser`;
3. registrar tentativa de provisionamento com falha;
4. se a exclusão também falhar, executar `AdminDisableUser` quando possível;
5. gerar alerta operacional para reconciliação.

### Resultado Cognito ambíguo

Após timeout ou erro cuja conclusão seja desconhecida:

1. consultar `AdminGetUser` usando o `userId`;
2. se o usuário não existir, repetir a criação;
3. se existir e corresponder ao e-mail esperado, continuar;
4. se existir com dados incompatíveis, interromper e gerar alerta de consistência.

### Resultado DynamoDB ambíguo

1. consultar os itens de aplicação de forma consistente;
2. se a transação estiver materializada corretamente, continuar;
3. caso contrário, repetir a mesma transação dentro da janela de idempotência nativa;
4. após essa janela, reconstruir o estado a partir da idempotência da aplicação e das condições dos itens, sem criar uma nova identidade Cognito.

### Falha no envio do convite

A falha em `RESEND` **não desfaz** Cognito nem DynamoDB.

O usuário permanece `INVITED`.

O erro é auditado e o Administrador pode executar novamente o fluxo de reenvio de convite previsto em RF-USR-008.

## Segurança

- `ForceAliasCreation` permanece `false`; o sistema nunca toma um alias de outro usuário automaticamente.
- nenhum password/TOTP é persistido pela aplicação;
- não registrar e-mail completo nos logs operacionais;
- operações Cognito usam IAM de menor privilégio;
- uma identidade sem projeção DynamoDB não recebe autorização funcional.
- um estado inconsistente não deve ser corrigido silenciosamente por adoção de outra identidade existente.

## Relação com ADRs anteriores

- Mantém ADR-006: em operação normal, o `sub` é a identidade imutável utilizada para autorização.
- A ADR-019 governa a única exceção break-glass controlada, na qual a identidade Cognito é substituída; nessa exceção, o `userId` de negócio permanece imutável e a projeção `COGNITO#<sub>` anterior é substituída pela projeção do novo `sub`.
- Mantém ADR-012: idempotência de aplicação.
- Mantém ADR-013: bootstrap controlado e Cognito como primeira criação de identidade.
- **Refina a ADR-013**: o envio efetivo do convite ocorre somente após a persistência transacional no DynamoDB.

Se aprovada, a ADR-013 deve receber uma nota apontando para esta ADR no trecho de ordenação do convite.

## Consequências

### Positivas

- reduz janela de inconsistência percebida pelo usuário;
- retries tornam-se reconciliáveis;
- evita envio de convite para identidade que precisará ser compensada;
- reutiliza o estado `INVITED` já definido no SRS.

### Negativas

- maior complexidade na `users-api` e no bootstrap;
- necessidade de testes de falha por etapa;
- necessidade de alarmes para compensações incompletas.

## Testes obrigatórios

Devem existir testes para:

1. criação completa;
2. retry da mesma requisição;
3. Cognito rejeitando duplicidade;
4. timeout ambíguo do Cognito;
5. DynamoDB rejeitando e-mail duplicado;
6. timeout ambíguo da transação DynamoDB;
7. compensação com `AdminDeleteUser`;
8. falha da compensação e fallback para disable;
9. falha no `RESEND`;
10. reenvio posterior do convite.

## Refinamento posterior — ADR-024

A **ADR-024 — Protocolo determinístico e trava singleton do bootstrap do primeiro Admin**, aprovada em 2026-08-20, complementa esta decisão exclusivamente para o bootstrap inicial. Nesse fluxo especial, a transação passa de quatro para cinco itens com a inclusão de `CONTROL#FIRST_ADMIN_BOOTSTRAP / CONTROL`, e a reconciliação confirma também o marker e o audit event.

O provisionamento normal de usuários preserva a transação original de quatro itens descrita nesta ADR e não utiliza o marker singleton do primeiro Admin.
