from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path


class PakemLangChainLoader:
    def __init__(self, path: str) -> None:
        self.path = path

    def load(self):
        suffix = Path(self.path).suffix.lower()
        docs: list[dict[str, object]] = []

        if suffix == ".json":
            payload = json.loads(Path(self.path).read_text(encoding="utf-8"))
            for item in payload.get("files", []):
                docs.append(
                    {
                        "page_content": "\n".join(item.get("content", [])),
                        "metadata": {
                            "path": item.get("path"),
                            "tokens": item.get("tokens"),
                        },
                    }
                )
            return docs

        if suffix == ".xml":
            root = ET.parse(self.path).getroot()
            for node in root.findall(".//file"):
                lines = [line.text or "" for line in node.findall("line")]
                docs.append(
                    {
                        "page_content": "\n".join(lines),
                        "metadata": {
                            "path": node.attrib.get("path"),
                            "tokens": node.attrib.get("tokens"),
                        },
                    }
                )
            return docs

        text = Path(self.path).read_text(encoding="utf-8")
        docs.append({"page_content": text, "metadata": {"path": self.path}})
        return docs


class PakemLlamaIndexReader:
    def load_data(self, file: str):
        loader = PakemLangChainLoader(file)
        docs = loader.load()
        nodes: list[dict[str, object]] = []
        for item in docs:
            nodes.append(
                {
                    "text": item.get("page_content", ""),
                    "metadata": item.get("metadata", {}),
                }
            )
        return nodes
