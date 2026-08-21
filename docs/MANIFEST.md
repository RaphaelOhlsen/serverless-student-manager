# Manifesto do pacote canônico v2.7 — Engineering Ready

**Projeto:** Serverless Student Manager
**Versão:** 2.7
**Data:** 2026-08-20
**Arquivos listados:** 48

O próprio `MANIFEST.md` não é listado para evitar hash autorreferencial.

## Arquivos e SHA-256

| Arquivo | SHA-256 |
|---|---|
| `AGENTS.md` | `beafa571941a98ccd89f087f21939be4c6d0d44b660c4e7623f15260f5844448` |
| `RESTORE-INSTRUCTIONS.md` | `9f7d55d96f112e2bb50f73995f2ca42fbb5a4bbb5ba4b32fb54ba2beb6438e8d` |
| `docs/AUDIT-REPORT.md` | `60eb194a127c553fcf6b9ebe991ab8ba403deebeead4bd49c284b00794e7e13f` |
| `docs/DOCUMENTATION-VERSION.md` | `c5aeecfe512d636227ff698df0f61aa08b0907b00d77d518ea810c197668c11d` |
| `docs/ENGINEERING-READINESS.md` | `1a890640dbd850a116d57311e9afc5b2197b0b3c1bd6b6f8e30bfab90ebac36a` |
| `docs/README.md` | `0255a84b5167767c07a618545256928147d2e660ddb0f8c82ea527f236a61811` |
| `docs/architecture/architecture-overview.md` | `8b32c3b900aeb63c7b81317fb7e65c404b8f6589f18f901bc4a09941525320af` |
| `docs/architecture/data-model.md` | `8e37ad31c4891ad27b6976ca2a7b26e8916328518b1a14e6394ac7a4b5a5548a` |
| `docs/architecture/deployment-and-cicd.md` | `0f9a7264438a0811a7d37e1f69a8490667ea0d28872602dde58d35b2e01fff23` |
| `docs/architecture/diagrams.md` | `c6d18b9af0cb28f495bb1e86fb785b73da81a63cf508a13716dd9d706b1965cc` |
| `docs/architecture/observability.md` | `fbce8a6786cd5a301548219f2a121cbd61b431a4bfa6656cbeaf94506b3a0d21` |
| `docs/architecture/security.md` | `9b3602120339f074e754f1a9e43cfcd36f4e43dc1ec62f4fe95b6b07a7d40c17` |
| `docs/decisions/adr/adr-001-monorepo.md` | `68549fff169d8fd5190e4502f17f6a89b61fb05579ac5b4b0c535bf03f885c8f` |
| `docs/decisions/adr/adr-002-frontend-hosting.md` | `ca847e03a949c9dcbd74575bd0ac4c2f46985397770456d8089afaeb6d9c0add` |
| `docs/decisions/adr/adr-003-api-gateway-http-api.md` | `d7746a1ce7e1246d862d91acde9e31e1c4fcd5637855429c1e32b46d6afe8d65` |
| `docs/decisions/adr/adr-004-lambda-organization.md` | `1276cb9fa6e9b1f389986e6898b3850a88fe5479221145970f33fb82b53e0e33` |
| `docs/decisions/adr/adr-005-dynamodb-modeling.md` | `2163cb4bd42397c019bf07ea781bfb286985be6a6011dc1e51edf9d02fea1bbe` |
| `docs/decisions/adr/adr-006-authentication-authorization.md` | `abfcc96eac25a0ff6b49ae8a75c245f489c4db5def1e54a5a174443ae82d5586` |
| `docs/decisions/adr/adr-007-environments.md` | `5859aaa39ab9afa9c87c3946855a6518147340043245ab497a9c7f246bc664b1` |
| `docs/decisions/adr/adr-008-terraform-remote-state.md` | `886b185b0e2abf25957d04899f2f061aee73e3e17a5b5b912617f83dd88c1089` |
| `docs/decisions/adr/adr-009-cicd-oidc.md` | `03b3312a241a0dace595e19be02d54ed1bb2bef20180de244de0890b0e8e399d` |
| `docs/decisions/adr/adr-010-observability.md` | `127a43fcf1899fad919238a7cdb594ed852e17f2442818abc12473a9486a404e` |
| `docs/decisions/adr/adr-011-testing-strategy.md` | `5209b902e2033ae6fb875de75f41b75abbd72130eb03949e3a89cf51ffcb97c9` |
| `docs/decisions/adr/adr-012-idempotency.md` | `c56101c8dc4fa3541a4bd8c37c62ac0c8ff4ac8f440c2b695ea3126f3339ebb4` |
| `docs/decisions/adr/adr-013-first-admin-bootstrap.md` | `6573a833c209002a2ca97b1afb5e1494d55cc90dc34f524d6be30f2518aee9cf` |
| `docs/decisions/adr/adr-014-mfa-security.md` | `49359c2703cf130dac2ff4cd6a3c06c35d324232714a5433e91e8d9fd820dcc9` |
| `docs/decisions/adr/adr-015-audit-retention.md` | `e73a542d56837a33aeba8521589440a682958ede6a7a89547fe14991bdff2da5` |
| `docs/decisions/adr/adr-016-terraform-modules.md` | `0ae86449cb73fca06892d59997384bda87e0e42b77a11d2382baddfa2acce0ee` |
| `docs/decisions/adr/adr-017-cognito-dynamodb-provisioning-consistency.md` | `356714683949e3f2724be610275cf38150fef43225c8ac81fe5fcdade91d0cc9` |
| `docs/decisions/adr/adr-018-non-http-idempotency.md` | `aa624fb7b63594cebac8cef03ee4d4fcc3fb1ff8d259db4b6374890b1c89f255` |
| `docs/decisions/adr/adr-019-sole-admin-mfa-recovery.md` | `dd9eb396e14d3d6cf35834d96649babec9bf428bbfa28c2835efdba345ba4530` |
| `docs/decisions/adr/adr-020-rollback-strategy.md` | `8c8cfb74f59359e7c110ec6f5c481b31bef1aeb75c9598a8751254404a3dfc06` |
| `docs/decisions/adr/adr-021-audit-index-modeling.md` | `d3bf7ec8a6c88780e3c0693810488e3b9db2b09db478d83568b326da04579f8b` |
| `docs/decisions/adr/adr-022-operational-access-oidc.md` | `a81b774cea28468848fe065c318393267665856cfa29c3eb935cdd04250cf1b4` |
| `docs/decisions/adr/adr-023-users-physical-modeling.md` | `da25a5288557267c4f18760d4519aa72d5c52fe295083c127c1b14e6d1ff9717` |
| `docs/decisions/adr/adr-024-first-admin-bootstrap-execution-protocol.md` | `7bd59dce435ce826ec6231347329079aa786b12d1b975710e155f4c5aa5b7303` |
| `docs/decisions/decision-register.md` | `627116e6dc943901e2d47a61331975459ea8b1b901bf446a64da9fdd72b2e081` |
| `docs/decisions/pending-decisions.md` | `9a8524b823533c2c5186c91d7fae61375be0ba95995cb5cc7ecaf55b0c0cd22a` |
| `docs/operations/cognito-dynamodb-compensation.md` | `d2914292047679b7858e6b130f4baf04440913f9fb0809b243df22323d448807` |
| `docs/operations/first-admin-invitation-resume.md` | `33213a038e5f7400b09cb88cba7f19c75be248ac860b1bccd6af762153f6679a` |
| `docs/operations/non-http-idempotency.md` | `5fa1abb45fc5c5c06d75c1115a292662fc0ca402f0ad303b2e97ee4a8dad0804` |
| `docs/operations/rollback-strategy.md` | `0341e5837516cb745a42b76b57247e3ac3bb8e3afc02d6bce92c26ba4f606d91` |
| `docs/operations/sole-admin-mfa-recovery.md` | `30dce5d37c002be252e16509fd43afa0e26f38ad2e05453eb0656cee0ff24797` |
| `docs/overview.md` | `b2b59684b040212a5eceda06b9316d4897859f46273ddb82e2c419e1be96348d` |
| `docs/references.md` | `f86b0ea29df69ea0ba5e6bad78e6dc661cad6ee24dc45bcc63222fd6735ff236` |
| `docs/requirements/srs.md` | `01613134925ef8f3d584b612c7bb4b3a5746ca8992d9af0adfea7ba925eadb91` |
| `docs/serverless-student-manager-ordem-de-leitura.md` | `97faf4c85cb91f636e3e5b87e990c680428a2027b5fea6ce29404a0e3e23f123` |
| `docs/serverless-student-manager-ordem-de-leitura.png` | `0243000a218ca8860a10c45b0eeb21a02195664f9c4da1eacb1f8abf9ceed611` |
