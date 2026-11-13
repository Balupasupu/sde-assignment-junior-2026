import os
import hmac
import hashlib

from cryptography.fernet import Fernet


def get_encryption():
    key = os.environ.get("FERNET_KEY")

    if not key:
        raise RuntimeError("FERNET_KEY is not configured")

    return Fernet(key.encode())


def encrypt_text(value):
    if value is None:
        return None

    return get_encryption().encrypt(
        value.encode("utf-8")
    ).decode("utf-8")


def decrypt_text(encrypted_value):
    if encrypted_value is None:
        return None

    return get_encryption().decrypt(
        encrypted_value.encode("utf-8")
    ).decode("utf-8")


def hash_phone(canonical_phone):
    key = os.environ.get("PHONE_HASH_KEY")

    if not key:
        raise RuntimeError("PHONE_HASH_KEY is not configured")

    return hmac.new(
        key.encode("utf-8"),
        canonical_phone.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()