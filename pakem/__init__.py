"""pakem - A repository packer that generates XML representations of codebases."""

__version__ = "1.0.0"

from pakem.core import (
    RepoPacker as RepoPacker,
    count_tokens as count_tokens,
    get_ignore_patterns as get_ignore_patterns,
    is_binary as is_binary,
    should_ignore as should_ignore,
)
