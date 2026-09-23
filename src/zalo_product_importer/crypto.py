from __future__ import annotations

import base64
import json
import urllib.parse
from typing import Any

try:
    from Crypto.Cipher import AES
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Missing dependency: install pycryptodome.") from exc


ZERO_IV = bytes.fromhex("00000000000000000000000000000000")


def encode_payload(payload: dict[str, Any], secret_key: str) -> str:
    key = base64.b64decode(secret_key)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    padded = _pad(raw, AES.block_size)
    encrypted = AES.new(key, AES.MODE_CBC, ZERO_IV).encrypt(padded)
    return base64.b64encode(encrypted).decode("ascii")


def decode_payload(payload: str, secret_key: str) -> Any:
    key = base64.b64decode(secret_key)
    encrypted = base64.b64decode(urllib.parse.unquote(payload).encode("ascii"))
    padded = AES.new(key, AES.MODE_CBC, ZERO_IV).decrypt(encrypted)
    raw = _unpad(padded)
    return json.loads(raw.decode("utf-8"))


def _pad(value: bytes, block_size: int) -> bytes:
    padding_length = block_size - len(value) % block_size
    return value + bytes([padding_length]) * padding_length


def _unpad(value: bytes) -> bytes:
    padding_length = value[-1]
    if padding_length <= 0 or padding_length > len(value):
        raise ValueError("Invalid PKCS#7 padding.")
    return value[:-padding_length]
