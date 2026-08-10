# ADR-002 — Hospedagem do frontend

**Status:** Approved  
**Data:** 2026-07-30

## Contexto

O frontend React será compilado em arquivos estáticos e precisa de distribuição segura.

## Alternativas

1. S3 público.
2. S3 privado com CloudFront.
3. Serviço de hospedagem gerenciada adicional.

## Decisão

Hospedar o build em bucket S3 privado e distribuí-lo exclusivamente pelo CloudFront.

## Consequências

- O bucket não será público.
- CloudFront será o ponto de acesso.
- O pipeline enviará o build e invalidará o cache quando necessário.
- Rotas de SPA retornarão `index.html` de forma controlada.
- Cabeçalhos de segurança serão configurados.
- Domínio próprio e certificado poderão ser adicionados depois.
