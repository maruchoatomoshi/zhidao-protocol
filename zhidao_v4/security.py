from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
SCRYPT_MAXMEM = 64 * 1024 * 1024
LOCAL_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


class CredentialValidationError(ValueError):
    pass


def normalize_local_username(username: str) -> str:
    normalized = str(username or "").strip().lower()
    if not LOCAL_USERNAME_RE.fullmatch(normalized):
        raise CredentialValidationError(
            "Username must be 3-64 lowercase ASCII characters: a-z, 0-9, dot, dash, underscore"
        )
    return normalized


def validate_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < 12:
        raise CredentialValidationError("Password must contain at least 12 characters")
    if len(password) > 128:
        raise CredentialValidationError("Password must not exceed 128 characters")


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=SCRYPT_DKLEN,
        maxmem=SCRYPT_MAXMEM,
    )


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    validate_password(password)
    actual_salt = salt or secrets.token_bytes(16)
    digest = _derive(password, actual_salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return "$".join(
        (
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            _b64encode(actual_salt),
            _b64encode(digest),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n_value, r_value, p_value, salt_value, digest_value = encoded.split("$")
        if algorithm != "scrypt":
            return False
        n, r, p = int(n_value), int(r_value), int(p_value)
        if n < 2**14 or n > 2**18 or n & (n - 1):
            return False
        if not 1 <= r <= 16 or not 1 <= p <= 4:
            return False
        salt = _b64decode(salt_value)
        expected = _b64decode(digest_value)
        if len(salt) < 16 or len(expected) != SCRYPT_DKLEN:
            return False
        actual = _derive(str(password or ""), salt, n, r, p)
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


DUMMY_PASSWORD_HASH = hash_password(
    "not-a-real-password",
    salt=b"zhidao-auth-dummy",
)
