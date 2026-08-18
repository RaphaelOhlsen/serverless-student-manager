# Manifesto do pacote canônico v2.4 — Engineering Ready

**Projeto:** Serverless Student Manager
**Versão:** 2.4
**Data:** 2026-08-18
**Arquivos listados:** 44

O próprio `MANIFEST.md` não é listado para evitar hash autorreferencial.

## Arquivos e SHA-256

| Arquivo | SHA-256 |
|---|---|
| `AGENTS.md` | `4486e02db8557bd380957a1ca3e1576d0cb457554b6959388a74b8cb79438e4e` |
| `RESTORE-INSTRUCTIONS.md` | `9f7d55d96f112e2bb50f73995f2ca42fbb5a4bbb5ba4b32fb54ba2beb6438e8d` |
| `docs/AUDIT-REPORT.md` | `60eb194a127c553fcf6b9ebe991ab8ba403deebeead4bd49c284b00794e7e13f` |
| `docs/DOCUMENTATION-VERSION.md` | `966dc9429600918299e71fa5e0655c3de68eaf112955aed3291e960d8c1e6161` |
| `docs/ENGINEERING-READINESS.md` | `1a890640dbd850a116d57311e9afc5b2197b0b3c1bd6b6f8e30bfab90ebac36a` |
| `docs/README.md` | `bfa57e7f5dffb0514746d0b977752d7e1e276f2e277c88e786ee7dd913933b48` |
| `docs/architecture/architecture-overview.md` | `83f1532d29afe2c751d7295aac75b163a38e296b7ffa6d2b5ebd5188ba88342e` |
| `docs/architecture/data-model.md` | `66a43cdc7790c856f342d403c1904949f355ad72c0f8a3f63d1cee9deadf593f` |
| `docs/architecture/deployment-and-cicd.md` | `7b4d51418186cade574ccf89a13b2c2de6b54e97d153ca6f182c7fe2f6d74b2f` |
| `docs/architecture/diagrams.md` | `c6d18b9af0cb28f495bb1e86fb785b73da81a63cf508a13716dd9d706b1965cc` |
| `docs/architecture/observability.md` | `fa2442b24a1b5012f87a354c1f26688014ac259699aba32672ddb7f42a671dd8` |
| `docs/architecture/security.md` | `398e8c5c3616bd548bb7aa270cbf04f6c2554f95d00c58c18ab5b4cc245b087d` |
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
| `docs/decisions/decision-register.md` | `a1cffdbcbfc9469971cb52d68c9c37e5988c123b4191f4362e952a421a53f1d8` |
| `docs/decisions/pending-decisions.md` | `5f3c3e32abb68a94c9f0e017e3d8767e6dc90df30b1b9ae95d727b58dca1bc16` |
| `docs/operations/cognito-dynamodb-compensation.md` | `572a0a0c6cb16fe49e7f580fca3ebcb7d4e1b058e7af12c0bc0de260e2d67a86` |
| `docs/operations/non-http-idempotency.md` | `76799bc79a021a8a5ce765dfa582882eaacade211dbcc0f17749472be2ad362c` |
| `docs/operations/rollback-strategy.md` | `0341e5837516cb745a42b76b57247e3ac3bb8e3afc02d6bce92c26ba4f606d91` |
| `docs/operations/sole-admin-mfa-recovery.md` | `30dce5d37c002be252e16509fd43afa0e26f38ad2e05453eb0656cee0ff24797` |
| `docs/overview.md` | `b0bb212f5ec37e7539c5752200ae9baa489b3d2046055175176fe1a25d2602b0` |
| `docs/references.md` | `f86b0ea29df69ea0ba5e6bad78e6dc661cad6ee24dc45bcc63222fd6735ff236` |
| `docs/requirements/srs.md` | `01613134925ef8f3d584b612c7bb4b3a5746ca8992d9af0adfea7ba925eadb91` |
| `docs/serverless-student-manager-ordem-de-leitura.md` | `aef5f4522d0e8fe81650828017ee983ca91640d777a404e2b368e3bfda0af90e` |
| `docs/serverless-student-manager-ordem-de-leitura.png` | `0243000a218ca8860a10c45b0eeb21a02195664f9c4da1eacb1f8abf9ceed611` |
