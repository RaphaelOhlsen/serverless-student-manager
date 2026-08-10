# ADR-010 — Observabilidade

**Status:** Approved  
**Data:** 2026-07-30

## Alternativas

1. Observabilidade mínima.
2. CloudWatch com logs e métricas estruturados.
3. Observabilidade distribuída completa.

## Decisão

Adotar a Opção 2:

- CloudWatch Logs.
- Access logs JSON do API Gateway.
- Logs JSON das Lambdas.
- Powertools for AWS Lambda para Logger e Metrics.
- Métricas técnicas e de negócio.
- Alarmes e dashboards.
- SNS para notificações.
- Correlação por request ID do API Gateway.

## Retenção

- `dev`: 14 dias.
- `prod`: 90 dias.

## Proteção de dados

Não registrar tokens, credenciais, senhas, cabeçalho `Authorization`, corpos completos, e-mail completo, telefone ou data de nascimento.

## Evolução futura

A base deverá permitir adicionar:

- OpenTelemetry;
- Application Signals;
- Grafana conectado ao CloudWatch;
- Amazon Managed Service for Prometheus;
- dashboards unificados no Grafana.

Essas tecnologias não fazem parte do MVP obrigatório.
