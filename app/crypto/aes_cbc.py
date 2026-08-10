"""
AES/CBC/PKCS5Padding compatible with openapi-mng-dev CommonFunc.aesEncode/aesDecode.

Java side (CommonFunc.java):
    key = key.getBytes("UTF-8")           # used directly as AES key material (16/24/32 bytes)
    iv  = new byte[16]                    # all-zero IV
    Cipher.getInstance("AES/CBC/PKCS5Padding")
    output = Base64(ciphertext)

PKCS5Padding on a 16-byte block cipher is byte-identical to PKCS7Padding.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_ZERO_IV = b"\x00" * 16
_VALID_KEY_LENS = (16, 24, 32)


def _key_bytes(key: str) -> bytes:
    key_bytes = key.encode("utf-8")
    if len(key_bytes) not in _VALID_KEY_LENS:
        raise ValueError(
            f"AES key must be 16, 24 or 32 bytes (UTF-8), but was {len(key_bytes)} bytes"
        )
    return key_bytes


def encrypt(plain: str | None, key: str) -> str | None:
    if plain is None:
        return None
    if plain == "" or not key:
        return ""
    cipher = Cipher(algorithms.AES(_key_bytes(key)), modes.CBC(_ZERO_IV))
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(plain.encode("utf-8")) + padder.finalize()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("utf-8")


def decrypt(cipher_base64: str | None, key: str) -> str | None:
    if cipher_base64 is None:
        return None
    if cipher_base64 == "" or not key:
        return ""
    try:
        cipher = Cipher(algorithms.AES(_key_bytes(key)), modes.CBC(_ZERO_IV))
        decryptor = cipher.decryptor()
        decoded = base64.b64decode(cipher_base64.encode("utf-8"))
        padded = decryptor.update(decoded) + decryptor.finalize()
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        plain = unpadder.update(padded) + unpadder.finalize()
        return plain.decode("utf-8")
    except Exception:
        return ""
