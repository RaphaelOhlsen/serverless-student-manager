from tools.bootstrap_admin.normalization import normalize_email, normalize_name


def build_user_profile(
    *,
    user_id: str,
    cognito_sub: str,
    full_name: str,
    email: str,
    created_at: str,
    created_by: str,
) -> dict[str, object]:
    normalized_name = normalize_name(full_name)
    normalized_email = normalize_email(email)

    return {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "userId": user_id,
        "cognitoSub": cognito_sub,
        "fullName": full_name,
        "normalizedName": normalized_name,
        "email": normalized_email,
        "role": "ADMIN",
        "status": "INVITED",
        "authVersion": 1,
        "createdAt": created_at,
        "createdBy": created_by,
        "updatedAt": created_at,
        "updatedBy": created_by,
        "GSI1PK": "USERS",
        "GSI1SK": f"NAME#{normalized_name}#USER#{user_id}",
    }


def build_unique_email(
    *,
    user_id: str,
    email: str,
) -> dict[str, object]:
    normalized_email = normalize_email(email)

    return {
        "PK": f"UNIQUE#EMAIL#{normalized_email}",
        "SK": "UNIQUE",
        "userId": user_id,
    }


def build_cognito_projection(
    *,
    user_id: str,
    cognito_sub: str,
) -> dict[str, object]:
    return {
        "PK": f"COGNITO#{cognito_sub}",
        "SK": "AUTHORIZATION",
        "userId": user_id,
        "role": "ADMIN",
        "status": "INVITED",
        "authVersion": 1,
    }
