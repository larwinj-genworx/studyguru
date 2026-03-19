from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_domain(url: str) -> str:
    try:
        hostname = urlparse(url).hostname or ""
    except (AttributeError, TypeError, ValueError):
        return ""
    return hostname.lower().removeprefix("www.")


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    rank: int
    query: str
    provider: str = "duckduckgo"
    domain: str = ""
    domain_score: float = 0.0

    def __post_init__(self) -> None:
        if not self.domain:
            self.domain = extract_domain(self.url)


@dataclass(slots=True)
class SourceDocument:
    title: str
    url: str
    domain: str
    rank: int
    query: str
    snippet: str
    content_excerpt: str
    retrieval_status: str
    quality_score: float
    content_length: int
    retrieved_at: str
    provider: str = "duckduckgo"
    source_type: str = "webpage"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "rank": self.rank,
            "query": self.query,
            "snippet": self.snippet,
            "content_excerpt": self.content_excerpt,
            "retrieval_status": self.retrieval_status,
            "quality_score": round(self.quality_score, 4),
            "content_length": self.content_length,
            "retrieved_at": self.retrieved_at,
            "provider": self.provider,
            "source_type": self.source_type,
        }

    def to_reference(self) -> dict[str, str]:
        note_parts = [self.domain or "web"]
        if self.retrieval_status != "full_content":
            note_parts.append(self.retrieval_status.replace("_", " "))
        note_parts.append(f"quality {self.quality_score:.2f}")
        return {
            "title": self.title.strip()[:120] or "Resource",
            "url": self.url.strip(),
            "note": " | ".join(note_parts)[:240],
        }


@dataclass(slots=True)
class EvidenceSnippet:
    text: str
    source_url: str
    source_title: str
    domain: str
    query: str
    score: float
    snippet_type: str = "content"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source_url": self.source_url,
            "source_title": self.source_title,
            "domain": self.domain,
            "query": self.query,
            "score": round(self.score, 4),
            "snippet_type": self.snippet_type,
        }
