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

## 5. Evolução

Grafana poderá consultar CloudWatch futuramente.

OpenTelemetry/Application Signals serão considerados quando houver maior distribuição.

AMP será considerado quando Prometheus/PromQL se tornar requisito.
