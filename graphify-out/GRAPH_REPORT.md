# Graph Report - serverless-student-manager  (2026-09-24)

## Corpus Check
- 343 files · ~203,443 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 30 file(s) not represented in the graph (top: (none) 21, .example 5, .css 2)

## Summary
- 4068 nodes · 11514 edges · 198 communities (145 shown, 53 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 1114 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `84b61fef`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- bootstrap_admin/tests/test_service.py
- verify_first_admin_email/tests/test_service.py
- users_api/validation.py
- test_user_provisioning_service.py
- test_activation_service.py
- CreateUserService
- test_create_user_routes.py
- bootstrap_admin/tests/test_idempotency.py
- DeactivationService
- students_api/cursor.py
- release
- test_handler_get_student.py
- users_api/dependencies.py
- api.ts
- test_resume_service.py
- admin_user_service.py
- InvitationSagaInvariantError
- CreateStudentService
- test_invitation_saga.py
- cli.py
- frontend/package.json
- bootstrap/main.tf
- ProvisioningRepository
- CognitoRepository
- test_cli.py
- typing
- SelfProfileService
- students_api/validation.py
- test_role_change_service.py
- AuthorizationService
- test_resend_invitation_service.py
- verify_first_admin_email/service.py
- CognitoRepository
- test_user_repository.py
- UpdateStudentIdempotency
- test_create_student_service.py
- students_api/errors.py
- FirstAdminBootstrapService
- test_resume_discovery.py
- test_update_repository.py
- AdminUserService
- aws_lambda_function.this
- unit/test_idempotency.py
- students.py
- resume_discovery.py
- aws_apigatewayv2_api.this
- bootstrap_admin/service.py
- StudentLifecycleIdempotency
- test_agentic_scripts.py
- test_student_lifecycle_service.py
- test_cognito_create_repository.py
- package.json
- dev/locals.tf
- test_discovery.py
- Canonical Reading Order
- StudentRepository
- UpdateIdempotencyRecord
- test_lifecycle_repository.py
- users_api/errors.py
- App.test.tsx
- agentic-common.sh
- ReactivationService
- UserRepository
- test_deactivation_routes.py
- OperationalErrorDetails
- components.json
- StagingCheckTests
- discovery.py
- dev/outputs.tf
- compilerOptions
- InvalidStudentLifecycleRequestError
- FakeCognitoClient
- Saga Cognito, DynamoDB e convite
- EditStudentForm.tsx
- ScopeCheckTests
- test_reactivation_routes.py
- CognitoRepository
- dev/main.tf
- VerifyFirstAdminEmailService
- test_role_change_routes.py
- SagaRepositoryProtocol
- App
- CreateStudentForm.tsx
- test_resume_context.py
- CreateSagaState
- parse_verify_first_admin_email_context
- test_repositories.py
- devDependencies
- compilerOptions
- ResumeInvitationService
- IdempotencyRepository
- AuditRepository
- ActivationService
- operational_access/variables.tf
- user_repository.py
- FakeCognitoClient
- ResendInvitationService
- UserRepositoryProtocol
- test_lifecycle_routes.py
- dependencies
- Any
- FakeCognitoReader
- users_api/app.py
- test_self_profile_routes.py
- PreflightTests
- Any
- FakeCognitoReader
- dev/variables.tf
- test_update_routes.py
- user_provisioning.py
- pytest
- TemporaryGitRepository
- main.tsx
- DynamoDBClient
- CognitoClient
- CognitoIdentityEvidence
- Architecture Documentation
- Frontend Icon Sprite
- IdempotencyTable
- bootstrap_admin/idempotency_repository.py
- DynamoDBTable
- scripts
- test_routes.py
- DynamoDBClient
- test_resend_invitation_routes.py
- conditional_error
- Vite Logo
- tsconfig.json
- Graphify
- get_aws_error_code
- Layered Platform Illustration
- SourceTreeTests
- test_cognito_reactivation_repository.py
- aws_dynamodb_table.this
- Non-HTTP Idempotency
- Purple Lightning Bolt Favicon
- React Logo
- vite-env.d.ts
- aws_cognito_user_pool.this
- FakeIdGenerator
- Backend CI
- Documental Audit v2.3
- Lambda Release via GitHub Actions
- Cognito DynamoDB Compensation
- Frontend Application Entry Document
- bootstrap_admin/__init__.py
- tools/__init__.py
- lambda_release/__init__.py
- Dev e prod isolados na mesma conta AWS
- Estado remoto S3 separado por ambiente
- Observabilidade estruturada no CloudWatch
- ResumeInvitationServiceConfig
- Terraform Bootstrap
- Bootstrap Admin Dependencies
- Students API Release Dependencies
- Users API Release Dependencies
- test_admin_user_routes.py
- aws_dynamodb_table.this
- lambda_handler
- bootstrap_admin/tests/test_context.py
- aws_dynamodb_table.this
- aws_dynamodb_table.this
- DynamoDBClient
- test_health.py
- LifecycleIdempotencyRecord
- .update_item
- FakeClock
- .__init__
- graphify reference: extra exports and benchmark
- Restauração da documentação canônica v2.3 — Engineering Ready
- graphify reference: add a URL and watch a folder
- graphify reference: commit hook and native CLAUDE.md integration
- graphify reference: GitHub clone and cross-repo merge
- graphify reference: transcribe video and audio
- extraction-spec.md
- bootstrap/.terraform.lock.hcl
- dev/.terraform.lock.hcl
- IdempotencyClient
- service_models.py

## God Nodes (most connected - your core abstractions)
1. `InvitationSagaInvariantError` - 103 edges
2. `_build_service()` - 77 edges
3. `_existing_record()` - 66 edges
4. `InvitationSagaRepository` - 60 edges
5. `UserRepository` - 55 edges
6. `ReactivationService` - 50 edges
7. `DeactivationService` - 46 edges
8. `AwsStyleError` - 44 edges
9. `CreateSagaState` - 43 edges
10. `CognitoRepository` - 42 edges

## Surprising Connections (you probably didn't know these)
- `get_aws_error_code()` --indirect_call--> `response()`  [INFERRED]
  tools/bootstrap_admin/aws_errors.py → backend/students-api/tests/unit/test_lifecycle_repository.py
- `is_ambiguous_dynamodb_write_error()` --indirect_call--> `response()`  [INFERRED]
  tools/bootstrap_admin/aws_errors.py → backend/students-api/tests/unit/test_lifecycle_repository.py
- `_response_mapping()` --indirect_call--> `response()`  [INFERRED]
  tools/bootstrap_admin/operational_error.py → backend/students-api/tests/unit/test_lifecycle_repository.py
- `Terraform CI` --implements--> `Approved Serverless Architecture`  [INFERRED]
  .github/workflows/terraform-ci.yml → AGENTS.md
- `POST /users/me/activation` --implements--> `Security Architecture`  [INFERRED]
  backend/users-api/template.local.yaml → docs/architecture/security.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Canonical Documentation Reading Sequence** — docs_serverless_student_manager_ordem_de_leitura_governance, docs_serverless_student_manager_ordem_de_leitura_requirements, docs_serverless_student_manager_ordem_de_leitura_decisions, docs_serverless_student_manager_ordem_de_leitura_architecture, docs_serverless_student_manager_ordem_de_leitura_operations, docs_serverless_student_manager_ordem_de_leitura_audit [EXTRACTED 1.00]
- **Deploy, validação e recuperação** — docs_decisions_adr_adr_009_cicd_oidc_decision, docs_decisions_adr_adr_011_testing_strategy_decision, docs_decisions_adr_adr_020_rollback_strategy_decision [EXTRACTED 1.00]
- **Ciclo de vida da identidade do primeiro Administrador** — docs_decisions_adr_adr_013_first_admin_bootstrap_decision, docs_decisions_adr_adr_017_cognito_dynamodb_provisioning_consistency_decision, docs_decisions_adr_adr_019_sole_admin_mfa_recovery_decision, docs_decisions_adr_adr_023_users_physical_modeling_decision, docs_decisions_adr_adr_024_first_admin_bootstrap_execution_protocol_decision, docs_decisions_adr_adr_025_first_admin_email_verification_decision [EXTRACTED 1.00]
- **Arquitetura de idempotência HTTP e não HTTP** — docs_decisions_adr_adr_012_idempotency_decision, docs_decisions_adr_adr_018_non_http_idempotency_decision, docs_decisions_adr_adr_024_first_admin_bootstrap_execution_protocol_decision, docs_decisions_adr_adr_025_first_admin_email_verification_decision [EXTRACTED 1.00]
- **Delivery Quality Pipeline** — _github_workflows_backend_ci_backend_ci, _github_workflows_lambda_release_lambda_application_release, _github_workflows_terraform_ci_terraform_ci [INFERRED 0.85]
- **Canonical Documentation Governance** — docs_readme_canonical_documentation, docs_documentation_version_canonical_documentation_version, docs_manifest_canonical_package_manifest, docs_serverless_student_manager_ordem_de_leitura_canonical_reading_order, docs_decisions_decision_register_decision_register [INFERRED 0.95]
- **First Administrator Operations** — docs_operations_first_admin_email_verification_first_admin_email_verification, docs_operations_first_admin_invitation_resume_first_admin_invitation_resume, docs_operations_sole_admin_mfa_recovery_sole_admin_mfa_recovery, docs_operations_non_http_idempotency_non_http_idempotency [INFERRED 0.95]
- **Frontend Social Platform Icons** — frontend_public_icons_bluesky_icon, frontend_public_icons_discord_icon, frontend_public_icons_github_icon, frontend_public_icons_x_icon [INFERRED 0.95]
- **Serverless Architecture Views** — docs_overview_serverless_student_manager, docs_architecture_architecture_overview_architecture_overview, docs_architecture_data_model_data_model, docs_architecture_security_security_architecture, docs_architecture_observability_observability [INFERRED 0.95]
- **Student Domain Decisions** — docs_decisions_adr_adr_030_student_creation_student_creation, docs_decisions_adr_adr_032_student_update_student_update, docs_decisions_adr_adr_033_student_lifecycle_student_lifecycle, docs_decisions_adr_adr_034_student_physical_deletion_policy_student_physical_deletion_policy [INFERRED 0.95]
- **Vite Logo Visual System** — frontend_src_assets_vite_lightning_bolt_mark, frontend_src_assets_vite_parenthesis_frame, frontend_src_assets_vite_adaptive_color_scheme, frontend_src_assets_vite_vite_brand_identity [INFERRED 0.95]

## Communities (198 total, 53 thin omitted)

### Community 0 - "bootstrap_admin/tests/test_service.py"
Cohesion: 0.06
Nodes (96): ExpectedProvisioningItems, ProvisioningItems, OperationalError, RuntimeError, _assert_started_replay_completed(), _assert_started_replay_has_no_downstream_effects(), AwsStyleError, _build_service() (+88 more)

### Community 1 - "verify_first_admin_email/tests/test_service.py"
Cohesion: 0.10
Nodes (62): ReadTimeoutError, audit_event_matches(), build_first_admin_email_verification_audit_event(), VerifyFirstAdminEmailAuditResult, VerifyFirstAdminEmailDiscoveryResult, _event(), parametrize, VerifyFirstAdminEmailAuditResult (+54 more)

### Community 2 - "users_api/validation.py"
Cohesion: 0.08
Nodes (45): InvalidActivationRequestError, InvalidAdminUserWriteRequestError, ValueError, DeactivationInput, _is_control(), normalize_admin_user_email(), normalize_admin_user_full_name(), parse_create_user_body() (+37 more)

### Community 3 - "test_user_provisioning_service.py"
Cohesion: 0.06
Nodes (42): ReconciledCognitoIdentity, CognitoRepositoryProtocol, Protocol, CognitoRepositoryProtocol, Protocol, SagaRepositoryProtocol, UserRepositoryProtocol, CognitoCompensationProtocol (+34 more)

### Community 4 - "test_activation_service.py"
Cohesion: 0.10
Nodes (39): aws_lambda_powertools_shared_json_encoder, ActivationConflictError, ActivationForbiddenError, activate(), client_error(), ConcurrentCompletionIdempotency, DynamoCompletedIdempotency, FakeCognito (+31 more)

### Community 5 - "CreateUserService"
Cohesion: 0.16
Nodes (8): CreateUserService, ProvisioningServiceProtocol, ProvisioningResult, ProvisioningSnapshot, Exception, UserProvisioningService, UserProvisioningItems, CreateUserInput

### Community 6 - "test_create_user_routes.py"
Cohesion: 0.25
Nodes (13): event(), FakeContext, FakeCreateService, Any, Exception, MonkeyPatch, parametrize, resolve() (+5 more)

### Community 7 - "bootstrap_admin/tests/test_idempotency.py"
Cohesion: 0.08
Nodes (48): hashlib, _build_payload_hash(), build_started_record(), IdempotencyConflictError, is_valid_state_transition(), RuntimeError, validate_existing_record(), build_resume_invitation_started_record() (+40 more)

### Community 8 - "DeactivationService"
Cohesion: 0.08
Nodes (37): UserDeactivationReconciliationError, DeactivationDomainResult, DeactivationService, ClientError, DeactivationState, CognitoState, committed(), deactivate() (+29 more)

### Community 9 - "students_api/cursor.py"
Cohesion: 0.10
Nodes (31): CursorPosition, decode_cursor(), encode_cursor(), normalize_name(), Any, _unique_object(), _valid_normalized_name(), _valid_student_id() (+23 more)

### Community 10 - "release"
Cohesion: 0.13
Nodes (41): argparse, CommandRunner, SmokeRunner, time, _artifact_code_sha256(), aws_json(), main(), Any (+33 more)

### Community 11 - "test_handler_get_student.py"
Cohesion: 0.19
Nodes (12): lambda_handler(), Any, inject_lambda_context, LambdaContext, log_metrics, FakeLambdaContext, FakeStudentService, load_event() (+4 more)

### Community 12 - "users_api/dependencies.py"
Cohesion: 0.12
Nodes (40): get_audit_retention_days(), get_audit_table_name(), get_environment(), get_idempotency_table_name(), get_user_pool_id(), get_users_table_name(), _required(), get_activation_service() (+32 more)

### Community 13 - "api.ts"
Cohesion: 0.10
Nodes (39): handleActivation(), AuthView, isSuccessfulActivation(), nextStageContent, hasUnsafeControls(), Props, reasonError(), StudentLifecycleAction (+31 more)

### Community 14 - "test_resume_service.py"
Cohesion: 0.18
Nodes (38): ResumeDiscoveryStatus, AwsError, _discovery_result(), FakeDiscovery, FakeIdempotencyRepository, FakeInvitationSender, BaseException, parametrize (+30 more)

### Community 15 - "admin_user_service.py"
Cohesion: 0.16
Nodes (18): decode_cursor(), encode_cursor(), normalize_email(), normalize_name(), Any, _unique_object(), UserCursorPosition, _valid_normalized_name() (+10 more)

### Community 16 - "InvitationSagaInvariantError"
Cohesion: 0.13
Nodes (19): InvitationSagaConcurrentTransitionError, InvitationSagaInvariantError, InvitationSagaRepository, ClientError, UUID, create_request_hash(), deactivation_request_hash(), _hash() (+11 more)

### Community 17 - "CreateStudentService"
Cohesion: 0.12
Nodes (10): CreateAuthorizationProtocol, CreateStudentRepositoryProtocol, CreateStudentService, IdempotencyProtocol, Any, ClientError, datetime, Protocol (+2 more)

### Community 18 - "test_invitation_saga.py"
Cohesion: 0.14
Nodes (40): replay_from_record(), StoredReplay, claim_create(), FakeTable, ids(), UUID, repository(), test_active_create_claim_is_in_progress() (+32 more)

### Community 19 - "cli.py"
Cohesion: 0.12
Nodes (33): _aws_dependencies(), BootstrapService, _build_bootstrap_service(), _build_resume_service(), _build_verify_email_service(), _exit_code(), main(), Any (+25 more)

### Community 20 - "frontend/package.json"
Cohesion: 0.06
Nodes (36): eslint, @eslint/js, typescript, typescript-eslint, vitest, name, private, type (+28 more)

### Community 21 - "bootstrap/main.tf"
Cohesion: 0.07
Nodes (57): aws_iam_openid_connect_provider.github_actions, aws_iam_policy.terraform_state_dev, aws_iam_policy.terraform_state_prod, aws_iam_role.github_actions_dev_deployment, aws_iam_role.github_actions_prod_deployment, aws_iam_role_policy_attachment.terraform_state_dev, aws_iam_role_policy_attachment.terraform_state_prod, aws_iam_role_policy.lambda_application_release_dev (+49 more)

### Community 22 - "ProvisioningRepository"
Cohesion: 0.11
Nodes (21): ProvisioningRepository, _audit_event(), _bootstrap_marker(), _cognito_projection(), DynamoDBFailure, FailingDynamoDBClient, FakeDynamoDBClient, Any (+13 more)

### Community 23 - "CognitoRepository"
Cohesion: 0.15
Nodes (25): CognitoCreateResultError, CognitoIdentityValidationError, CognitoRepository, RuntimeError, FakeGetUserCognitoClient, parametrize, test_create_suppressed_user_uses_controlled_cognito_flow(), test_delete_user_sends_exact_cognito_arguments() (+17 more)

### Community 24 - "test_cli.py"
Cohesion: 0.09
Nodes (40): ArgumentParser, CaptureFixture, _bootstrap_output(), build_parser(), CliUsageError, ValueError, run(), _bootstrap_args() (+32 more)

### Community 25 - "typing"
Cohesion: 0.12
Nodes (22): AdminUserForbiddenError, AdminUserNotFoundError, LastActiveAdminConflictError, UserVersionConflictError, ClientError, RoleChangeService, RuntimeError, reconcile_user_state() (+14 more)

### Community 26 - "SelfProfileService"
Cohesion: 0.17
Nodes (12): SelfProfileForbiddenError, SelfProfileService, Protocol, UserStateRepositoryProtocol, FakeUsers, Any, parametrize, test_forbids_disallowed_role_or_status() (+4 more)

### Community 27 - "students_api/validation.py"
Cohesion: 0.16
Nodes (32): InvalidCreateStudentRequestError, InvalidUpdateStudentRequestError, Raised when a create-student request violates the public contract., Raised when a partial update request violates the public contract., _is_control(), _normalize_email(), _normalize_full_name(), parse_create_student_body() (+24 more)

### Community 28 - "test_role_change_service.py"
Cohesion: 0.14
Nodes (25): FakeSaga, FakeUsers, invoke(), profile(), ClientError, parametrize, service(), test_completed_replay_precedes_target_state_validation_and_has_no_mutation() (+17 more)

### Community 29 - "AuthorizationService"
Cohesion: 0.09
Nodes (36): AuthorizationService, Any, Protocol, UsersTable, ForbiddenError, Raised when the authenticated identity is not allowed to list students., normalize_dynamodb_value(), FakeUsersTable (+28 more)

### Community 30 - "test_resend_invitation_service.py"
Cohesion: 0.15
Nodes (20): ResendSagaState, FakeCognito, FakeSaga, FakeUsers, invoke(), make_service(), Exception, MonkeyPatch (+12 more)

### Community 31 - "verify_first_admin_email/service.py"
Cohesion: 0.08
Nodes (25): _as_utc(), Clock, format_utc_rfc3339_millis(), datetime, Protocol, SystemClock, to_epoch_seconds(), IdGenerator (+17 more)

### Community 32 - "CognitoRepository"
Cohesion: 0.15
Nodes (7): CognitoRepository, Exception, ReconciledCognitoDeactivationState, ReconciledCognitoReactivationState, Never, NoReturn, _SafeArgumentParser

### Community 33 - "test_user_repository.py"
Cohesion: 0.11
Nodes (35): Users API repositories., activate(), deserialized(), FakeClient, Any, ClientError, MonkeyPatch, parametrize (+27 more)

### Community 34 - "UpdateStudentIdempotency"
Cohesion: 0.17
Nodes (22): Acquire and resolve durable update-student idempotency records., UpdateStudentIdempotency, acquire(), Client, decode(), encode(), Any, parametrize (+14 more)

### Community 35 - "test_create_student_service.py"
Cohesion: 0.13
Nodes (17): build_service(), create(), FakeAuthorization, FakeRepository, PassthroughIdempotency, Any, ClientError, Exception (+9 more)

### Community 36 - "students_api/errors.py"
Cohesion: 0.06
Nodes (56): IdempotencyKeyReusedError, OperationInProgressError, Exception, RuntimeError, Raised when a student cannot be found., Raised when the normalized student email is reserved., Raised when registration number and email are both reserved., Raised when an idempotency key is reused with a different payload. (+48 more)

### Community 37 - "FirstAdminBootstrapService"
Cohesion: 0.26
Nodes (6): BootstrapTerminalState, BootstrapContext, FirstAdminBootstrapService, BootstrapResult, BaseException, Exception

### Community 38 - "test_resume_discovery.py"
Cohesion: 0.21
Nodes (23): ResumeInvitationDiscoveryConfig, _cognito_projection(), _discover(), _discovery(), FakeProvisioningReader, _marker(), BaseException, parametrize (+15 more)

### Community 39 - "test_update_repository.py"
Cohesion: 0.22
Nodes (16): Client, decode(), Any, Exception, parametrize, run(), Table, test_atomic_update() (+8 more)

### Community 40 - "AdminUserService"
Cohesion: 0.17
Nodes (15): AdminUserService, FakeRepository, profile(), parametrize, test_email_not_found_is_an_empty_result(), test_exact_email_search_uses_reservation_and_applies_filters(), test_filtered_pagination_continues_across_empty_intermediate_pages(), test_get_and_list_require_active_admin() (+7 more)

### Community 41 - "aws_lambda_function.this"
Cohesion: 0.12
Nodes (34): aws_cloudwatch_log_group.this, aws_iam_role_policy.additional, aws_iam_role_policy.logging, aws_iam_role.this, aws_lambda_alias.live, aws_lambda_function.this, data.aws_iam_policy_document.assume_role, data.aws_iam_policy_document.logging (+26 more)

### Community 42 - "unit/test_idempotency.py"
Cohesion: 0.15
Nodes (16): aws_lambda_powertools_utilities_idempotency, aws_lambda_powertools_utilities_idempotency_exceptions, aws_lambda_powertools_utilities_idempotency_persistence_datarecord, CreateStudentIdempotency, BasePersistenceLayer, data(), MemoryPersistence, Any (+8 more)

### Community 43 - "students.py"
Cohesion: 0.09
Nodes (51): aws_lambda_powertools_logging, aws_lambda_powertools_metrics, aws_lambda_powertools_utilities_typing, health(), get_audit_retention_days(), get_audit_table_name(), get_environment(), get_idempotency_table_name() (+43 more)

### Community 44 - "resume_discovery.py"
Cohesion: 0.12
Nodes (16): CognitoReader, FirstAdminInvitationTarget, _is_valid_cognito_projection(), _nonempty_string(), _parse_marker(), _parse_user_profile(), ProvisioningReader, FirstAdminStatus (+8 more)

### Community 45 - "aws_apigatewayv2_api.this"
Cohesion: 0.12
Nodes (32): aws_apigatewayv2_api.this, aws_apigatewayv2_authorizer.jwt, aws_apigatewayv2_integration.lambda, aws_apigatewayv2_route.this, aws_apigatewayv2_stage.default, aws_cloudwatch_log_group.access, aws_lambda_permission.api_gateway, Terraform module: infra/modules/http_api (+24 more)

### Community 46 - "bootstrap_admin/service.py"
Cohesion: 0.17
Nodes (21): botocore_session, botocore_validate, build_user_created_audit_event(), build_cognito_projection(), build_first_admin_bootstrap_marker(), build_unique_email(), build_user_profile(), normalize_email() (+13 more)

### Community 47 - "StudentLifecycleIdempotency"
Cohesion: 0.22
Nodes (20): Durable idempotency for the two explicit student lifecycle operations., StudentLifecycleIdempotency, acquire(), Client, decode(), encode(), Any, LifecycleOperation (+12 more)

### Community 48 - "test_agentic_scripts.py"
Cohesion: 0.16
Nodes (17): os, pathlib, shutil, subprocess, sys, tempfile, build_artifact(), _is_included() (+9 more)

### Community 49 - "test_student_lifecycle_service.py"
Cohesion: 0.23
Nodes (19): Authorization, deactivate(), Idempotency, make_service(), Any, Exception, parametrize, reactivate() (+11 more)

### Community 50 - "test_cognito_create_repository.py"
Cohesion: 0.19
Nodes (19): client_error(), compatible_response(), FakeCognitoClient, Any, ClientError, Exception, parametrize, repository() (+11 more)

### Community 51 - "package.json"
Cohesion: 0.08
Nodes (25): devDependencies, eslint, @eslint/js, prettier, @redocly/cli, typescript, typescript-eslint, vitest (+17 more)

### Community 52 - "dev/locals.tf"
Cohesion: 0.12
Nodes (28): local.common_tags, local.environment, local.github_admin_recovery_subject, local.github_bootstrap_admin_subject, local.github_immutable_repository, local.github_oidc_provider_arn, local.github_owner, local.github_repository_name (+20 more)

### Community 53 - "test_discovery.py"
Cohesion: 0.19
Nodes (21): _discovery(), FakeProvisioningReader, _marker(), _projection(), BaseException, parametrize, test_compatible_user_statuses_are_reconciled(), test_confirmed_cognito_inconsistency_requires_reconciliation() (+13 more)

### Community 54 - "Canonical Reading Order"
Cohesion: 0.07
Nodes (43): Terraform CI, Agentic Development Harness v1, Approved Serverless Architecture, Serverless Student Manager Governance, Students API Runtime Dependencies, GET /health, Students API Local SAM Function, Users API Runtime Dependencies (+35 more)

### Community 55 - "StudentRepository"
Cohesion: 0.10
Nodes (15): DynamoDBClient, DynamoDBTable, Any, Protocol, Persist one effective change and its durable replay response atomically., StudentRepository, FakeDynamoDBClient, FakeDynamoDBTable (+7 more)

### Community 56 - "UpdateIdempotencyRecord"
Cohesion: 0.09
Nodes (29): UpdateIdempotencyRecord, UpdateTransactionContext, UpdateStudentServiceProtocol, Any, datetime, Exception, Protocol, UUID (+21 more)

### Community 57 - "test_lifecycle_repository.py"
Cohesion: 0.18
Nodes (17): Client, decode(), Any, ClientError, Exception, parametrize, response(), run() (+9 more)

### Community 58 - "users_api/errors.py"
Cohesion: 0.10
Nodes (31): aws_lambda_powertools, AdminUserDataInvariantError, CognitoAliasExistsError, CognitoCreateDeterministicError, CognitoIdentityInvariantError, CognitoInvitationDeliveryError, CognitoResultAmbiguousError, CognitoServiceError (+23 more)

### Community 59 - "App.test.tsx"
Cohesion: 0.09
Nodes (15): activeProfile, apiMocks, authMocks, invitedProfile, studentDetail, studentsPage, successfulActivation, body (+7 more)

### Community 60 - "agentic-common.sh"
Cohesion: 0.14
Nodes (21): GIT_OPTIONAL_LOCKS, LC_ALL, agentic-preflight.sh script, usage(), allowed_paths, GIT_OPTIONAL_LOCKS, LC_ALL, agentic-scope-check.sh script (+13 more)

### Community 61 - "ReactivationService"
Cohesion: 0.06
Nodes (40): UserReactivationReconciliationError, ReactivationState, CognitoRepositoryProtocol, Protocol, ReactivationService, ReactivationTarget, SagaRepositoryProtocol, UserRepositoryProtocol (+32 more)

### Community 63 - "test_deactivation_routes.py"
Cohesion: 0.20
Nodes (21): event(), FakeContext, FakeService, Any, Exception, MonkeyPatch, parametrize, resolve() (+13 more)

### Community 64 - "OperationalErrorDetails"
Cohesion: 0.18
Nodes (15): re, _cancellation_reason_codes(), _nested_string(), OperationalErrorDetails, BaseException, _response_mapping(), _sanitize_technical_value(), _client_error() (+7 more)

### Community 65 - "components.json"
Cohesion: 0.09
Nodes (21): aliases, components, hooks, lib, ui, utils, iconLibrary, menuAccent (+13 more)

### Community 67 - "discovery.py"
Cohesion: 0.14
Nodes (15): validate_uuid4(), parametrize, test_uuid4_generator_returns_canonical_lowercase_uuid4(), test_validate_uuid4_rejects_noncanonical_or_non_v4_values(), test_validate_uuid4_returns_valid_value_unchanged(), CognitoReader, FirstAdminEmailTarget, _is_valid_projection() (+7 more)

### Community 68 - "dev/outputs.tf"
Cohesion: 0.09
Nodes (30): module.http_api, module.student_store, module.students_api, output.audit_gsi_actor_time, output.audit_gsi_correlation_time, output.audit_gsi_period_time, output.audit_table_arn, output.audit_table_name (+22 more)

### Community 69 - "compilerOptions"
Cohesion: 0.10
Nodes (20): compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection (+12 more)

### Community 70 - "InvalidStudentLifecycleRequestError"
Cohesion: 0.16
Nodes (22): InvalidStudentLifecycleRequestError, Raised when a student lifecycle request violates the public contract., StudentLifecycleServiceProtocol, DeactivateStudentInput, _is_unsafe_reason_character(), parse_deactivate_student_body(), parse_reactivate_student_body(), ReactivateStudentInput (+14 more)

### Community 71 - "FakeCognitoClient"
Cohesion: 0.21
Nodes (12): client_error(), FakeCognitoClient, Any, ClientError, Exception, parametrize, repository(), test_deactivation_calls_use_only_pool_and_stable_username() (+4 more)

### Community 72 - "Saga Cognito, DynamoDB e convite"
Cohesion: 0.24
Nodes (20): Lambda por domínio, Tabela DynamoDB por domínio orientada por padrões de acesso, Projeção de autorização Cognito no DynamoDB, Deploy via GitHub Actions OIDC, Estratégia de testes em camadas, Idempotency-Key para escritas HTTP, Bootstrap controlado do primeiro Administrador, MFA TOTP obrigatório (+12 more)

### Community 73 - "EditStudentForm.tsx"
Cohesion: 0.20
Nodes (14): EditStudentForm(), submit(), mutableFields(), Props, mocks, student, submit(), updateRequest() (+6 more)

### Community 75 - "test_reactivation_routes.py"
Cohesion: 0.20
Nodes (15): event(), FakeContext, FakeService, Any, Exception, MonkeyPatch, parametrize, resolve() (+7 more)

### Community 76 - "CognitoRepository"
Cohesion: 0.11
Nodes (4): CognitoRepository, IdempotencyRepository, ProvisioningRepository, Protocol

### Community 77 - "dev/main.tf"
Cohesion: 0.58
Nodes (11): data.aws_iam_policy_document.admin_recovery, data.aws_iam_policy_document.bootstrap_admin, data.aws_iam_policy_document.resume_first_admin_invitation, data.aws_iam_policy_document.students_api, data.aws_iam_policy_document.users_api, data.aws_iam_policy_document.verify_first_admin_email, module.audit_store, module.idempotency_store (+3 more)

### Community 78 - "VerifyFirstAdminEmailService"
Cohesion: 0.28
Nodes (7): _verify_email_output(), VerifyFirstAdminEmailContext, BaseException, VerifyFirstAdminEmailAuditResult, VerifyFirstAdminEmailTerminalState, VerifyFirstAdminEmailResult, VerifyFirstAdminEmailService

### Community 79 - "test_role_change_routes.py"
Cohesion: 0.23
Nodes (17): event(), FakeContext, FakeService, Any, Exception, MonkeyPatch, parametrize, resolve() (+9 more)

### Community 80 - "SagaRepositoryProtocol"
Cohesion: 0.12
Nodes (4): CognitoRepositoryProtocol, Protocol, SagaRepositoryProtocol, UserRepositoryProtocol

### Community 81 - "App"
Cohesion: 0.19
Nodes (12): App(), beginEdit(), beginLifecycle(), clearPasswords(), clearTotpData(), handleConfirmNewPassword(), handleConfirmTotp(), handleSignIn() (+4 more)

### Community 82 - "CreateStudentForm.tsx"
Cohesion: 0.20
Nodes (16): CreateStudentForm(), submit(), empty, messageFor(), normalize(), Props, validate(), CreatedStudent (+8 more)

### Community 83 - "test_resume_context.py"
Cohesion: 0.29
Nodes (16): InvalidResumeInvitationRecordError, parse_resume_invitation_context(), ValueError, _required_integer(), _required_string(), _required_uuid(), _parse(), parametrize (+8 more)

### Community 84 - "CreateSagaState"
Cohesion: 0.12
Nodes (26): CreateSagaState, FakeCognitoCreate, FakeInvitations, FakeProvisioning, FakeSaga, FakeUsers, invoke(), make_service() (+18 more)

### Community 85 - "parse_verify_first_admin_email_context"
Cohesion: 0.34
Nodes (17): InvalidVerifyFirstAdminEmailRecordError, parse_verify_first_admin_email_context(), ValueError, _required_integer(), _required_string(), _required_utc_rfc3339_millis(), _required_uuid(), parametrize (+9 more)

### Community 86 - "test_repositories.py"
Cohesion: 0.19
Nodes (6): FakeCognitoClient, FakeTable, Any, test_cognito_repository_uses_same_pool_and_username(), test_idempotency_repository_normalizes_nested_dynamodb_numbers(), test_idempotency_repository_uses_conditional_state_changes()

### Community 87 - "devDependencies"
Cohesion: 0.12
Nodes (17): devDependencies, eslint, @eslint/js, eslint-plugin-react-hooks, eslint-plugin-react-refresh, globals, jsdom, @testing-library/dom (+9 more)

### Community 88 - "compilerOptions"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection, noEmit, noFallthroughCasesInSwitch (+8 more)

### Community 89 - "ResumeInvitationService"
Cohesion: 0.29
Nodes (7): ResumeInvitationTerminalState, _resume_output(), ResumeInvitationContext, BaseException, Exception, ResumeInvitationService, ResumeInvitationResult

### Community 90 - "IdempotencyRepository"
Cohesion: 0.26
Nodes (14): IdempotencyRepository, FailingUpdatableDynamoDBTable, FakeUpdatableDynamoDBTable, parametrize, test_bootstrap_cognito_created_requires_sub_before_update(), test_bootstrap_cognito_created_writes_sub_with_conditional_update(), test_create_started_record_uses_conditional_put(), test_get_existing_record_uses_strongly_consistent_read() (+6 more)

### Community 91 - "AuditRepository"
Cohesion: 0.23
Nodes (9): AuditRepository, _event(), FakeDynamoDBClient, Any, parametrize, test_get_audit_event_returns_none_when_missing(), test_get_audit_event_uses_exact_key_and_consistent_read(), test_put_audit_event_is_single_conditional_append_only_write() (+1 more)

### Community 93 - "operational_access/variables.tf"
Cohesion: 0.18
Nodes (18): aws_iam_policy.this, aws_iam_role_policy_attachment.this, aws_iam_role.this, data.aws_iam_policy_document.trust, output.policy_arn, output.policy_name, output.role_arn, output.role_name (+10 more)

### Community 94 - "user_repository.py"
Cohesion: 0.17
Nodes (5): normalize_dynamodb_value(), IdempotencyRepository, IdempotencyTable, Any, Protocol

### Community 95 - "FakeCognitoClient"
Cohesion: 0.16
Nodes (7): FakeCognitoClient, FakeCreateResponseCognitoClient, FakeUpdateUserAttributesCognitoClient, Any, Exception, test_create_suppressed_user_rejects_result_without_usable_sub(), test_set_email_verified_uses_only_authorized_cognito_mutation()

### Community 97 - "UserRepositoryProtocol"
Cohesion: 0.18
Nodes (3): Protocol, SagaRepositoryProtocol, UserRepositoryProtocol

### Community 98 - "test_lifecycle_routes.py"
Cohesion: 0.35
Nodes (9): event(), LifecycleService, Any, Exception, parametrize, resolve(), test_lifecycle_route_returns_public_student_and_delegates(), test_lifecycle_routes_map_errors_without_leaking_details() (+1 more)

### Community 99 - "dependencies"
Cohesion: 0.14
Nodes (14): dependencies, aws-amplify, @base-ui/react, class-variance-authority, clsx, @fontsource-variable/geist, lucide-react, react (+6 more)

### Community 100 - "Any"
Cohesion: 0.20
Nodes (3): FakeDynamoDBTable, FakeReadableDynamoDBTable, Any

### Community 101 - "FakeCognitoReader"
Cohesion: 0.18
Nodes (4): AwsError, FakeCognitoReader, NoReturn, RuntimeError

### Community 102 - "users_api/app.py"
Cohesion: 0.12
Nodes (23): aws_lambda_powertools_event_handler, get_self_profile_service(), ActivationUnauthorizedError, SelfProfileUnauthorizedError, ActivationServiceProtocol, _error_response(), _is_canonical_uuid(), _parse_request() (+15 more)

### Community 103 - "test_self_profile_routes.py"
Cohesion: 0.35
Nodes (10): event(), FakeService, Any, Exception, parametrize, resolve(), test_rejects_body_or_query_parameters(), test_returns_exact_contract_using_only_authenticated_subject() (+2 more)

### Community 105 - "Any"
Cohesion: 0.19
Nodes (5): CognitoClient, CognitoDeactivationClient, CognitoReactivationClient, Any, Protocol

### Community 106 - "FakeCognitoReader"
Cohesion: 0.15
Nodes (5): ReconciledCognitoIdentity, AwsError, FakeCognitoReader, NoReturn, RuntimeError

### Community 107 - "dev/variables.tf"
Cohesion: 0.16
Nodes (10): Terraform module: infra/environments/dev, output.aws_region, provider.aws, var.aws_account_id, var.aws_region, var.github_owner_id, var.github_repository, var.github_repository_id (+2 more)

### Community 108 - "test_update_routes.py"
Cohesion: 0.38
Nodes (9): event(), Any, Exception, parametrize, resolve(), test_patch_maps_domain_errors_without_leaking_details(), test_patch_rejects_invalid_http_or_json_request(), test_patch_returns_200_and_calls_update_service() (+1 more)

### Community 109 - "user_provisioning.py"
Cohesion: 0.43
Nodes (6): build_user_provisioning_items(), _required_string(), parametrize, record(), test_builds_approved_five_item_domain_shapes(), test_retries_rebuild_identical_items_and_client_request_token()

### Community 110 - "pytest"
Cohesion: 0.21
Nodes (9): MonkeyPatch, parametrize, test_audit_retention_must_be_positive_integer(), test_required_configuration(), pytest, main(), select_targets(), parametrize (+1 more)

### Community 111 - "TemporaryGitRepository"
Cohesion: 0.27
Nodes (3): CompletedProcess, Path, TemporaryGitRepository

### Community 112 - "main.tsx"
Cohesion: 0.24
Nodes (6): configureAmplify(), env, frontend_src_index, aws-amplify, react, react-dom

### Community 113 - "DynamoDBClient"
Cohesion: 0.38
Nodes (3): DynamoDBClient, Any, Protocol

### Community 114 - "CognitoClient"
Cohesion: 0.33
Nodes (3): CognitoClient, Any, Protocol

### Community 115 - "CognitoIdentityEvidence"
Cohesion: 0.20
Nodes (24): CognitoCreateOutcome, StrEnum, CognitoIdentityEvidence, StrEnum, claimed_record(), FakeCognitoRepository, FakeSagaRepository, Exception (+16 more)

### Community 116 - "Architecture Documentation"
Cohesion: 0.25
Nodes (8): Architecture Documentation, Audit Documentation, Architecture Decisions, Canonical Documentation to Engineering Flow, Governance, Operations Documentation, Serverless Student Manager Reading Order v2.3, Requirements

### Community 117 - "Frontend Icon Sprite"
Cohesion: 0.50
Nodes (8): Bluesky Butterfly Icon, Discord Icon, Code Documentation File Icon, GitHub Octocat Icon, Frontend Icon Sprite, Social and Developer Link Iconography, Social Profile Badge Icon, X Social Network Icon

### Community 118 - "IdempotencyTable"
Cohesion: 0.47
Nodes (3): IdempotencyTable, Any, Protocol

### Community 120 - "DynamoDBTable"
Cohesion: 0.38
Nodes (3): DynamoDBTable, Any, Protocol

### Community 121 - "scripts"
Cohesion: 0.33
Nodes (6): scripts, build, dev, lint, preview, test

### Community 122 - "test_routes.py"
Cohesion: 0.27
Nodes (14): event(), FakeContext, FakeService, Any, Exception, MonkeyPatch, parametrize, resolve() (+6 more)

### Community 123 - "DynamoDBClient"
Cohesion: 0.40
Nodes (3): DynamoDBClient, Any, Protocol

### Community 124 - "test_resend_invitation_routes.py"
Cohesion: 0.27
Nodes (13): event(), FakeContext, FakeService, Any, Exception, MonkeyPatch, parametrize, resolve() (+5 more)

### Community 125 - "conditional_error"
Cohesion: 0.40
Nodes (3): conditional_error(), Any, ClientError

### Community 126 - "Vite Logo"
Cohesion: 0.70
Nodes (5): Adaptive Light and Dark Color Scheme, Purple Cyan Lightning Bolt Mark, Parenthesis Logo Frame, Vite Brand Identity, Vite Logo

### Community 127 - "tsconfig.json"
Cohesion: 0.40
Nodes (4): compilerOptions, paths, files, references

### Community 128 - "Graphify"
Cohesion: 0.50
Nodes (4): Graph Query Traversal, Incremental Graph Update, Graphify, Knowledge Graph Pipeline

### Community 129 - "get_aws_error_code"
Cohesion: 0.19
Nodes (23): get_aws_error_code(), is_ambiguous_aws_transport_error(), is_ambiguous_dynamodb_write_error(), BaseException, _aws_error(), AwsStyleError, BaseException, Exception (+15 more)

### Community 130 - "Layered Platform Illustration"
Cohesion: 0.67
Nodes (4): Connected Layer Separation, Layered Platform Illustration, Lower Purple Foundation Layer, Upper Interface Layer

### Community 132 - "test_cognito_reactivation_repository.py"
Cohesion: 0.20
Nodes (17): client_error(), compatible_user(), FakeCognitoClient, Any, ClientError, Exception, parametrize, readback() (+9 more)

### Community 133 - "aws_dynamodb_table.this"
Cohesion: 0.18
Nodes (12): aws_dynamodb_table.this, Terraform module: infra/modules/audit_store, output.gsi_actor_time, output.gsi_correlation_time, output.gsi_period_time, output.table_arn, output.table_name, var.data_classification (+4 more)

### Community 134 - "Non-HTTP Idempotency"
Cohesion: 0.67
Nodes (3): First Administrator Email Verification, First Administrator Invitation Resume, Non-HTTP Idempotency

### Community 135 - "Purple Lightning Bolt Favicon"
Cohesion: 1.00
Nodes (3): Purple Lightning Bolt Favicon, Lightning Bolt Symbol, Purple Cyan Neon Gradient Palette

### Community 136 - "React Logo"
Cohesion: 0.67
Nodes (3): Atomic Orbit Motif, React Brand Identity, React Logo

### Community 138 - "aws_cognito_user_pool.this"
Cohesion: 0.22
Nodes (11): aws_cognito_user_pool_client.this, aws_cognito_user_pool.this, Terraform module: infra/modules/identity, output.issuer, output.user_pool_arn, output.user_pool_client_id, output.user_pool_endpoint, output.user_pool_id (+3 more)

### Community 162 - "test_admin_user_routes.py"
Cohesion: 0.30
Nodes (10): event(), FakeService, Any, Exception, parametrize, resolve(), test_detail_maps_success_not_found_forbidden_and_safe_technical_error(), test_list_parses_exact_contract_and_defaults() (+2 more)

### Community 163 - "aws_dynamodb_table.this"
Cohesion: 0.21
Nodes (10): aws_dynamodb_table.this, Terraform module: infra/modules/student_store, output.gsi_all_name, output.gsi_status_name, output.table_arn, output.table_name, var.deletion_protection_enabled, var.point_in_time_recovery_enabled (+2 more)

### Community 164 - "lambda_handler"
Cohesion: 0.40
Nodes (5): lambda_handler(), Any, inject_lambda_context, LambdaContext, log_metrics

### Community 165 - "bootstrap_admin/tests/test_context.py"
Cohesion: 0.25
Nodes (21): copy, InvalidBootstrapRecordError, _optional_nonempty_string(), parse_bootstrap_context(), ValueError, _required_integer(), _required_string(), _required_uuid() (+13 more)

### Community 166 - "aws_dynamodb_table.this"
Cohesion: 0.24
Nodes (9): aws_dynamodb_table.this, Terraform module: infra/modules/idempotency_store, output.table_arn, output.table_name, var.data_classification, var.deletion_protection_enabled, var.point_in_time_recovery_enabled, var.table_name (+1 more)

### Community 167 - "aws_dynamodb_table.this"
Cohesion: 0.23
Nodes (9): aws_dynamodb_table.this, Terraform module: infra/modules/user_store, output.gsi_all_users_name, output.table_arn, output.table_name, var.deletion_protection_enabled, var.point_in_time_recovery_enabled, var.table_name (+1 more)

### Community 168 - "DynamoDBClient"
Cohesion: 0.40
Nodes (3): DynamoDBClient, Any, Protocol

### Community 170 - "LifecycleIdempotencyRecord"
Cohesion: 0.12
Nodes (4): LifecycleIdempotencyRecord, LifecycleOperation, LifecycleIdempotencyProtocol, LifecycleOperation

### Community 173 - ".__init__"
Cohesion: 0.18
Nodes (7): CognitoRepositoryProtocol, IdempotencyRepositoryProtocol, Any, datetime, Protocol, UUID, UserRepositoryProtocol

### Community 174 - "graphify reference: extra exports and benchmark"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 177 - "Restauração da documentação canônica v2.3 — Engineering Ready"
Cohesion: 0.40
Nodes (4): Antes da substituição, Estrutura esperada, Procedimento recomendado, Restauração da documentação canônica v2.3 — Engineering Ready

### Community 179 - "graphify reference: add a URL and watch a folder"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 180 - "graphify reference: commit hook and native CLAUDE.md integration"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

### Community 200 - "IdempotencyClient"
Cohesion: 0.21
Nodes (3): IdempotencyClient, Any, Protocol

### Community 201 - "service_models.py"
Cohesion: 0.33
Nodes (7): FirstAdminBootstrapConfig, parametrize, test_bootstrap_result_accepts_terminal_state(), test_bootstrap_result_is_immutable(), test_first_admin_bootstrap_config_accepts_valid_values(), test_first_admin_bootstrap_config_rejects_empty_string(), test_first_admin_bootstrap_config_rejects_nonpositive_retention()

## Knowledge Gaps
- **232 isolated node(s):** `$schema`, `style`, `rsc`, `tsx`, `config` (+227 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 828 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **53 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `UserRepository` connect `UserRepository` to `test_user_repository.py`, `users_api/app.py`, `users_api/dependencies.py`, `admin_user_service.py`, `DynamoDBClient`, `user_repository.py`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Why does `SagaClaim` connect `InvitationSagaInvariantError` to `UserRepositoryProtocol`, `test_user_provisioning_service.py`, `DeactivationService`, `SagaRepositoryProtocol`, `CreateSagaState`, `typing`, `users_api/errors.py`, `test_role_change_service.py`, `ReactivationService`, `test_resend_invitation_service.py`?**
  _High betweenness centrality (0.018) - this node is a cross-community bridge._
- **Why does `InvitationSagaInvariantError` connect `InvitationSagaInvariantError` to `ResendInvitationService`, `CreateUserService`, `DeactivationService`, `user_provisioning.py`, `test_invitation_saga.py`, `CognitoIdentityEvidence`, `typing`, `users_api/errors.py`, `ReactivationService`?**
  _High betweenness centrality (0.017) - this node is a cross-community bridge._
- **Are the 26 inferred relationships involving `InvitationSagaInvariantError` (e.g. with `InvitationSagaRepository` and `CognitoCreateService`) actually correct?**
  _`InvitationSagaInvariantError` has 26 INFERRED edges - model-reasoned connections that need verification._
- **What connects `$schema`, `style`, `rsc` to the rest of the system?**
  _232 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `bootstrap_admin/tests/test_service.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05619834710743802 - nodes in this community are weakly interconnected._
- **Should `verify_first_admin_email/tests/test_service.py` be split into smaller, more focused modules?**
  _Cohesion score 0.10411392405063291 - nodes in this community are weakly interconnected._