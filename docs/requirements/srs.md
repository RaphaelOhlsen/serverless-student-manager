# Software Requirements Specification (SRS)

## Serverless Student Manager

**Status:** Approved baseline — architecture resolutions incorporated  
**Document version:** 1.2  
**Date:** 2026-08-10  
**Document language:** English  
**Application locale:** Portuguese (Brazil)

---

## 1. Introduction

### 1.1 Purpose

This document specifies the functional and non-functional requirements of the **Serverless Student Manager**, a web application for managing students in a single educational institution.

The system is a portfolio project designed to demonstrate professional software engineering practices using serverless architecture on AWS, including authentication, authorization, observability, infrastructure as code, automated testing and continuous deployment.

### 1.2 Scope

The MVP will provide:

- Authentication of administrative users.
- Mandatory TOTP multi-factor authentication for administrative users.
- Role-based access control.
- Student registration and management.
- Student search and paginated listing.
- Logical deactivation and reactivation.
- Administrative user management.
- Audit trail.
- Standardized error handling.
- Logs, metrics and alarms.
- Infrastructure provisioned with Terraform.
- CI/CD with GitHub Actions.

### 1.3 Out of scope for the MVP

The following capabilities are not part of the first version:

- Grades and academic performance.
- Attendance.
- Subjects and classes.
- Financial management.
- Certificates and report cards.
- Student portal.
- Guardian portal.
- Native mobile application.
- Multi-tenancy.
- Physical deletion through the application.
- Advanced full-text or fuzzy search.
- Guardian registration.
- Student authentication.

---

## 2. Actors

### 2.1 Administrator

Responsible for administrative operations, including:

- Managing students.
- Deactivating and reactivating students.
- Managing users.
- Changing user roles.
- Consulting audit history.

### 2.2 Operator

Responsible for routine student operations, including:

- Registering students.
- Consulting students.
- Updating student data.
- Searching and listing students.

### 2.3 External technical actors

- **Amazon Cognito:** authenticates users and issues tokens.
- **Amazon API Gateway:** receives and authorizes API requests.
- **AWS Lambda:** executes business logic.
- **Amazon DynamoDB:** stores application data.
- **Amazon CloudWatch:** receives logs, metrics and alarms.
- **GitHub Actions:** performs quality checks and deployments.

---

## 3. Permission Matrix

| Capability | Administrator | Operator |
|---|:---:|:---:|
| Login and logout | Yes | Yes |
| Recover own access | Yes | Yes |
| Change own password | Yes | Yes |
| Consult own profile | Yes | Yes |
| List and consult students | Yes | Yes |
| Search students | Yes | Yes |
| Register students | Yes | Yes |
| Update students | Yes | Yes |
| Deactivate students | Yes | No |
| Reactivate students | Yes | No |
| Physically delete students | No | No |
| Consult student audit history | Yes | No |
| Create administrative users | Yes | No |
| List and consult administrative users | Yes | No |
| Change another user's role | Yes | No |
| Deactivate and reactivate users | Yes | No |
| Resend invitations | Yes | No |
| Consult technical logs through the application | No | No |

The frontend may hide controls according to the user's role, but authorization must always be enforced by the backend.

---

## 4. Functional Requirements — Authentication and Authorization

### RF-AUTH-001 — Login

The system shall allow active and authorized users to authenticate using their credentials and the mandatory MFA flow defined for their account state.

**Acceptance criteria:**

- Invalid credentials produce a generic message.
- The system does not reveal whether the email or password is incorrect.
- Valid credentials alone do not grant access when an authentication challenge is pending.
- A user with MFA already configured shall successfully validate a TOTP code before entering the protected area.
- A first-access user shall complete the required password-change and MFA-enrollment challenges before entering the protected area.
- After all required authentication challenges are successfully completed, the application resolves the current application role and status and redirects the user to the protected area.
- A deactivated application user shall not gain access even if Cognito authentication succeeds.

### RF-AUTH-002 — Logout

The system shall allow the user to terminate the current session.

**Acceptance criteria:**

- Local session data is removed.
- Protected screens become inaccessible.
- The user is redirected to the login screen.

### RF-AUTH-003 — Session renewal

The system shall renew the session while the renewal credentials remain valid.

**Acceptance criteria:**

- The user does not need to authenticate again during a valid session.
- Failed renewal redirects the user to login.
- The application must not enter an infinite retry loop.

### RF-AUTH-004 — Account recovery

The system shall allow a user to recover access through Amazon Cognito.

**Acceptance criteria:**

- Recovery is initiated with the registered email.
- The response does not reveal whether the email exists.
- The new password complies with the approved policy.

### RF-AUTH-005 — Deactivated user

A deactivated user shall not access the system.

### RF-AUTH-006 — Role-based access control

The backend shall authorize every protected operation according to the user's role.

### RF-AUTH-007 — Unauthenticated access

