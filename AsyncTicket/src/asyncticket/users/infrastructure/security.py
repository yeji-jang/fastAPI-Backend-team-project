import bcrypt

from asyncticket.users.domain.service import PasswordHasher


MAX_BCRYPT_PASSWORD_BYTES = 72


class BcryptPasswordHasher(PasswordHasher):
    def hash(self, raw_password: str) -> str:
        
        password_bytes = raw_password.encode("utf-8")

        if len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
            raise ValueError(
                "Password must be 72 bytes or fewer.",
            )

        hashed_password = bcrypt.hashpw(
            password_bytes,
            bcrypt.gensalt(),
        )

        return hashed_password.decode("utf-8")

    def verify(
        self,
        raw_password: str,
        hashed_password: str,
    ) -> bool:
       
        password_bytes = raw_password.encode("utf-8")

        if len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
            return False

        try:
            return bcrypt.checkpw(
                password_bytes,
                hashed_password.encode("utf-8"),
            )
        except (ValueError, TypeError):
            return False