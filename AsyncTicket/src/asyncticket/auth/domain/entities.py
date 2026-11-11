from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BlacklistedToken:
    jti_token: str
    expired_at: datetime

    def __post_init__(self) -> None:
        if not self.jti_token.strip():
            raise ValueError("jti_token은 비어 있을 수 없습니다.")