__version__ = "2.0.0"

from pakem.analyze import FileMetadata, analyze_text, count_tokens, is_binary
from pakem.cli import main
from pakem.commands import (
    ArchiveDiffCommand,
    BaseCommand,
    DiffCommand,
    ExploreCommand,
    PackCommand,
    RestoreCommand,
    SetupPrecommitCommand,
)
from pakem.ignore import IgnoreRules
from pakem.loaders import PakemLangChainLoader, PakemLlamaIndexReader
from pakem.packer import RepoPacker
from pakem.policy import PackagingPolicy
from pakem.serialize import XmlSerializer
from pakem.tokenizer import (
    DEFAULT_TOKEN_COUNTER,
    TokenCounter,
    get_token_counter,
)

__all__ = [
    "main",
    "RepoPacker",
    "IgnoreRules",
    "XmlSerializer",
    "analyze_text",
    "count_tokens",
    "is_binary",
    "FileMetadata",
    "DEFAULT_TOKEN_COUNTER",
    "get_token_counter",
    "TokenCounter",
    "BaseCommand",
    "PackCommand",
    "DiffCommand",
    "RestoreCommand",
    "PackagingPolicy",
    "ArchiveDiffCommand",
    "ExploreCommand",
    "SetupPrecommitCommand",
    "PakemLangChainLoader",
    "PakemLlamaIndexReader",
]
