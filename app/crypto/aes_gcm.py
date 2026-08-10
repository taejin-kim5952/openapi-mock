"""
AES-256/GCM compatible with openapi-ptl Aes256GcmSupport.

Wire format: Base64(nonce[12] || ciphertext || tag[16])
Key: 64 hex chars → 32 bytes, otherwise UTF-8 must be exactly 32 bytes.
"""

from __future__ import annotations

import base64
import os
import re

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_LEN = 12
_TAG_LEN = 16
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def resolve_aes256_key_bytes(key: str) -> bytes:
    if not key:
        raise ValueError("AES-256 key is empty")
    if _HEX64.match(key):
        return bytes.fromhex(key)
    utf8 = key.encode("utf-8")
    if len(utf8) != 32:
        raise ValueError(
            f"AES-256 key must be 32 bytes (UTF-8) or 64 hex characters, but was {len(utf8)} bytes"
        )
    return utf8


def encrypt(plain: str | None, key: str) -> str | None:
    if plain is None:
        return None
    if plain == "":
        return ""
    if not key:
        return ""
    key_bytes = resolve_aes256_key_bytes(key)
    nonce = os.urandom(_NONCE_LEN)
    aesgcm = AESGCM(key_bytes)
    # cryptography AESGCM.encrypt returns ciphertext || tag
    cipher_with_tag = aesgcm.encrypt(nonce, plain.encode("utf-8"), None)
    return base64.b64encode(nonce + cipher_with_tag).decode("utf-8")


def decrypt(cipher_base64: str | None, key: str) -> str | None:
    if cipher_base64 is None:
        return None
    if cipher_base64 == "":
        return ""
    if not key:
        return ""
    try:
        key_bytes = resolve_aes256_key_bytes(key)
        decoded = base64.b64decode(cipher_base64.encode("utf-8"))
        if len(decoded) < _NONCE_LEN + _TAG_LEN:
            return ""
        nonce = decoded[:_NONCE_LEN]
        cipher_with_tag = decoded[_NONCE_LEN:]
        aesgcm = AESGCM(key_bytes)
        return aesgcm.decrypt(nonce, cipher_with_tag, None).decode("utf-8")
    except Exception:
        return ""
