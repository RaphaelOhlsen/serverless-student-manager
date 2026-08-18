# Manifesto do pacote canônico v2.5 — Engineering Ready

**Projeto:** Serverless Student Manager
**Versão:** 2.5
**Data:** 2026-08-18
**Arquivos listados:** 45

O próprio `MANIFEST.md` não é listado para evitar hash autorreferencial.

## Arquivos e SHA-256

| Arquivo | SHA-256 |
|---|---|
| `AGENTS.md` | `a0c5f88b03e9c57dcc9302b2491063a12ec5190c901e6629c6ff037420fe889f` |
| `RESTORE-INSTRUCTIONS.md` | `9f7d55d96f112e2bb50f73995f2ca42fbb5a4bbb5ba4b32fb54ba2beb6438e8d` |
| `docs/AUDIT-REPORT.md` | `60eb194a127c553fcf6b9ebe991ab8ba403deebeead4bd49c284b00794e7e13f` |
| `docs/DOCUMENTATION-VERSION.md` | `f1851a0775c56c2202444f4053a7d68f68afec95e8f4bc92ae04c297f432e87b` |
| `docs/ENGINEERING-READINESS.md` | `1a890640dbd850a116d57311e9afc5b2197b0b3c1bd6b6f8e30bfab90ebac36a` |
| `docs/README.md` | `c18f85e45aa60a65e89b06a3cd960d50e35ac6436767bd9b55452de577d625f4` |
| `docs/architecture/architecture-overview.md` | `668042cbaeed9e0635b167d85b075ab46d5e2b028455fd9db1a8291a27072f8b` |
| `docs/architecture/data-model.md` | `ed9437164f72434f62aa412ee06ffe92204c4788bf3a07ee5ff3837a9be9a7f6` |
| `docs/architecture/deployment-and-cicd.md` | `9cc46fd5a2f91e2fb1f4049a4f5798b2a5dca845110774d4fec8056ff004ec6b` |
| `docs/architecture/diagrams.md` | `c6d18b9af0cb28f495bb1e86fb785b73da81a63cf508a13716dd9d706b1965cc` |
| `docs/architecture/observability.md` | `69c77f8e7fb86c8226d5c197abbf42f45b26ee426695e5e489a177e65f04dd81` |
| `docs/architecture/security.md` | `2b3dfbe0e71666072979f3683717e51bb3391db8668fa1f92cf01ed069a2f531` |
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
| `docs/decisions/adr/adr-013-first-admin-bootstrap.md` | `6879b5a3546e8bd05caed2adbac1f56816dea126a254ae98c127487fc82d28f2` |
| `docs/decisions/adr/adr-014-mfa-security.md` | `49359c2703cf130dac2ff4cd6a3c06c35d324232714a5433e91e8d9fd820dcc9` |
| `docs/decisions/adr/adr-015-audit-retention.md` | `e73a542d56837a33aeba8521589440a682958ede6a7a89547fe14991bdff2da5` |
| `docs/decisions/adr/adr-016-terraform-modules.md` | `0ae86449cb73fca06892d59997384bda87e0e42b77a11d2382baddfa2acce0ee` |
| `docs/decisions/adr/adr-017-cognito-dynamodb-provisioning-consistency.md` | `043e5ed0be0089f39725d542618f7f1aad512c2b6a78c4698bcf719841963448` |
| `docs/decisions/adr/adr-018-non-http-idempotency.md` | `458fafc994095893f76ed5e7e40fc193283467e1e93e6b8ce97eb17767403b09` |
| `docs/decisions/adr/adr-019-sole-admin-mfa-recovery.md` | `dd9eb396e14d3d6cf35834d96649babec9bf428bbfa28c2835efdba345ba4530` |
| `docs/decisions/adr/adr-020-rollback-strategy.md` | `8c8cfb74f59359e7c110ec6f5c481b31bef1aeb75c9598a8751254404a3dfc06` |
| `docs/decisions/adr/adr-021-audit-index-modeling.md` | `d97bd71d84623307fe7e07a8c94885dc91d420fd4674c984ea95892318064b14` |
| `docs/decisions/adr/adr-022-operational-access-oidc.md` | `a81b774cea28468848fe065c318393267665856cfa29c3eb935cdd04250cf1b4` |
| `docs/decisions/decision-register.md` | `8257fb1536138dbacf5a3de5cc64a2d97f0a6633f4d07d1fa2c6521336801866` |
| `docs/decisions/pending-decisions.md` | `a0c1533402899a6fead4b2ce61289e7301edb1c097dbab8744b5bac1bb4ac148` |
| `docs/operations/cognito-dynamodb-compensation.md` | `572a0a0c6cb16fe49e7f580fca3ebcb7d4e1b058e7af12c0bc0de260e2d67a86` |
| `docs/operations/non-http-idempotency.md` | `76799bc79a021a8a5ce765dfa582882eaacade211dbcc0f17749472be2ad362c` |
| `docs/operations/rollback-strategy.md` | `0341e5837516cb745a42b76b57247e3ac3bb8e3afc02d6bce92c26ba4f606d91` |
| `docs/operations/sole-admin-mfa-recovery.md` | `30dce5d37c002be252e16509fd43afa0e26f38ad2e05453eb0656cee0ff24797` |
| `docs/overview.md` | `1ac172dc7c231de60ae56d68d0e75fdb51c42509f0cb26435e379afef85d4fc4` |
| `docs/references.md` | `f86b0ea29df69ea0ba5e6bad78e6dc661cad6ee24dc45bcc63222fd6735ff236` |
| `docs/requirements/srs.md` | `01613134925ef8f3d584b612c7bb4b3a5746ca8992d9af0adfea7ba925eadb91` |
| `docs/serverless-student-manager-ordem-de-leitura.md` | `a913f4a72596ed21ce8b2e3c0d8156d2824e266235658ffaabf78b1d5c2ec402` |
| `docs/serverless-student-manager-ordem-de-leitura.png` | `0243000a218ca8860a10c45b0eeb21a02195664f9c4da1eacb1f8abf9ceed611` |
