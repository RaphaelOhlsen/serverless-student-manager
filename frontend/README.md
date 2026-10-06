# Frontend

SPA React + TypeScript construída com Vite para o Serverless Student Manager.

## Configuração pública

O build exige:

- `VITE_COGNITO_USER_POOL_ID`;
- `VITE_COGNITO_USER_POOL_CLIENT_ID`;
- `VITE_API_BASE_URL`.

Esses valores são identificadores e URLs públicos incorporados ao bundle. Nunca
use o prefixo `VITE_` para secrets. Para desenvolvimento local, copie os nomes de
`.env.example` para um arquivo local ignorado pelo Git.

## Comandos

```bash
npm ci
npm run lint
npm test
npm run build
```

O build de produção é criado em `dist/` e usa nomes fingerprinted em `assets/`.

## Release em dev

O workflow `.github/workflows/frontend-release.yml` obtém bucket, distribuição,
URL do frontend, Cognito e API dos outputs Terraform. Ele publica assets antes do
`index.html`, não exclui releases anteriores, invalida apenas os entry points e
executa smoke. Se o smoke falhar, restaura a versão anterior do `index.html`
quando disponível e mantém a release como failed.

O workflow está implementado, mas seu primeiro deploy é um gate operacional
separado. Hosting de produção, domínio próprio e CSP específica permanecem fora
deste incremento.
