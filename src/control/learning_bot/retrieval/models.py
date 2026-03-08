from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BotEvidenceChunk:
    label: str
    text: str
    score: float
    source_type: str
    section_id: str | None = None
    url: str | None = None
    note: str | None = None
    source_id: str = ""

    def to_prompt_block(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "label": self.label,
            "text": self.text,
            "source_type": self.source_type,
            "note": self.note or "",
        }

    def to_citation(self) -> dict[str, str | None]:
        return {
            "source_id": self.source_id,
            "label": self.label,
            "source_type": self.source_type,
            "url": self.url,
            "section_id": self.section_id,
            "note": self.note,
        }
