from __future__ import annotations

import json
import os
import struct
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def _ensure_dict(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError("Expected object to be a dict")
    return obj


def _ensure_list(obj: Any) -> list:
    if not isinstance(obj, list):
        raise ValueError("Expected object to be a list")
    return obj


def _validate_repository_dict(repo: dict[str, Any]) -> None:
    required = [
        "root",
        "timestamp",
        "total_files",
        "total_size",
        "total_tokens",
    ]
    for key in required:
        if key not in repo:
            raise ValueError(f"Missing required repository key: {key}")

    if not isinstance(repo["root"], str):
        raise ValueError("repository.root must be a string")

    if not isinstance(repo["timestamp"], str):
        raise ValueError("repository.timestamp must be a string")

    for key in ["total_files", "total_size", "total_tokens"]:
        if not isinstance(repo[key], int):
            raise ValueError(f"repository.{key} must be an integer")


def _validate_directories(dirs: Any) -> None:
    dirs = _ensure_list(dirs)
    for d in dirs:
        d = _ensure_dict(d)
        for key in ["name", "path", "depth"]:
            if key not in d:
                raise ValueError(f"Directory missing key: {key}")
        if not isinstance(d["name"], str):
            raise ValueError("Directory.name must be a string")
        if not isinstance(d["path"], str):
            raise ValueError("Directory.path must be a string")
        if not isinstance(d["depth"], int):
            raise ValueError("Directory.depth must be an integer")


def _validate_files(files: Any) -> None:
    files = _ensure_list(files)
    for f in files:
        f = _ensure_dict(f)
        required = [
            "name",
            "path",
            "size",
            "tokens",
            "type",
            "extension",
            "lines",
            "depth",
            "content",
        ]
        for key in required:
            if key not in f:
                raise ValueError(f"File missing key: {key}")

        if not isinstance(f["name"], str):
            raise ValueError("File.name must be a string")
        if not isinstance(f["path"], str):
            raise ValueError("File.path must be a string")
        for key in ["size", "tokens", "lines", "depth"]:
            if not isinstance(f[key], int):
                raise ValueError(f"File.{key} must be an integer")
        if not isinstance(f["content"], list):
            raise ValueError("File.content must be a list of strings")
        for line in f["content"]:
            if not isinstance(line, str):
                raise ValueError("File.content must be a list of strings")


def validate_json(path: str) -> None:
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    data = _ensure_dict(data)
    if "repository" not in data:
        raise ValueError("Missing top-level repository element")

    _validate_repository_dict(_ensure_dict(data["repository"]))
    _validate_directories(data.get("directories", []))
    _validate_files(data.get("files", []))


def validate_xml(path: str) -> None:
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag != "repository":
        raise ValueError("Root element must be <repository>")

    required_attrs = [
        "root",
        "timestamp",
        "total_files",
        "total_size",
        "total_tokens",
    ]
    for attr in required_attrs:
        if attr not in root.attrib:
            raise ValueError(f"Missing repository attribute: {attr}")

    for child in root:
        if child.tag not in {"directory", "file"}:
            raise ValueError(f"Unexpected element: {child.tag}")

        if child.tag == "directory":
            for attr in ["name", "path", "depth"]:
                if attr not in child.attrib:
                    raise ValueError(f"Directory missing attribute: {attr}")
        else:
            for attr in [
                "name",
                "path",
                "size",
                "tokens",
                "type",
                "extension",
                "lines",
                "depth",
            ]:
                if attr not in child.attrib:
                    raise ValueError(f"File missing attribute: {attr}")

            for line in child.findall("line"):
                for attr in ["index", "length", "indentation"]:
                    if attr not in line.attrib:
                        raise ValueError(f"Line missing attribute: {attr}")


def validate_proto(path: str) -> None:
    from pakem.proto import get_repository_message_class

    cls = get_repository_message_class()
    cls.FromString(Path(path).read_bytes())


def validate_pakem(path: str) -> None:
    data = Path(path).read_bytes()
    if len(data) < 9:
        raise ValueError("pakem payload too short")
    if data[:4] != b"PAKM":
        raise ValueError("Invalid pakem magic")
    version = data[4]
    if version != 1:
        raise ValueError("Unsupported pakem version")
    header_len = struct.unpack(">I", data[5:9])[0]
    metadata_end = 9 + header_len
    if metadata_end > len(data):
        raise ValueError("Invalid pakem header length")
    metadata = json.loads(data[9:metadata_end].decode("utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("pakem metadata must be a dict")
    if "repository" not in metadata or "files" not in metadata:
        raise ValueError("pakem metadata missing required keys")


def is_path_safe(base_dir: str, target_path: str) -> bool:
    base_real = os.path.realpath(base_dir)
    target_real = os.path.realpath(target_path)
    try:
        common = os.path.commonpath([base_real, target_real])
    except ValueError:
        return False
    return common == base_real


def validate(path: str, format: str | None = None) -> None:
    if not format:
        ext = Path(path).suffix.lower()
        if ext in {".json"}:
            format = "json"
        elif ext in {".xml"}:
            format = "xml"
        elif ext in {".pb", ".proto"}:
            format = "proto"
        elif ext in {".pakem"}:
            format = "pakem"
        else:
            raise ValueError("Could not infer format; specify explicitly")

    if format == "json":
        validate_json(path)
        return
    if format == "xml":
        validate_xml(path)
        return
    if format in {"proto", "protobuf"}:
        validate_proto(path)
        return
    if format == "pakem":
        validate_pakem(path)
        return

    raise ValueError(f"Unknown format: {format}")
