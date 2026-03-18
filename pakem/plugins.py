from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

from pakem.registries import (
    register_analyzer,
    register_compression,
    register_crypto,
    register_serializer,
)


@dataclass(frozen=True)
class PluginAPI:
    register_analyzer: object
    register_serializer: object
    register_compression: object
    register_crypto: object


def load_plugins(plugin_specs: list[str] | None) -> None:
    for spec in plugin_specs or []:
        _load_plugin(spec)


def _load_plugin(spec: str) -> None:
    path = Path(spec)
    if not path.exists():
        raise ValueError(f"Plugin path does not exist: {spec}")

    module_name = f"pakem_plugin_{abs(hash(path.resolve()))}"
    module_spec = importlib.util.spec_from_file_location(module_name, str(path))
    if module_spec is None or module_spec.loader is None:
        raise ValueError(f"Failed to load plugin: {spec}")

    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)

    register = getattr(module, "register", None)
    if not callable(register):
        raise ValueError(f"Plugin {spec} must define callable register(api)")

    api = PluginAPI(
        register_analyzer=register_analyzer,
        register_serializer=register_serializer,
        register_compression=register_compression,
        register_crypto=register_crypto,
    )
    register(api)
