# Manifesto do pacote canônico v3.1 — OpenAPI API Contract

**Projeto:** Serverless Student Manager
**Versão:** 3.1
**Data:** 2026-10-06
**Arquivos listados:** 67

O próprio `MANIFEST.md` não é listado para evitar hash autorreferencial.

## Arquivos e SHA-256

| Arquivo | SHA-256 |
|---|---|
| `AGENTS.md` | `19dd81e60bef77ea3460870de32560a07094f8a23d35c1f158dba0b4bf6bdf78` |
| `CLAUDE.md` | `8d0c661384c9b8c101c9a64e688576ad6a08ac187c984d0ff114ca44cf410260` |
| `RESTORE-INSTRUCTIONS.md` | `9f7d55d96f112e2bb50f73995f2ca42fbb5a4bbb5ba4b32fb54ba2beb6438e8d` |
| `docs/AUDIT-REPORT.md` | `60eb194a127c553fcf6b9ebe991ab8ba403deebeead4bd49c284b00794e7e13f` |
| `docs/DOCUMENTATION-VERSION.md` | `172235ffbd0a4b15c3b2d4534de1f7b3a3c430c3830ad7be7203c535832e3103` |
| `docs/ENGINEERING-READINESS.md` | `1a890640dbd850a116d57311e9afc5b2197b0b3c1bd6b6f8e30bfab90ebac36a` |
| `docs/FRONTEND-MILESTONE-CLOSURE.md` | `906ee878757b087e3458460194ad5cc9516d7c654eb53b43d022af47c4330984` |
| `docs/README.md` | `9e81f5777f2e6396d5ef43850b82a9e98a1bb4d929248ff4cd07816f5ae6b856` |
| `docs/api/openapi.yaml` | `13606d5b04b60c6821cce607d945a9b9f8d582cf6b22485817514b927c472989` |
| `docs/architecture/architecture-overview.md` | `2d07a3425ba5896f04bd570fcd3ca6050e0492f1693e0a0e0eb640ccf382fefb` |
| `docs/architecture/data-model.md` | `d1ad9aad9f8a6f2fc9370023f125f85f3861a96532e578324ce85da26232c9b1` |
| `docs/architecture/deployment-and-cicd.md` | `5a34bde2310a274fb62557a007695bddb8f73fe9a65b9ad6681fde6df3358b21` |
| `docs/architecture/diagrams.md` | `c6d18b9af0cb28f495bb1e86fb785b73da81a63cf508a13716dd9d706b1965cc` |
| `docs/architecture/observability.md` | `164ea0d7a1c1a0e4005f58c6cb7d68e175b39d3b0f1d7bb65ad5c94f6f143f0b` |
| `docs/architecture/security.md` | `afa0ce38f52e6981d24835d0bfb24a2970a33e6baf4f34e3cca10fd329d1a0f1` |
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
| `docs/decisions/adr/adr-013-first-admin-bootstrap.md` | `4f129f1837c28ccae41cffb7df1665619d86973f7fa12890fe1cd3443526e89f` |
| `docs/decisions/adr/adr-014-mfa-security.md` | `49359c2703cf130dac2ff4cd6a3c06c35d324232714a5433e91e8d9fd820dcc9` |
| `docs/decisions/adr/adr-015-audit-retention.md` | `e73a542d56837a33aeba8521589440a682958ede6a7a89547fe14991bdff2da5` |
| `docs/decisions/adr/adr-016-terraform-modules.md` | `0ae86449cb73fca06892d59997384bda87e0e42b77a11d2382baddfa2acce0ee` |
| `docs/decisions/adr/adr-017-cognito-dynamodb-provisioning-consistency.md` | `356714683949e3f2724be610275cf38150fef43225c8ac81fe5fcdade91d0cc9` |
| `docs/decisions/adr/adr-018-non-http-idempotency.md` | `9fcff471f17fcea774976555931b3bb7c281af3201565560002ba046d8ab6e6a` |
| `docs/decisions/adr/adr-019-sole-admin-mfa-recovery.md` | `dd9eb396e14d3d6cf35834d96649babec9bf428bbfa28c2835efdba345ba4530` |
| `docs/decisions/adr/adr-020-rollback-strategy.md` | `8c8cfb74f59359e7c110ec6f5c481b31bef1aeb75c9598a8751254404a3dfc06` |
| `docs/decisions/adr/adr-021-audit-index-modeling.md` | `d3bf7ec8a6c88780e3c0693810488e3b9db2b09db478d83568b326da04579f8b` |
| `docs/decisions/adr/adr-022-operational-access-oidc.md` | `084f4c34d6885153bd518bc9d998d8612f6e0519ee11603bfddc7e469236afe1` |
| `docs/decisions/adr/adr-023-users-physical-modeling.md` | `da25a5288557267c4f18760d4519aa72d5c52fe295083c127c1b14e6d1ff9717` |
| `docs/decisions/adr/adr-024-first-admin-bootstrap-execution-protocol.md` | `f165561261adbf0501450e45140f81382bc73376c6687e233ccac9cf5a7eb39e` |
| `docs/decisions/adr/adr-025-first-admin-email-verification.md` | `6b2ac96d0b24bf103504e73e28f17b81e19d6d5a8725c428ee67679816d768a4` |
| `docs/decisions/adr/adr-026-students-list-contract-and-physical-modeling.md` | `3dbe8ab825c20a4e005e011ac3f1633b458411f70619d5832a7f7e139757e3fa` |
| `docs/decisions/adr/adr-027-user-activation-after-first-sign-in.md` | `19096d119afc6d4258aab6941ea1b14c7dece26a55c18428480eadb99973d4f5` |
| `docs/decisions/adr/adr-028-lambda-application-release-via-github-actions.md` | `dec580a6979c144ee660af14e33a182e75431f386931dea5682a12a5cabd0924` |
| `docs/decisions/adr/adr-029-self-profile-resolution.md` | `a265176f4c28d21541b326d6dc9904856082206bddf4030ff520c43ab373769f` |
| `docs/decisions/adr/adr-030-student-creation.md` | `a8038803c0baf6b56f4e01eb0e7592fb4907af0b53916aaa057f375bfad56891` |
| `docs/decisions/decision-register.md` | `b86c3c9f05ee4b42f93e31438d757b5250a20145e79171bd282af5feac897f06` |
| `docs/decisions/pending-decisions.md` | `3877f4dcdb6bfd6d367696e0b3b473bbf10c78bf9c81ee357c35b05375e5daea` |
| `docs/operations/cognito-dynamodb-compensation.md` | `d2914292047679b7858e6b130f4baf04440913f9fb0809b243df22323d448807` |
| `docs/operations/agentic-development-harness-local.md` | `ed86ef0cf28c3365052a8040e088eaa78b5b7a837bdd32ef0ca17b57def55f76` |
| `docs/operations/first-admin-email-verification.md` | `f067eb2b1bbea6d453d542b67fbf6d9d8a86504c2c293f5e035786518480150d` |
| `docs/operations/first-admin-invitation-resume.md` | `33213a038e5f7400b09cb88cba7f19c75be248ac860b1bccd6af762153f6679a` |
| `docs/operations/non-http-idempotency.md` | `3734ceb6968b2c6ee998bcfbb690bb3899c5dd86551a309b05b21b72bb4d6a96` |
| `docs/operations/rollback-strategy.md` | `0341e5837516cb745a42b76b57247e3ac3bb8e3afc02d6bce92c26ba4f606d91` |
| `docs/operations/sole-admin-mfa-recovery.md` | `30dce5d37c002be252e16509fd43afa0e26f38ad2e05453eb0656cee0ff24797` |
| `docs/overview.md` | `99c0311d0a7f4993b3bf5e715e3da7e455b20959dc33d0e1d8f6968ca7e29e97` |
| `docs/references.md` | `f86b0ea29df69ea0ba5e6bad78e6dc661cad6ee24dc45bcc63222fd6735ff236` |
| `docs/requirements/srs.md` | `f9382e5a292d585d4703f2b335aa56c809506db096b7268ddede95a01217f96e` |
| `docs/serverless-student-manager-ordem-de-leitura.md` | `81f5f9edc80aa7addee803f0b580080ae418f775a52eccf4faf176066220002d` |
| `docs/serverless-student-manager-ordem-de-leitura.png` | `0243000a218ca8860a10c45b0eeb21a02195664f9c4da1eacb1f8abf9ceed611` |
| `docs/decisions/adr/adr-031-agentic-development-harness.md` | `6d0215e41b58547365c7ceb7dd0c9724f1c28f71a9ac43ded7ecb0cbec7e0e5a` |
| `docs/operations/agentic-development-harness-v1.md` | `835bdc169af5e0076f9618aa38e21129ff0a25cce7c5d14ec609ddbe5fbd6bb5` |
| `docs/decisions/adr/adr-032-student-update.md` | `f07e204c9bcd405493b24bfe54fba5415eefe877fbbcdc9034c7a2d340c6ae99` |
| `docs/decisions/adr/adr-033-student-lifecycle.md` | `05388a5d59a66996468b049b3acecfc3596885c776e9d42672d2d20dc454ab0d` |
| `docs/decisions/adr/adr-034-student-physical-deletion-policy.md` | `5158870d552c0a1d87cd59dfc33d7daf1c861c2e881777a1b2d105a031cb2c02` |
| `docs/decisions/adr/adr-035-administrative-user-management.md` | `04f467c41c3c242d7ef8f29bedd62c8b663752158f60bf81e635f78c18ecee49` |
| `docs/decisions/adr/adr-036-student-registration-lookup-contract.md` | `0ebb2f77667768d9d26c383870924ed74a6dcf681f70d5a77aac36e95f22945a` |
| `docs/decisions/adr/adr-037-audit-query-api-contract.md` | `97d700757d60f1493736115cbb0c62d464c83b1828d8f6181f9620f031f8f9b4` |