Requests without valid authentication shall receive HTTP `401 Unauthorized`.

### RF-AUTH-008 — Unauthorized access

Authenticated users without permission shall receive HTTP `403 Forbidden`.

### RF-AUTH-009 — Authenticated identity

Audit fields shall be populated from the validated identity contained in the token. The client shall not freely provide the identity responsible for an operation.

### RF-AUTH-010 — Change own password

Administrators and Operators shall be able to change their own password using Amazon Cognito.

**Acceptance criteria:**

- The current password is validated.
- The new password complies with the policy.
- The application never stores or logs either password.
- Changing the password does not change role or status.

### RF-AUTH-011 — Mandatory TOTP MFA

All administrative users, including Administrators and Operators, shall use TOTP multi-factor authentication.

**Acceptance criteria:**

- TOTP MFA is mandatory for both `ADMIN` and `OPERATOR`.
- SMS MFA is not used.
- Email MFA is not used.
- Remembered-device bypass is not used.
- A user cannot enter the protected area without satisfying the required MFA challenge.

### RF-AUTH-012 — MFA enrollment at first access

A user who has not yet enrolled TOTP shall configure MFA before completing the first authenticated session.

**Acceptance criteria:**

- A Cognito temporary password triggers `NEW_PASSWORD_REQUIRED`.
- The user defines a permanent password that complies with the approved password policy.
- When TOTP has not yet been configured, authentication proceeds to `MFA_SETUP`.
- The user associates a TOTP authenticator and proves possession with a valid code.
- Protected application access is granted only after successful completion of the required first-access challenges.
- TOTP shared secrets and codes are never written to application logs.

### RF-AUTH-013 — TOTP validation during login

A user with TOTP already configured shall successfully answer the Cognito TOTP challenge during login.

**Acceptance criteria:**

- Password validation precedes the TOTP challenge.
- An invalid or expired TOTP code does not create an authenticated application session.
- Authentication failures use generic messages that do not reveal sensitive account state.
- Successful TOTP validation still requires the backend authorization checks based on the current DynamoDB role and status.

### RF-AUTH-014 — Administrative MFA reset

The system shall support a controlled and audited administrative procedure to reset MFA when a user loses access to the registered authenticator.

**Acceptance criteria:**

- The reset requires an authorized administrative procedure.
- The reset action is auditable.
- Existing sessions are invalidated as defined by the operational recovery procedure.
- The affected user must enroll TOTP again before regaining normal protected access.
- TOTP secrets and recovery material are not exposed in logs or versioned files.
- Recovery of the sole active Administrator follows the separately documented exceptional operational procedure.

---

## 5. Functional Requirements — Student Management

### RF-ALU-001 — Register student

Administrators and Operators shall be able to register a student.

**Acceptance criteria:**

- An internal immutable identifier is generated.
- Registration number is mandatory and unique.
- Personal email is mandatory and unique.
- Telephone is mandatory.
- Birth date is mandatory and valid.
- Audit fields are populated by the backend.
- Success returns HTTP `201 Created`.
- Duplicate registration number or email returns HTTP `409 Conflict`.

### RF-ALU-002 — Consult student by identifier

Administrators and Operators shall be able to consult a student by internal identifier.

- A missing student returns HTTP `404 Not Found`.
- Active and inactive students can be consulted.

### RF-ALU-003 — Consult student by registration number

The system shall support exact lookup by normalized registration number.

### RF-ALU-004 — List students

The system shall provide a cursor-based paginated list.

**Acceptance criteria:**

- The cursor is opaque to the client.
- The response indicates whether more results exist.
- An empty result returns an empty list, not an error.
- Default page size: 20.
- Maximum page size: 100.
- Default order: student name in ascending alphabetical order.

The HTTP contract is `GET /students` and accepts only:

- `limit`: optional integer from 1 to 100, default 20;
- `cursor`: optional opaque pagination cursor;
- `status`: optional `ACTIVE`, `INACTIVE` or `ALL`, default `ACTIVE`;
- `namePrefix`: optional case-insensitive name prefix normalized by the backend.

The response contains `items`, `nextCursor` and `hasMore`. Each summarized item
contains only `studentId`, `registrationNumber`, `fullName` and `status`.
`hasMore` is true exactly when `nextCursor` is not null. Invalid parameters or
an invalid or incompatible cursor return HTTP `400 Bad Request`.

Exact lookup by registration number is not part of `GET /students`.

### RF-ALU-005 — Search student by name

The system shall support case-insensitive prefix search by normalized name.

The MVP shall not provide substring search, fuzzy matching or typo correction.

### RF-ALU-006 — Filter students by status

The list shall support:

- `ACTIVE`
- `INACTIVE`
- all statuses

The default filter shall be `ACTIVE`.

### RF-ALU-007 — Update student

Administrators and Operators shall be able to update mutable student data.

**Acceptance criteria:**

