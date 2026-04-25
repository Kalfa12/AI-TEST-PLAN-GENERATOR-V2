"""Password hashing and verification using Argon2 (M13).

Never use bcrypt for passwords — Argon2 is the current best practice.
bcrypt is reserved for API key material (passlib) for its fixed-cost
characteristic that's acceptable for short, high-entropy keys.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_ph = PasswordHasher()


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        _ph.verify(hashed, plain)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
