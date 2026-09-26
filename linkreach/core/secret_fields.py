"""Encrypted Django fields for local credentials and browser session state.

Windows releases use the signed-in user's DPAPI key. Non-Windows test and
development environments use Fernet with Django's installation secret.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
from ctypes import wintypes

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


_PREFIX = "enc:v1:"


class SecretDecryptionError(RuntimeError):
    """Encrypted local data cannot be opened by this installation/user."""


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(
        len(data),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    return blob, buffer


def _dpapi_encrypt(data: bytes) -> bytes:
    source, source_buffer = _blob(data)
    result = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptProtectData(
        ctypes.byref(source),
        "linkreach local secret",
        None,
        None,
        None,
        0x01,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(result),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(result.pbData)
        del source_buffer


def _dpapi_decrypt(data: bytes) -> bytes:
    source, source_buffer = _blob(data)
    result = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        0x01,
        ctypes.byref(result),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(result.pbData)
        del source_buffer


def _fernet() -> Fernet:
    digest = hashlib.sha256(
        ("linkreach-local-secrets:" + settings.SECRET_KEY).encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def protect_secret(value: str) -> str:
    if not value or value.startswith(_PREFIX):
        return value
    raw = value.encode("utf-8")
    if os.name == "nt":
        payload = base64.urlsafe_b64encode(_dpapi_encrypt(raw)).decode("ascii")
        return f"{_PREFIX}dpapi:{payload}"
    return f"{_PREFIX}fernet:{_fernet().encrypt(raw).decode('ascii')}"


def reveal_secret(value: str) -> str:
    if not value or not value.startswith(_PREFIX):
        # Backward-compatible read for data written before encryption landed.
        return value
    try:
        _prefix, _version, provider, payload = value.split(":", 3)
        if provider == "dpapi":
            if os.name != "nt":
                raise SecretDecryptionError(
                    "This secret is protected for its original Windows user."
                )
            raw = _dpapi_decrypt(base64.urlsafe_b64decode(payload.encode("ascii")))
        elif provider == "fernet":
            raw = _fernet().decrypt(payload.encode("ascii"))
        else:
            raise SecretDecryptionError(f"Unknown secret provider: {provider}")
        return raw.decode("utf-8")
    except SecretDecryptionError:
        raise
    except (ValueError, UnicodeError, InvalidToken, OSError) as exc:
        raise SecretDecryptionError(
            "A saved credential could not be decrypted. Re-enter it in Settings."
        ) from exc


class EncryptedTextField(models.TextField):
    """Stores text encrypted while exposing plaintext to model code."""

    def from_db_value(self, value, expression, connection):
        return reveal_secret(value) if value is not None else None

    def to_python(self, value):
        if value is None or not isinstance(value, str):
            return value
        return reveal_secret(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return protect_secret(value) if value is not None else None


class EncryptedJSONField(models.TextField):
    """Encrypted JSON object field used for persisted browser storage state."""

    def from_db_value(self, value, expression, connection):
        if value is None or isinstance(value, (dict, list)):
            return value
        plaintext = reveal_secret(value)
        return json.loads(plaintext) if plaintext else None

    def to_python(self, value):
        if value is None or isinstance(value, (dict, list)):
            return value
        plaintext = reveal_secret(value)
        return json.loads(plaintext) if plaintext else None

    def get_prep_value(self, value):
        if value is None:
            return None
        if isinstance(value, str) and value.startswith(_PREFIX):
            return value
        return protect_secret(json.dumps(value, separators=(",", ":"), sort_keys=True))