- `studentId` and registration number cannot be changed.
- Duplicate email is rejected.
- Validation rules are reapplied.
- Audit fields and record version are updated.
- Silent overwriting of a newer version is prevented.

### RF-ALU-008 — Deactivate student

Only Administrators shall be able to deactivate a student.

- The record is not physically deleted.
- Status becomes `INACTIVE`.
- Reason, date and responsible user are recorded.
- Operators receive HTTP `403 Forbidden`.

### RF-ALU-009 — Reactivate student

Only Administrators shall be able to reactivate a student.

### RF-ALU-010 — Consult student audit history

Only Administrators shall be able to consult student audit history.

### RF-ALU-011 — Validate student data

The backend shall validate types, required fields, limits, formats and unknown fields.

### RF-ALU-012 — Ensure unique registration number

Uniqueness shall be guaranteed for active and inactive students, including concurrent requests.

### RF-ALU-013 — Ensure unique personal email

Personal email shall be mandatory, normalized and unique among active and inactive students, including concurrent requests.

---

## 6. Functional Requirements — Administrative User Management

### RF-USR-001 — Create user

Only Administrators shall create administrative users.

Required data:

- Full name.
- Email.
- Role (`ADMIN` or `OPERATOR`).

The application shall not receive or store the user's password.

### RF-USR-002 — Invite user

The system shall initiate the Cognito invitation or password-definition flow.

### RF-USR-003 — List users

Only Administrators shall list users with pagination and filtering.

### RF-USR-004 — Consult user

Only Administrators shall consult another user's administrative details.

### RF-USR-005 — Change user role

Only Administrators shall change another user's role.

The application shall never be left without at least one active Administrator.

### RF-USR-006 — Deactivate user

Only Administrators shall deactivate another user.

The system shall prevent:

- Self-deactivation through the application.
- Deactivation of the last active Administrator.

### RF-USR-007 — Reactivate user

Only Administrators shall reactivate an inactive user.

### RF-USR-008 — Resend invitation

Only Administrators shall resend invitations to users in a compatible state.

### RF-USR-009 — Recover own access

Administrators and Operators shall recover their own access through Cognito.

### RF-USR-010 — Consult own profile

Authenticated users shall consult their own name, email, role and status.

### RF-USR-011 — User administration audit

Creation, invitation, role changes, deactivation, reactivation and unauthorized attempts shall be audited.

### RF-USR-012 — Search and filter users

Administrators shall search users by name or email and filter by role and status.

### RF-USR-013 — Provision first Administrator

The first Administrator shall be created through the controlled bootstrap procedure approved in ADR-013.

**Acceptance criteria:**

- There is no public sign-up for administrative users.
- The bootstrap is executed by a controlled Python utility invoked through a manual GitHub Actions workflow.
- GitHub Actions authenticates to AWS through OIDC and a temporary, environment-scoped IAM role.
- No permanent AWS credential or Administrator password is stored in code, Terraform, logs, GitHub secrets or versioned files.
- Cognito initiates the first-access temporary-password flow.
- The Administrator defines the permanent password during `NEW_PASSWORD_REQUIRED`.
- The Administrator completes mandatory TOTP enrollment before normal protected access.
- The bootstrap operation is idempotent.
- The procedure records audit information and handles Cognito/DynamoDB inconsistency according to the approved operational compensation procedure.
- No public bootstrap endpoint exists.

---

## 7. Audit, Errors and Observability

### RF-AUD-001 — Record relevant actions

The system shall audit relevant student and user operations.

Each event shall contain at least:

- Event type.
- Date and time in UTC.
- Responsible user.
- Affected resource.
- Operation result.
- Correlation identifier.

### RF-AUD-002 — Consult student history

Only Administrators shall consult student history.

### RF-AUD-003 — Audit immutability

Audit records shall not be changed or deleted through the application.

### RF-AUD-004 — Filter audit events

Administrators shall filter audit events by:

- Date range.
- Resource type.
- Resource identifier.
- Action type.
- Responsible user.
- Result.
- Correlation identifier.

### RF-ERR-001 — Standardized error response

The API shall use a consistent error structure:

```json
{
  "code": "STUDENT_EMAIL_ALREADY_EXISTS",
  "message": "Já existe um aluno cadastrado com este e-mail.",
  "correlationId": "01J4E9ZY3Y8PZQAB7M2C9F6XDE",
  "details": [
    {
      "field": "studentEmail",
      "reason": "duplicate"
    }
  ]
}
```

### RF-ERR-002 — HTTP status codes

The API shall use appropriate HTTP status codes, including:

| Code | Meaning |
|---:|---|
| `200` | Successful consultation or update |
| `201` | Resource created |
| `204` | Successful operation without response body |
| `400` | Invalid input |
| `401` | Unauthenticated |
| `403` | Unauthorized |
| `404` | Resource not found |
| `409` | Conflict or duplicate |
| `429` | Rate limit exceeded |
| `500` | Unexpected internal error |

