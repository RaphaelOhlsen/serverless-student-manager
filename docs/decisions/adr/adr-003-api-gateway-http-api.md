# ADR-003 — Tipo de API Gateway

**Status:** Approved  
**Data:** 2026-07-30

## Alternativas

1. API Gateway HTTP API.
2. API Gateway REST API.

## Decisão

Utilizar Amazon API Gateway HTTP API, integrado às Lambdas e protegido por JWT Authorizer conectado ao Cognito.

## Justificativa

A HTTP API atende ao MVP com menor complexidade, integração direta com Lambda, CORS e autorização JWT.

## Consequências

- A API continuará seguindo princípios RESTful.
- Recursos exclusivos do produto REST API não estarão disponíveis.
- A decisão será reavaliada se surgirem requisitos como usage plans, API keys, cache do API Gateway, endpoint privado ou associação direta com WAF.
