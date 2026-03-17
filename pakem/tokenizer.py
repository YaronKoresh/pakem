from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


class TokenCounter(Protocol):
    def count(self, text: str, model: str | None = None) -> int:
        pass


@dataclass(frozen=True)
class RegexTokenCounter:
    pattern: re.Pattern = re.compile(
        r"""(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\r\n\w]?:(?:[a-zA-Z_]\w*)+"""
        r"""|\d{1,3}| ?[^\s\w]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+"""
    )

    def count(self, text: str, model: str | None = None) -> int:
        if not text:
            return 0
        return len(self.pattern.findall(text))


class TiktokenTokenCounter:
    def __init__(self, model: str = "gpt-3.5-turbo") -> None:
        self.model = model
        try:
            import tiktoken

            self._encoder = tiktoken.encoding_for_model(model)
        except Exception:
            self._encoder = None

    def count(self, text: str, model: str | None = None) -> int:
        target = model or self.model
        if not text:
            return 0
        if self._encoder is None:
            return RegexTokenCounter().count(text, model=target)

        try:
            return len(self._encoder.encode(text))
        except Exception:
            return RegexTokenCounter().count(text, model=target)


def get_token_counter(model: str | None = None) -> TokenCounter:

    if not model:
        return RegexTokenCounter()

    try:
        import tiktoken

        return TiktokenTokenCounter(model=model)
    except Exception:
        return RegexTokenCounter()


DEFAULT_TOKEN_COUNTER: TokenCounter = get_token_counter(None)