### RF-ERR-003 — No internal details in client errors

Client responses shall not expose stack traces, AWS resource names, credentials, tokens or infrastructure details.

### RF-OBS-001 — Correlation identifier

Every API request shall have a correlation identifier that is propagated through related logs.

### RF-OBS-002 — Structured logs

Application logs shall use a structured format, preferably JSON.

### RF-OBS-003 — Application metrics

Metrics shall cover at least:

- Students created.
- Students deactivated.
- Errors per operation.
- Denied access.
- Lambda duration and errors.
- API Gateway failures.
- Throttling.
- Cognito and DynamoDB integration failures.

### RF-OBS-004 — Alarms

Alarms shall be defined for relevant error rates, repeated Lambda failures, throttling, abnormal duration and deployment failures.

### RF-OBS-005 — Personal data protection in logs

Logs shall not contain complete passwords, tokens, recovery codes, email addresses, telephone numbers or complete request bodies with personal data.

---

## 8. Business Rules

### 8.1 Student rules

#### RN-ALU-001 — Internal identifier

`studentId` is unique, immutable and generated by the system.

#### RN-ALU-002 — Registration number

The registration number shall:

- Be mandatory.
- Be unique among active and inactive students.
- Contain 4 to 20 letters, digits or hyphens.
- Be trimmed and stored in uppercase.
- Be immutable in the MVP.

#### RN-ALU-003 — Full name

The full name shall:

- Be mandatory.
- Contain 3 to 150 characters.
- Preserve accents and capitalization for display.
- Have a separate normalized value for search.

#### RN-ALU-004 — Personal email

`studentEmail` shall:

- Be mandatory.
- Be unique among active and inactive students.
- Be the primary contact channel.
- Be trimmed and stored in lowercase.
- Contain at most 254 characters.
- Not be used as a student login while the `STUDENT` role is outside the MVP.

#### RN-ALU-005 — Telephone

Telephone shall:

- Be mandatory.
- Include country code and area code.
- Be stored in normalized international format.
- Not be required to be unique.

#### RN-ALU-006 — Birth date

Birth date shall:

- Be mandatory.
- Be displayed in the frontend as `DD/MM/AAAA`.
- Be transmitted and stored as `AAAA-MM-DD`.
- Represent a real calendar date.
- Correctly handle leap years.
- Not be in the future.
- Contain no time or time zone.
- Be validated by both frontend and backend.

#### RN-ALU-007 — Status

Allowed values:

- `ACTIVE`
- `INACTIVE`

Every new student is created as `ACTIVE`.

#### RN-ALU-008 — Deactivation

Deactivation requires a reason between 5 and 300 characters and records the date and responsible Administrator.

#### RN-ALU-009 — Reactivation

Reactivation preserves the previous deactivation history.

#### RN-ALU-010 — Concurrency

Each student record shall contain a version number.

- Initial value: `1`.
- Every update increments the version.
- An outdated version returns HTTP `409 Conflict`.

#### RN-ALU-011 — Data minimization

The MVP shall not collect CPF, RG, address, medical data, financial data or photograph.

### 8.2 Administrative user rules

#### RN-USR-001 — Email

Administrative user email is mandatory, unique, verified and used for login.

#### RN-USR-002 — Identity

Each user shall have:

- `userId`: internal application identifier.
- `cognitoSub`: Cognito identifier that is immutable during normal identity operation.

The only permitted replacement of `cognitoSub` is the controlled break-glass procedure defined in ADR-019. In that exceptional procedure:

- `USER#<userId>` and the business `userId` remain unchanged;
- `oldCognitoSub` is replaced by `newCognitoSub`;
- `authVersion` is incremented;
- the identity replacement is audited.

#### RN-USR-003 — Status

Allowed states:

- `INVITED`
- `ACTIVE`
- `INACTIVE`

#### RN-USR-004 — Passwords

The application shall not store, process or log passwords.

#### RN-USR-005 — Last Administrator

At least one active Administrator shall always remain.

---

## 9. Data Dictionary

### 9.1 Student

| Field | Type | Required | Unique | Mutable |
|---|---|:---:|:---:|:---:|
| `studentId` | UUID/String | Yes | Yes | No |
| `registrationNumber` | String | Yes | Yes | No |
| `fullName` | String | Yes | No | Yes |
| `normalizedName` | String | Yes | No | Backend |
| `studentEmail` | String | Yes | Yes | Yes |
| `phone` | String | Yes | No | Yes |
| `birthDate` | Date | Yes | No | Yes |
| `status` | Enum | Yes | No | Administrator |
| `createdAt` | DateTime | Yes | No | No |
| `createdBy` | String | Yes | No | No |
| `updatedAt` | DateTime | Yes | No | Backend |
| `updatedBy` | String | Yes | No | Backend |
| `deactivatedAt` | DateTime | No | No | Backend |
| `deactivatedBy` | String | No | No | Backend |
| `deactivationReason` | String | No | No | Administrator |
| `version` | Integer | Yes | No | Backend |

