from __future__ import annotations

import re
from typing import Any, Iterable

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.schemas.study_material import LearningContent, LearningSection

from .models import BotEvidenceChunk


_TOKEN_RE = re.compile(r"[a-z0-9]+")


class ConceptContentRetriever:
    def __init__(self) -> None:
        self._chunk_cache: dict[tuple[str, int], list[BotEvidenceChunk]] = {}

    def retrieve(
        self,
        *,
        concept_id: str,
        material_version: int,
        concept_name: str,
        content: LearningContent,
        query: str,
        max_chunks: int,
    ) -> list[BotEvidenceChunk]:
        cache_key = (concept_id, material_version)
        chunks = self._chunk_cache.get(cache_key)
        if chunks is None:
            chunks = self._build_chunks(concept_name=concept_name, content=content)
            self._chunk_cache[cache_key] = chunks
        return self._rank_chunks(query=query, chunks=chunks, max_chunks=max_chunks)

    def _build_chunks(self, *, concept_name: str, content: LearningContent) -> list[BotEvidenceChunk]:
        chunks: list[BotEvidenceChunk] = []
        if content.highlights:
            chunks.append(
                BotEvidenceChunk(
                    label=f"{concept_name}: highlights",
                    text=" ".join(str(item).strip() for item in content.highlights if str(item).strip()),
                    score=0.0,
                    source_type="internal",
                    note="Highlights from the current lesson",
                )
            )
        for section in content.sections:
            self._collect_section_chunks(section=section, path=[section.title], into=chunks)
        return [chunk for chunk in chunks if chunk.text.strip()]

    def _collect_section_chunks(
        self,
        *,
        section: LearningSection,
        path: list[str],
        into: list[BotEvidenceChunk],
    ) -> None:
        section_text = " ".join(self._flatten_block_texts(section.blocks)).strip()
        for index, piece in enumerate(self._split_text(section_text), start=1):
            note = " > ".join(path)
            label = section.title if index == 1 else f"{section.title} (part {index})"
            into.append(
                BotEvidenceChunk(
                    label=label,
                    text=piece,
                    score=0.0,
                    source_type="internal",
                    section_id=section.id,
                    note=note,
                )
            )
        for child in section.children or []:
            self._collect_section_chunks(section=child, path=[*path, child.title], into=into)

    @staticmethod
    def _flatten_block_texts(blocks: list[dict[str, Any]]) -> Iterable[str]:
        for block in blocks:
            block_type = block.get("type")
            if block_type == "paragraph":
                text = str(block.get("text", "")).strip()
                if text:
                    yield text
            elif block_type == "list":
                for item in block.get("items") or []:
                    text = str(item).strip()
                    if text:
                        yield text
            elif block_type == "formula":
                title = str(block.get("title", "")).strip()
                formula = str(block.get("formula", "")).strip()
                explanation = str(block.get("explanation", "")).strip()
                if title:
                    yield title
                if formula:
                    yield formula
                if explanation:
                    yield explanation
                for variable in block.get("variables") or []:
                    if isinstance(variable, dict):
                        symbol = str(variable.get("symbol", "")).strip()
                        meaning = str(variable.get("meaning", "")).strip()
                        text = " ".join(part for part in (symbol, meaning) if part)
                        if text:
                            yield text
            elif block_type == "callout":
                title = str(block.get("title", "")).strip()
                if title:
                    yield title
                content = block.get("content") or []
                if isinstance(content, list):
                    for item in content:
                        text = str(item).strip()
                        if text:
                            yield text
                else:
                    text = str(content).strip()
                    if text:
                        yield text
            elif block_type == "example":
                title = str(block.get("title", "")).strip()
                if title:
                    yield title
                for item in block.get("steps") or []:
                    text = str(item).strip()
                    if text:
                        yield text
                result = str(block.get("result", "")).strip()
                if result:
                    yield result

    @staticmethod
    def _split_text(text: str) -> list[str]:
        if not text:
            return []
        cleaned = " ".join(text.split()).strip()
        if len(cleaned) <= 420:
            return [cleaned]
        sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", cleaned) if item.strip()]
        pieces: list[str] = []
        current = ""
        for sentence in sentences:
            if not current:
                current = sentence
                continue
            if len(current) + len(sentence) + 1 <= 420:
                current = f"{current} {sentence}"
            else:
                pieces.append(current)
                current = sentence
        if current:
            pieces.append(current)
        return pieces or [cleaned]

    def _rank_chunks(self, *, query: str, chunks: list[BotEvidenceChunk], max_chunks: int) -> list[BotEvidenceChunk]:
        if not chunks:
            return []
        query_text = " ".join(query.split()).strip()
        tfidf_scores = self._score_with_tfidf(query_text, chunks)
        query_tokens = set(_TOKEN_RE.findall(query_text.lower()))
        ranked: list[BotEvidenceChunk] = []
        for index, chunk in enumerate(chunks):
            chunk_tokens = set(_TOKEN_RE.findall(chunk.text.lower()))
            label_tokens = set(_TOKEN_RE.findall(chunk.label.lower()))
            overlap = 0.0
            if query_tokens:
                overlap = len(query_tokens & chunk_tokens) / max(len(query_tokens), 1)
            title_boost = 0.0
            if query_tokens:
                title_boost = len(query_tokens & label_tokens) / max(len(query_tokens), 1)
            score = (tfidf_scores[index] * 0.72) + (overlap * 0.2) + (title_boost * 0.08)
            ranked.append(
                BotEvidenceChunk(
                    label=chunk.label,
                    text=chunk.text,
                    score=round(float(score), 4),
                    source_type=chunk.source_type,
                    section_id=chunk.section_id,
                    url=chunk.url,
                    note=chunk.note,
                )
            )
        ranked.sort(key=lambda item: item.score, reverse=True)
        limit = max(max_chunks, 1)
        return ranked[:limit]

    @staticmethod
    def _score_with_tfidf(query: str, chunks: list[BotEvidenceChunk]) -> list[float]:
        if not query.strip():
            return [0.0 for _ in chunks]
        corpus = [query, *[chunk.text for chunk in chunks]]
        try:
            vectorizer = TfidfVectorizer(stop_words="english")
            matrix = vectorizer.fit_transform(corpus)
            scores = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
            return [max(0.0, float(score)) for score in scores]
        except Exception:
            return [0.0 for _ in chunks]
