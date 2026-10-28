"""
Password hashing for the demo advisor accounts.

Passwords are never stored in plain text: each is salted and hashed with
PBKDF2-HMAC-SHA256 (Python standard library). The demo accounts use test
passwords published in the README; they protect synthetic data only.
"""

import hashlib
import hmac
import secrets

ITERATIONS = 120_000

# Test accounts for the teaching team (synthetic data only, not real people).
DEMO_USERS = [
    {"username": "advisor.a", "display_name": "Demo Advisor A", "password": "Demo-Advisor-A1"},
    {"username": "advisor.b", "display_name": "Demo Advisor B", "password": "Demo-Advisor-B2"},
]


def hash_password(password: str, salt: str = None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS)
    return digest.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, stored_hash)
