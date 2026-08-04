from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_SCHEME = "scrypt"
_N = 2**14
_R = 8
_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_KEY_BYTES)
    encode = base64.urlsafe_b64encode
    return f"{_SCHEME}${_N}${_R}${_P}${encode(salt).decode()}${encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_text, digest_text = encoded.split("$", 5)
        if scheme != _SCHEME:
            return False
        if (int(n), int(r), int(p)) != (_N, _R, _P):
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=_N,
            r=_R,
            p=_P,
            dklen=len(expected),
        )
    except (ValueError, TypeError, UnicodeError):
        return False
    return hmac.compare_digest(actual, expected)


__all__ = ["hash_password", "verify_password"]
