# Observabilidade

**Versão:** 2.7
**Status:** Approved

## 1. Base

CloudWatch será a plataforma central:

- logs JSON das Lambdas;
- access logs JSON da HTTP API;
- métricas nativas;
- métricas customizadas via Embedded Metric Format;
- Powertools Logger/Metrics;
- dashboards;
- alarmes;
- SNS para notificações.

## 2. Correlação

O request ID do API Gateway será propagado como `correlationId` para:

- access logs;
- Lambda logs;
- respostas de erro;
- eventos de auditoria.

`awsRequestId` permanece separado.

CLIs operacionais emitem diagnóstico sanitizado e determinístico. Os campos permitidos são `stage`, `service`, `operation`, `exceptionClass`, `awsErrorCode`, `awsRequestId` e `operationId`; na persistência inicial, o estágio é `PERSIST_FIRST_ADMIN_TRANSACTION`. Códigos de cancellation reasons podem ser registrados sem mensagens ou itens associados. A exceção original permanece encadeada internamente, mas traceback, mensagem bruta da AWS e payloads não são enviados ao log normal do operador.

## 3. Retenção

| Dado | `dev` | `prod` |
|---|---:|---:|
| CloudWatch Logs | 14 dias | 90 dias |
| Audit events | 90 dias | 5 anos |
| Idempotência | 24 horas | 24 horas |

## 4. Dados proibidos

- senhas;
- tokens;
- credenciais;
- `Authorization`;
- corpos completos;
- e-mail completo;
- telefone;
- nascimento.

Inputs pessoais de `workflow_dispatch` não se tornam secrets por serem mascarados. O runner deve registrar `add-mask` antes do uso, mas metadata e UI do GitHub permanecem fora dessa garantia de masking de logs.

## 5. Evolução

Grafana poderá consultar CloudWatch futuramente.

OpenTelemetry/Application Signals serão considerados quando houver maior distribuição.

AMP será considerado quando Prometheus/PromQL se tornar requisito.
