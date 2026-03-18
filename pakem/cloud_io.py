from __future__ import annotations

from pathlib import Path


def is_cloud_uri(path: str) -> bool:
    value = str(path)
    return (
        value.startswith("s3://")
        or value.startswith("gs://")
        or value.startswith("az://")
    )


def read_bytes(path: str) -> bytes:
    if not is_cloud_uri(path):
        return Path(path).read_bytes()

    fs, normalized = _get_filesystem(path)
    with fs.open(normalized, "rb") as handle:
        return handle.read()


def write_bytes(path: str, payload: bytes) -> int:
    if not is_cloud_uri(path):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return len(payload)

    fs, normalized = _get_filesystem(path)
    parent = _parent_uri(normalized)
    if parent:
        fs.makedirs(parent, exist_ok=True)
    with fs.open(normalized, "wb") as handle:
        handle.write(payload)
    return len(payload)


def write_text(path: str, text: str, encoding: str = "utf-8") -> int:
    data = text.encode(encoding)
    return write_bytes(path, data)


def _get_filesystem(path: str):
    try:
        import fsspec
    except Exception as exc:
        raise ValueError(
            "Cloud URI support requires fsspec and matching backend libraries"
        ) from exc

    protocol, remainder = path.split("://", 1)
    if protocol == "s3":
        fs = fsspec.filesystem("s3")
    elif protocol == "gs":
        fs = fsspec.filesystem("gcs")
    elif protocol == "az":
        fs = fsspec.filesystem("abfs")
    else:
        raise ValueError(f"Unsupported cloud protocol: {protocol}")

    return fs, remainder


def _parent_uri(path: str) -> str:
    if "/" not in path:
        return ""
    return path.rsplit("/", 1)[0]
