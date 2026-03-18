from __future__ import annotations

import hashlib
import os
import zlib
from base64 import b64decode, b64encode
from collections.abc import Callable
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305

from pakem.analyze import FileMetadata, get_file_info
from pakem.serialize import (
    JsonSerializer,
    LlmPromptSerializer,
    Serializer,
    XmlSerializer,
)
from pakem.tokenizer import DEFAULT_TOKEN_COUNTER, TokenCounter


@dataclass(frozen=True)
class CompressionProfile:
    name: str
    compress: Callable[[bytes], bytes]
    decompress: Callable[[bytes], bytes]


@dataclass(frozen=True)
class CryptoProfile:
    name: str
    encrypt: Callable[[bytes, str], tuple[bytes, dict[str, str]]]
    decrypt: Callable[[bytes, str, dict[str, str], bool], bytes]


_COMPRESSION_REGISTRY: dict[str, CompressionProfile] = {}
_CRYPTO_REGISTRY: dict[str, CryptoProfile] = {}
_ANALYZER_REGISTRY: dict[
    str,
    Callable[[str, TokenCounter | None, str | None], tuple[FileMetadata, str]],
] = {}
_SERIALIZER_REGISTRY: dict[str, Callable[[str | None], Serializer]] = {}


def register_compression(profile: CompressionProfile) -> None:
    _COMPRESSION_REGISTRY[profile.name] = profile


def get_compression_profile(name: str) -> CompressionProfile:
    if name not in _COMPRESSION_REGISTRY:
        raise ValueError(f"Unsupported compression profile: {name}")
    return _COMPRESSION_REGISTRY[name]


def register_crypto(profile: CryptoProfile) -> None:
    _CRYPTO_REGISTRY[profile.name] = profile


def get_crypto_profile(name: str) -> CryptoProfile:
    if name not in _CRYPTO_REGISTRY:
        raise ValueError(f"Unsupported crypto profile: {name}")
    return _CRYPTO_REGISTRY[name]


def register_analyzer(
    name: str,
    analyzer: Callable[
        [str, TokenCounter | None, str | None], tuple[FileMetadata, str]
    ],
) -> None:
    _ANALYZER_REGISTRY[name] = analyzer


def get_analyzer(
    name: str,
) -> Callable[[str, TokenCounter | None, str | None], tuple[FileMetadata, str]]:
    if name not in _ANALYZER_REGISTRY:
        raise ValueError(f"Unsupported analyzer profile: {name}")
    return _ANALYZER_REGISTRY[name]


def register_serializer(
    name: str, factory: Callable[[str | None], Serializer]
) -> None:
    _SERIALIZER_REGISTRY[name] = factory


def get_serializer_factory(name: str) -> Callable[[str | None], Serializer]:
    if name not in _SERIALIZER_REGISTRY:
        raise ValueError(f"Unsupported serializer format: {name}")
    return _SERIALIZER_REGISTRY[name]


def _analyze_default(
    path: str, token_counter: TokenCounter | None, model: str | None
) -> tuple[FileMetadata, str]:
    metadata = get_file_info(path)
    with open(path, encoding="utf-8", errors="replace") as handle:
        content = handle.read()
    counter = token_counter or DEFAULT_TOKEN_COUNTER
    tokens = counter.count(content, model=model)
    lines = len(content.splitlines())
    return (
        FileMetadata(
            size=metadata.size,
            mtime=metadata.mtime,
            tokens=tokens,
            lines=lines,
            extension=metadata.extension,
            sha256=None,
            status=None,
        ),
        content,
    )


def _encrypt_none(payload: bytes, key: str) -> tuple[bytes, dict[str, str]]:
    return payload, {"cipher": "none"}


def _decrypt_none(
    payload: bytes, key: str, metadata: dict[str, str], legacy_mode: bool
) -> bytes:
    return payload


def _build_aead_encryptor(
    cipher_name: str,
) -> Callable[[bytes, str], tuple[bytes, dict[str, str]]]:
    def encrypt(payload: bytes, key_text: str) -> tuple[bytes, dict[str, str]]:
        passphrase = key_text.encode("utf-8", errors="replace")
        if not passphrase:
            raise ValueError("Encryption key must not be empty")
        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = hashlib.pbkdf2_hmac("sha256", passphrase, salt, 200000, dklen=32)
        associated_data = b"pakem-v2"
        if cipher_name == "aes-gcm":
            encrypted = AESGCM(key).encrypt(nonce, payload, associated_data)
        else:
            encrypted = ChaCha20Poly1305(key).encrypt(
                nonce, payload, associated_data
            )
        return encrypted, {
            "cipher": cipher_name,
            "kdf": "pbkdf2-hmac-sha256",
            "kdf_iterations": "200000",
            "kdf_salt_b64": b64encode(salt).decode("ascii"),
            "nonce_b64": b64encode(nonce).decode("ascii"),
        }

    return encrypt