### 9.2 Administrative user

| Field | Type | Required | Unique |
|---|---|:---:|:---:|
| `userId` | UUID/String | Yes | Yes |
| `cognitoSub` | String | Yes after Cognito creation | Yes |
| `fullName` | String | Yes | No |
| `email` | String | Yes | Yes |
| `role` | Enum | Yes | No |
| `status` | Enum | Yes | No |
| `createdAt` | DateTime | Yes | No |
| `createdBy` | String | Yes | No |
| `updatedAt` | DateTime | Yes | No |
| `updatedBy` | String | Yes | No |
| `deactivatedAt` | DateTime | No | No |
| `deactivatedBy` | String | No | No |
| `deactivationReason` | String | No | No |

### 9.3 Audit event

| Field | Description |
|---|---|
| `eventId` | Unique identifier |
| `eventType` | Operation type |
| `resourceType` | Student or user |
| `resourceId` | Affected resource |
| `actorId` | Responsible user |
| `occurredAt` | UTC date and time |
| `result` | Success or failure |
| `correlationId` | Request trace identifier |
| `changes` | Relevant changes without sensitive data |

---

## 10. Non-Functional Requirements

### 10.1 Security

#### RNF-SEC-001 — Secure communication

All communication shall use HTTPS.

#### RNF-SEC-002 — Centralized authentication

Authentication shall be delegated to Amazon Cognito.

#### RNF-SEC-003 — Least privilege

Users, Lambdas and pipelines shall receive only the permissions they need.

#### RNF-SEC-004 — Input validation

All API input shall be validated for type, size, format, allowed values, required fields and unknown fields.

#### RNF-SEC-005 — Encryption at rest

Applicable data and artifacts shall use encryption at rest.

#### RNF-SEC-006 — Secret management

Secrets shall not be stored in code, versioned files, logs or plain-text workflows. GitHub Actions should use federated identity whenever possible.

#### RNF-SEC-007 — Security headers

The frontend shall use appropriate security headers.

#### RNF-SEC-008 — Dependency security

Dependencies shall be versioned and scanned for relevant vulnerabilities.

#### RNF-SEC-009 — Password policy

Administrative user passwords shall contain:

- At least 12 characters.
- At least one uppercase letter.
- At least one lowercase letter.
- At least one digit.
- At least one special character.

Temporary passwords shall be changed at first access.

#### RNF-SEC-010 — Failed login protection

The system shall use Cognito's native protection against repeated failed authentication attempts.

- No parallel login-attempt counter will be implemented.
- Temporary lockout behavior shall be handled and tested.
- The frontend shall display a generic message.
- Abnormal attempts shall be monitored.

#### RNF-SEC-011 — Disable public sign-up

Public administrative-user registration shall be disabled.

#### RNF-SEC-012 — Mandatory administrative MFA

TOTP MFA shall be mandatory for Administrators and Operators.

- SMS MFA shall be disabled.
- Email MFA shall be disabled.
- Remembered devices shall not bypass MFA.
- TOTP secrets and codes shall not be logged.

#### RNF-SEC-013 — Authentication token lifetime

The initial authentication token policy shall be:

- Access token: 15 minutes.
- ID token: 15 minutes.
- Refresh token: 8 hours.
- Refresh token rotation enabled.

### 10.2 Performance

#### RNF-PERF-001 — API latency objectives

| Operation | Initial target |
|---|---:|
| Lookup by identifier | p95 under 1 second |
| Lookup by registration number | p95 under 1 second |
| Create or update | p95 under 1.5 seconds |
| Paginated listing | p95 under 1.5 seconds |

#### RNF-PERF-002 — Responsive interface

The frontend shall provide immediate visual feedback for asynchronous operations.

#### RNF-PERF-003 — Mandatory pagination

List endpoints shall never return unlimited data.

### 10.3 Reliability and availability

#### RNF-REL-001 — Availability objective

Initial production objective: `99.5%` monthly availability. This is an engineering objective, not a commercial SLA.

#### RNF-REL-002 — Failure consistency

Unexpected failures shall not leave partially updated business data.

#### RNF-REL-003 — Idempotency

Operations susceptible to retries shall prevent duplicate results.

#### RNF-REL-004 — Optimistic concurrency

Updates shall use record versions to prevent silent overwrites.

#### RNF-REL-005 — Recovery procedures

Procedures shall exist to recreate infrastructure, recover configuration, restore data when applicable and roll back problematic deployments.

### 10.4 Scalability

#### RNF-SCA-001 — Automatic scaling

Core components shall scale without permanent server provisioning.

#### RNF-SCA-002 — Stateless Lambdas

Lambdas shall not depend on persistent local state between executions.

#### RNF-SCA-003 — Excessive load protection

The architecture shall limit abusive requests, detect throttling and control consumption.

