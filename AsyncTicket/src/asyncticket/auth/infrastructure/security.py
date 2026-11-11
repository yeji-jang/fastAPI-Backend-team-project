import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from jwt import InvalidTokenError

from asyncticket.auth.domain.service import (
    AuthRole,
    AccessTokenPayload,
    TokenProvider,
)
from asyncticket.auth.domain.exceptions import InvalidAccessTokenError


class JwtTokenProvider(TokenProvider):
    def __init__(
            self,
            secret_key: str | None = None,
            algorithm: str = "HS256",
            access_token_minutes: int | None = None,
    ) -> None:
        self.secret_key = secret_key or os.getenv(
            "JWT_SECRET_KEY",
        )

        if not self.secret_key:
            raise RuntimeError(
                "JWT_SECRET_KEY 환경 변수가 설정되지 않았습니다."
            )

        self.algorithm = algorithm

        self.access_token_minutes = access_token_minutes or int(
            os.getenv(
                "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
                "30"
            )
        )

    def issue_access_token(
        self,
        user_id: int,
        role: AuthRole,
    ) -> AccessTokenPayload:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(
            minutes=self.access_token_minutes
        )
        jti = str(uuid.uuid4())

        payload = {
            "sub": str(user_id),
            "role": role.value,
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }

        encoded_token = jwt.encode(
            payload,
            self.secret_key,
            algorithm=self.algorithm,
        )

        return AccessTokenPayload(
            access_token=encoded_token,
            user_id=user_id,
            role=role,
            jti=jti,
            expires_at=expires_at,
        )

    def verify_access_token(
        self,
        token: str,
    ) -> AccessTokenPayload:
        try:
            decoded_payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )

            subject = decoded_payload.get("sub")
            role_value = decoded_payload.get("role")
            jti = decoded_payload.get("jti")
            exp = decoded_payload.get("exp")

            if not subject or not role_value or not jti or not exp:
                raise InvalidTokenError(
                    "필수 JWT claim이 없습니다."
                )

            user_id = int(subject)
            role = AuthRole(role_value)
            expires_at = datetime.fromtimestamp(
                int(exp),
                tz=timezone.utc,
            )
        except (InvalidTokenError, TypeError, ValueError) as exc:
            raise InvalidAccessTokenError(
                "JWT claim 형식이 올바르지 않습니다."
            ) from exc

        return AccessTokenPayload(
            access_token=token,
            user_id=user_id,
            role=role,
            jti=jti,
            expires_at=expires_at,
        )
