from __future__ import annotations

import hashlib
import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

from pakem.cloud_io import is_cloud_uri, read_bytes


def diff_archives(
    left_path: str,
    right_path: str,
    left_format: str | None = None,
    right_format: str | None = None,
) -> dict[str, list[str]]:
    left = _build_archive_index(left_path, left_format)
    right = _build_archive_index(right_path, right_format)

    left_paths = set(left.keys())
    right_paths = set(right.keys())

    added = sorted(right_paths - left_paths)
    removed = sorted(left_paths - right_paths)
    modified = sorted(
        path for path in (left_paths & right_paths) if left[path] != right[path]
    )

    return {"added": added, "modified": modified, "removed": removed}


def _build_archive_index(
    artifact_path: str, artifact_format: str | None
) -> dict[str, str]:
    path = Path(artifact_path)
    fmt = _resolve_format(path, artifact_format)
    raw_bytes = (
        read_bytes(artifact_path) if is_cloud_uri(artifact_path) else None
    )

    if fmt == "json":
        if raw_bytes is None:
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = json.loads(raw_bytes.decode("utf-8"))
        files = data.get("files", []) if isinstance(data, dict) else []
        index: dict[str, str] = {}
        for item in files:
            if not isinstance(item, dict):
                continue
            rel = str(item.get("path", ""))
            if not rel:
                continue
            digest = str(item.get("hash", ""))
            if not digest:
                content = "\n".join(item.get("content", []))
                digest = hashlib.sha256(
                    content.encode("utf-8", errors="replace")
                ).hexdigest()
            index[rel] = digest
        return index

    if fmt == "xml":
        if raw_bytes is None:
            tree = ET.parse(str(path))
        else:
            import io

            tree = ET.parse(io.BytesIO(raw_bytes))
        root = tree.getroot()
        index = {}
        for node in root.findall(".//file"):
            rel = node.attrib.get("path", "")
            if not rel:
                continue
            digest = node.attrib.get("hash")
            if not digest:
                lines = [line.text or "" for line in node.findall("line")]
                digest = hashlib.sha256(
                    "\n".join(lines).encode("utf-8", errors="replace")
                ).hexdigest()
            index[rel] = digest
        return index

    if fmt == "pakem":
        return _read_pakem_index(path, raw_bytes)

    raise ValueError(f"Unsupported archive format: {fmt}")


def _read_pakem_index(
    path: Path, raw_bytes: bytes | None = None
) -> dict[str, str]:
    data = raw_bytes if raw_bytes is not None else path.read_bytes()
    if len(data) < 9 or data[:4] != b"PAKM":
        raise ValueError("Invalid pakem archive")

    header_len = struct.unpack(">I", data[5:9])[0]
    metadata_start = 9
    metadata_end = metadata_start + header_len
    metadata = json.loads(data[metadata_start:metadata_end].decode("utf-8"))
    payload = data[metadata_end:]

    index: dict[str, str] = {}
    offset = 0
    for item in metadata.get("files", []):
        rel = str(item.get("path", ""))
        length = int(item.get("payload_length", 0))
        if not rel or length < 0 or offset + length > len(payload):
            continue
        chunk = payload[offset : offset + length]
        offset += length
        digest = str(item.get("hash", ""))
        if not digest:
            digest = hashlib.sha256(chunk).hexdigest()
        index[rel] = digest

    return index


def _resolve_format(path: Path, override: str | None) -> str:
    if override:
        normalized = override.lower()
        if normalized in {"proto", "protobuf"}:
            return "proto"
        return normalized

    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".xml":
        return "xml"
    if suffix == ".pakem":
        return "pakem"
    if suffix in {".pb", ".proto"}:
        return "proto"
    raise ValueError("Could not infer archive format")