def _decrypt_aead(
    cipher_name: str,
) -> Callable[[bytes, str, dict[str, str], bool], bytes]:
    def decrypt(
        payload: bytes,
        key_text: str,
        metadata: dict[str, str],
        legacy_mode: bool,
    ) -> bytes:
        passphrase = key_text.encode("utf-8", errors="replace")
        if not passphrase:
            raise ValueError("Encryption key must not be empty")
        try:
            iterations = int(str(metadata.get("kdf_iterations", "200000")))
            salt = b64decode(str(metadata["kdf_salt_b64"]))
            nonce = b64decode(str(metadata["nonce_b64"]))
        except Exception as exc:
            raise ValueError(
                "Archive encryption metadata is invalid or missing"
            ) from exc
        key = hashlib.pbkdf2_hmac(
            "sha256", passphrase, salt, iterations, dklen=32
        )
        associated_data = b"pakem-v2"
        try:
            if cipher_name == "aes-gcm":
                return AESGCM(key).decrypt(nonce, payload, associated_data)
            return ChaCha20Poly1305(key).decrypt(
                nonce, payload, associated_data
            )
        except InvalidTag as exc:
            raise ValueError(
                "Authentication failed: wrong encryption key or archive tampering detected"
            ) from exc

    return decrypt


def _encrypt_legacy_xor(
    payload: bytes, key_text: str
) -> tuple[bytes, dict[str, str]]:
    key_bytes = key_text.encode("utf-8", errors="replace")
    if not key_bytes:
        raise ValueError("Encryption key must not be empty")
    out = bytes(
        b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(payload)
    )
    return out, {"cipher": "legacy-xor"}


def _decrypt_legacy_xor(
    payload: bytes, key_text: str, metadata: dict[str, str], legacy_mode: bool
) -> bytes:
    if not legacy_mode:
        raise ValueError("Legacy cipher requires --legacy-mode")
    key_bytes = key_text.encode("utf-8", errors="replace")
    if not key_bytes:
        raise ValueError("Encryption key must not be empty")
    return bytes(
        b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(payload)
    )


def _compress_none(payload: bytes) -> bytes:
    return payload


def _decompress_none(payload: bytes) -> bytes:
    return payload


def _compress_zlib(payload: bytes) -> bytes:
    return zlib.compress(payload)


def _decompress_zlib(payload: bytes) -> bytes:
    try:
        return zlib.decompress(payload)
    except zlib.error as exc:
        raise ValueError(
            "Failed to decompress payload. Archive may be corrupted or encryption key is invalid."
        ) from exc


def _compress_zstd(payload: bytes) -> bytes:
    try:
        import zstandard as zstd
    except Exception as exc:
        raise ValueError("zstd compression requires package zstandard") from exc
    return zstd.ZstdCompressor(level=3).compress(payload)


def _decompress_zstd(payload: bytes) -> bytes:
    try:
        import zstandard as zstd
    except Exception as exc:
        raise ValueError(
            "zstd decompression requires package zstandard"
        ) from exc
    return zstd.ZstdDecompressor().decompress(payload)


def _compress_lz4(payload: bytes) -> bytes:
    try:
        import lz4.frame
    except Exception as exc:
        raise ValueError("lz4 compression requires package lz4") from exc
    return lz4.frame.compress(payload)


def _decompress_lz4(payload: bytes) -> bytes:
    try:
        import lz4.frame
    except Exception as exc:
        raise ValueError("lz4 decompression requires package lz4") from exc
    return lz4.frame.decompress(payload)


def _serializer_proto(output_path: str | None) -> Serializer:
    from pakem.serialize import ProtoSerializer

    return ProtoSerializer(output_path=output_path)


def _serializer_pakem(output_path: str | None) -> Serializer:
    from pakem.serialize import PakemSerializer

    return PakemSerializer(output_path=output_path)


def initialize_registries() -> None:
    if _COMPRESSION_REGISTRY:
        return

    register_compression(
        CompressionProfile("none", _compress_none, _decompress_none)
    )
    register_compression(
        CompressionProfile("zlib", _compress_zlib, _decompress_zlib)
    )
    register_compression(
        CompressionProfile("zstd", _compress_zstd, _decompress_zstd)
    )
    register_compression(
        CompressionProfile("lz4", _compress_lz4, _decompress_lz4)
    )

    register_crypto(CryptoProfile("none", _encrypt_none, _decrypt_none))
    register_crypto(
        CryptoProfile(
            "aes-gcm",
            _build_aead_encryptor("aes-gcm"),
            _decrypt_aead("aes-gcm"),
        )
    )
    register_crypto(
        CryptoProfile(
            "chacha20-poly1305",
            _build_aead_encryptor("chacha20-poly1305"),
            _decrypt_aead("chacha20-poly1305"),
        )
    )
    register_crypto(
        CryptoProfile("legacy-xor", _encrypt_legacy_xor, _decrypt_legacy_xor)
    )

    register_analyzer("text", _analyze_default)

    register_serializer(
        "xml", lambda output_path: XmlSerializer(output_path=output_path)
    )
    register_serializer(
        "json", lambda output_path: JsonSerializer(output_path=output_path)
    )
    register_serializer("proto", _serializer_proto)
    register_serializer("pakem", _serializer_pakem)
    register_serializer(
        "llm-prompt",
        lambda output_path: LlmPromptSerializer(output_path=output_path),
    )


initialize_registries()
