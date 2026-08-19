from tools.bootstrap_admin.models import (
    build_cognito_projection,
    build_unique_email,
    build_user_profile,
)


def test_build_user_profile_uses_adr_023_physical_model() -> None:
    item = build_user_profile(
        user_id="user-123",
        cognito_sub="cognito-sub-123",
        full_name="Maria da Silva",
        email="admin@example.com",
        created_at="2026-08-19T20:00:00Z",
        created_by="bootstrap-admin",
    )

    assert item == {
        "PK": "USER#user-123",
        "SK": "PROFILE",
        "userId": "user-123",
        "cognitoSub": "cognito-sub-123",
        "fullName": "Maria da Silva",
        "normalizedName": "maria da silva",
        "email": "admin@example.com",
        "role": "ADMIN",
        "status": "INVITED",
        "authVersion": 1,
        "createdAt": "2026-08-19T20:00:00Z",
        "createdBy": "bootstrap-admin",
        "updatedAt": "2026-08-19T20:00:00Z",
        "updatedBy": "bootstrap-admin",
        "GSI1PK": "USERS",
        "GSI1SK": "NAME#maria da silva#USER#user-123",
    }


def test_build_unique_email_uses_adr_023_physical_model() -> None:
    item = build_unique_email(
        user_id="user-123",
        email="  Admin@Example.COM ",
    )

    assert item == {
        "PK": "UNIQUE#EMAIL#admin@example.com",
        "SK": "UNIQUE",
        "userId": "user-123",
    }


def test_build_cognito_projection_uses_adr_023_physical_model() -> None:
    item = build_cognito_projection(
        user_id="user-123",
        cognito_sub="cognito-sub-123",
    )

    assert item == {
        "PK": "COGNITO#cognito-sub-123",
        "SK": "AUTHORIZATION",
        "userId": "user-123",
        "role": "ADMIN",
        "status": "INVITED",
        "authVersion": 1,
    }