### 10.5 Privacy

#### RNF-PRIV-001 — Data minimization

Only data required by the MVP shall be collected.

#### RNF-PRIV-002 — Contact-data use

Email and telephone are student contact data. They shall not be used for marketing in the MVP.

#### RNF-PRIV-003 — Personal-data protection

Personal data shall not appear fully in logs, metrics, URLs or infrastructure identifiers.

#### RNF-PRIV-004 — Retention

The approved initial retention policy is:

- Audit events in `dev`: 90 days.
- Audit events in `prod`: 5 years.
- CloudWatch application logs in `dev`: 14 days.
- CloudWatch application logs in `prod`: 90 days.
- Idempotency records: 24 hours.
- `students` and `users`: no automatic TTL.

The final institutional disposal or anonymization policy for student and user business records shall be resolved before production.

### 10.6 Accessibility and user experience

#### RNF-ACC-001 — Keyboard navigation

Core functionality shall be usable by keyboard.

#### RNF-ACC-002 — Accessible forms

Forms shall use associated labels, textual error indications, coherent focus and messages that do not depend only on color.

#### RNF-ACC-003 — Responsive design

The interface shall work on desktop, notebook, tablet and modern mobile devices.

#### RNF-ACC-004 — Language

The initial interface language is Portuguese (Brazil).

#### RNF-ACC-005 — User feedback

Relevant operations shall provide clear success, validation, authorization, conflict and failure feedback.

### 10.7 Maintainability

#### RNF-MAN-001 — Modular organization

Frontend, backend and infrastructure shall have clear responsibilities.

#### RNF-MAN-002 — Code standards

The project shall use automated formatting, linting, static analysis and naming conventions.

#### RNF-MAN-003 — Synchronized documentation

Changes to behavior, architecture or contracts shall update the relevant documentation.

#### RNF-MAN-004 — Architecture decisions

Structural decisions shall be recorded as ADRs.

### 10.8 Testing and quality

#### RNF-TEST-001 — Automated tests

The project shall include unit, integration, API contract, frontend-flow and applicable infrastructure tests.

#### RNF-TEST-002 — Critical flows

Critical flows include:

- Login with mandatory TOTP MFA.
- First-access password change and TOTP enrollment.
- Administrative MFA reset.
- Role authorization.
- Student registration.
- Duplicate registration number.
- Duplicate email.
- Concurrent update.
- Student deactivation and reactivation.
- Administrative user creation and deactivation.
- Protection of the last Administrator.

#### RNF-TEST-003 — Quality pipeline

Before merge to `main`, the pipeline shall check formatting, linting, static analysis, tests, Terraform validation, relevant vulnerabilities and API contract consistency.

#### RNF-TEST-004 — Coverage objectives

- Backend business rules: minimum 80%.
- Frontend testable modules: minimum 70%.

Coverage alone shall not replace testing of critical behavior.

### 10.9 Cost

#### RNF-COST-001 — Low operational cost

The solution shall favor usage-based services and avoid permanent servers.

#### RNF-COST-002 — Budget controls

Initial portfolio objectives:

- Preventive alert: US$ 10/month.
- Critical alert: US$ 15/month.

#### RNF-COST-003 — Controlled retention

Logs, metrics and backups shall not be retained indefinitely without justification.

### 10.10 Compatibility and reproducibility

#### RNF-COMP-001 — Browsers

The application shall support modern versions of Chrome, Edge, Firefox and Safari.

#### RNF-COMP-002 — Reproducible infrastructure

Authorized users shall be able to recreate the environment using versioned source code, Terraform, documented variables and pipelines.

#### RNF-COMP-003 — Isolated environments

The environment strategy approved in ADR-007 is:

- `dev` and `prod` are separate environments.
- They initially reside in the same AWS account.
- Application resources, data, Cognito configuration, logs, Terraform state and deployment roles are not shared between environments.
- The project may begin with only `dev`.
- Separate AWS accounts remain a possible future evolution.

---

## 11. Use Cases

### UC-001 — Login

Actors: Administrator and Operator.

Precondition: the user has completed first-access setup and has TOTP enrolled.

Main flow:

1. User accesses login.
2. User provides email and password.
3. Cognito validates the credentials.
4. Cognito requests the TOTP challenge.
5. User provides a valid TOTP code.
6. Cognito completes authentication and issues tokens.
7. The frontend calls the protected API with the access token.
8. The API validates the JWT.
9. The backend validates `token_use=access` and resolves `COGNITO#<sub>` in the `users` table.
10. The backend verifies the current application `role` and `status`.
11. The user enters the protected area.

Alternative flows:

- Invalid credentials or TOTP produce a generic authentication failure.
- An inactive application user receives no protected access even if Cognito authentication succeeds.
- A user who has not completed first-access setup follows UC-017.

### UC-002 — Register student

Actors: Administrator and Operator.

Main flow:

