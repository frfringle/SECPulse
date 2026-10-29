"""HTML cleanup and token-budget truncation for later Ollama prompts."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style"}:
            self._skip = True
        if tag.lower() in {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"}:
            self._skip = False
        if tag.lower() in {"p", "div", "tr", "li", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._chunks.append(data)


_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")


def html_to_text(raw: str) -> str:
    """Convert HTML (or plain text) to normalized readable text."""
    if not raw:
        return ""
    # Fast path for plain text
    if "<" not in raw:
        text = html.unescape(raw)
    else:
        parser = _TextExtractor()
        try:
            parser.feed(raw)
            text = html.unescape("".join(parser._chunks))
        except Exception:  # noqa: BLE001
            text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = text.replace("\xa0", " ")
    text = _WS_RE.sub(" ", text)
    text = _BLANK_RE.sub("\n\n", text)
    return text.strip()


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) for budget checks."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def truncate_to_token_budget(text: str, token_budget: int) -> tuple[str, bool]:
    """Truncate text to approximately `token_budget` tokens.

    Returns (text, was_truncated).
    """
    if token_budget <= 0:
        return "", True
    if estimate_tokens(text) <= token_budget:
        return text, False
    # Keep head of document (most material for 8-K / 13D Item 4)
    char_budget = token_budget * 4
    truncated = text[:char_budget].rstrip()
    # Prefer breaking on a paragraph/sentence boundary
    for sep in ("\n\n", "\n", ". ", " "):
        idx = truncated.rfind(sep)
        if idx > char_budget * 0.6:
            truncated = truncated[: idx + len(sep)].rstrip()
            break
    return truncated + "\n…[truncated]", True