1. User opens the registration form.
2. User provides registration number, name, personal email, telephone and birth date.
3. Frontend validates the input.
4. Backend validates again.
5. Uniqueness is checked.
6. Student is created as `ACTIVE`.
7. Audit data is recorded.

### UC-003 — Consult and search students

Actors: Administrator and Operator.

Supports:

- Paginated listing.
- Exact registration-number search.
- Prefix name search.
- Status filter.

### UC-004 — Update student

Actors: Administrator and Operator.

The current version is required and immutable fields cannot be changed.

### UC-005 — Deactivate student

Actor: Administrator.

Requires confirmation and a reason.

### UC-006 — Reactivate student

Actor: Administrator.

### UC-007 — Create administrative user

Actor: Administrator.

Creates the identity and starts the invitation flow.

### UC-008 — Deactivate user

Actor: Administrator.

Self-deactivation and deactivation of the last Administrator are prohibited.

### UC-009 — Recover access

Actors: Administrator and Operator.

Uses Cognito with a generic response that does not reveal account existence.

### UC-010 — List and consult users

Actor: Administrator.

### UC-011 — Change user role

Actor: Administrator.

### UC-012 — Reactivate user

Actor: Administrator.

### UC-013 — Consult audit

Actor: Administrator.

### UC-014 — Logout

Actors: Administrator and Operator.

### UC-015 — Resend invitation

Actor: Administrator.

### UC-016 — Consult own profile

Actors: Administrator and Operator.

### UC-017 — First access and TOTP enrollment

Actors: Administrator and Operator.

Precondition: Cognito has created or invited the user and a permanent password/TOTP enrollment has not yet been completed.

Main flow:

1. User authenticates with the Cognito temporary password.
2. Cognito returns `NEW_PASSWORD_REQUIRED`.
3. User defines a permanent password that satisfies the password policy.
4. Cognito requires `MFA_SETUP`.
5. The user associates a TOTP authenticator.
6. The user proves possession with a valid TOTP code.
7. Cognito completes authentication.
8. The application resolves current `role` and `status`.
9. The user enters the protected area.

The application never stores the password, TOTP shared secret or TOTP code in its business database or logs.

### UC-018 — Administrative MFA reset

Actor: Administrator or the separately authorized exceptional recovery procedure for the sole active Administrator.

Main flow:

1. The loss of the authenticator is identified.
2. The authorized recovery procedure verifies that an MFA reset is appropriate.
3. The MFA reset action is executed and audited.
4. Existing sessions are invalidated according to the operational procedure.
5. At the next access, the affected user must enroll TOTP again.
6. Normal access resumes only after successful TOTP enrollment and current role/status authorization.

The detailed exceptional recovery sequence for the sole active Administrator is maintained in the operational documentation.

---

## 12. Traceability Summary

### 12.1 Requirements to use cases

| Domain | Main requirements | Main use cases |
|---|---|---|
| Authentication | RF-AUTH-001 to RF-AUTH-014 | UC-001, UC-009, UC-014, UC-016 to UC-018 |
| Students | RF-ALU-001 to RF-ALU-013 | UC-002 to UC-006 |
| Users | RF-USR-001 to RF-USR-013 | UC-007, UC-008, UC-010 to UC-012, UC-015, UC-017 |
| Audit | RF-AUD-001 to RF-AUD-004 | UC-013 and all data-changing or security-sensitive flows |
| Errors | RF-ERR-001 to RF-ERR-003 | All API use cases |
| Observability | RF-OBS-001 to RF-OBS-005 | All API use cases and security-sensitive operational flows |

### 12.2 Requirements to approved architecture decisions

| ADR | Requirement coverage |
|---|---|
| ADR-001 — Monorepo | RNF-MAN-001, RNF-MAN-003, RNF-COMP-002 |
| ADR-002 — Frontend hosting | RNF-SEC-001, RNF-SEC-005, RNF-SEC-007, RNF-COST-001 |
| ADR-003 — HTTP API + JWT Authorizer | RF-AUTH-006 to RF-AUTH-009, RF-ERR-001 to RF-ERR-003 |
| ADR-004 — Lambdas by domain | RNF-MAN-001, RNF-SEC-003, RNF-SCA-002 |
| ADR-005 — DynamoDB by domain | RF-ALU-001 to RF-ALU-013, RF-USR-001 to RF-USR-013, RF-AUD-001 to RF-AUD-004 |
| ADR-006 — Authentication/authorization source of truth | RF-AUTH-001, RF-AUTH-005 to RF-AUTH-009, RN-USR-002 to RN-USR-005 |
| ADR-007 — Environments | RNF-COMP-003 |
| ADR-008 — Terraform remote state | RNF-COMP-002, RNF-SEC-005, RNF-SEC-006 |
| ADR-009 — GitHub Actions + OIDC | RNF-SEC-003, RNF-SEC-006, RNF-TEST-003 |
| ADR-010 — Observability | RF-OBS-001 to RF-OBS-005, RNF-COST-003 |
| ADR-011 — Testing strategy | RNF-TEST-001 to RNF-TEST-004 |
| ADR-012 — Idempotency | RNF-REL-002, RNF-REL-003 and retry-sensitive write flows |
| ADR-013 — First Administrator bootstrap | RF-USR-013, RF-AUTH-012, UC-017 |
| ADR-014 — Mandatory MFA | RF-AUTH-001, RF-AUTH-011 to RF-AUTH-014, RNF-SEC-012, RNF-SEC-013, UC-001, UC-017, UC-018 |
| ADR-015 — Retention | RNF-PRIV-004, RNF-COST-003 |
| ADR-016 — Terraform modules | RNF-MAN-001, RNF-MAN-002, RNF-COMP-002 |
| ADR-017 — Cognito/DynamoDB provisioning consistency | RF-USR-001, RF-USR-008, RF-USR-013, RF-AUTH-012, RNF-REL-002, RNF-REL-003 |
| ADR-018 — Non-HTTP idempotency | RF-USR-013, RF-AUTH-014, RNF-REL-002, RNF-REL-003 |
| ADR-019 — Sole Administrator MFA recovery | RF-AUTH-014, RN-USR-002, UC-018, RNF-SEC-012, RNF-REL-002, RNF-REL-003 |
| ADR-020 — Layered rollback and deployment recovery | RNF-REL-001, RNF-TEST-003, RNF-COMP-003 and deployment recovery procedures |

---

## 13. Assumptions

- The MVP serves one institution.
- Administrative users are internal employees.
- The application requires internet access.
- Every student has a mandatory personal email and telephone.
- Initial volume is compatible with a small or medium institution.
- Interface language and locale are Brazilian Portuguese.
- Birth dates are shown as `DD/MM/AAAA` and stored as `AAAA-MM-DD`.

---

## 14. External Dependencies

- Amazon Cognito.
- Amazon API Gateway.
- AWS Lambda.
- Amazon DynamoDB.
- Amazon CloudWatch.
- GitHub Actions.
- Terraform.
- Email-delivery capability associated with Cognito.

---

## 15. Project Constraints

- Serverless-first architecture.
- Required stack: React, TypeScript, Python, Lambda, API Gateway, DynamoDB, Cognito, Terraform and GitHub Actions.
- Monorepo.
- Infrastructure as code.
- Logical deactivation instead of ordinary physical deletion.
- Immutable registration number.
- Prefix-only name search in the MVP.
- No direct frontend access to DynamoDB.
- Passwords outside the application.
- Controlled monthly budget.

---

## 16. Initial Risks

| Risk | Mitigation |
|---|---|
| Inadequate DynamoDB model | Define access patterns before physical design |
| Excessive project complexity | Keep the MVP controlled and incremental |
| Unexpected AWS costs | Budgets, alerts, tags and retention controls |
| Personal-data exposure | Masking, secure logs and synthetic test data |
| Cognito/application inconsistency | Idempotency, defined operation order and compensation |
| Prefix search limitations | Keep scope explicit and evaluate future need |
| AWS service quotas | Metrics, pagination, throttling and quota documentation |
| Vendor lock-in | Accept consciously and record in ADR |

---

## 17. Open Items

### 17.1 Product

- Retention period and future disposal/anonymization policy for inactive students.
- Whether Administrators may edit their own display name.
- Future student access.
- Future guardian registration.
- Future outbound communications.

### 17.2 Architecture / Operations

The initial architecture decisions ADR-001 through ADR-020 are approved.

Items that remain intentionally open for later phases:

- production-grade Cognito e-mail delivery configuration;
- distributed tracing as a future evolution;
- final institutional data-retention/disposal policy for students and users.

### 17.3 Technical implementation

The following implementation choices may be selected during engineering as long as they do not conflict with approved requirements or ADRs:

- frontend build tool;
- CSS framework;
- component library;
- form library;
- frontend validation library;
- remote-data/state management;
- HTTP client;
- additional Python libraries.

The test strategy itself is approved in ADR-011; specific supporting libraries may evolve if equivalent quality gates are preserved.

Open items may remain unresolved while they do not block the current phase. Each shall be resolved before the activity that depends on it.

---

## 18. SRS Completion Criteria

This SRS is complete when:

- Actors and permissions are approved.
- Functional and non-functional requirements are documented.
- Business rules and data dictionaries are defined.
- Core use cases are described.
- Traceability covers all critical behavior.
- Assumptions, dependencies, constraints and risks are explicit.
- Open items are assigned to the appropriate future phase.
- No critical requirement lacks an associated rule or use case.

---

## 19. Approval

This document is the approved baseline for **Milestone 2 — Software Requirements Specification**.

Future changes shall be versioned and reflected in the requirements, traceability, architecture and implementation documents as applicable.
